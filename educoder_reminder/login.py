"""Recover sessions through the normal password form; never log credentials."""
import fcntl
import json
import os
import re
import hashlib
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values, set_key
from playwright.async_api import Error as PlaywrightError

from .auth import signing_headers
from .errors import AuthenticationExpired, CollectionError, IdentityMismatch

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / '.env'
STATE_DIR = ROOT / 'data'
IDENTITY_URL = 'https://data.educoder.net/api/users/get_user_info.json'


async def verify_identity(context, username=None):
    response = await context.get(IDENTITY_URL, params={'school': 1}, headers=signing_headers(), max_redirects=0)
    try:
        if response.status == 401:
            raise AuthenticationExpired('Educoder 登录已失效。')
        if response.status != 200:
            raise CollectionError('身份验证接口异常，未尝试密码登录。')
        try:
            data = await response.json()
        except (ValueError, UnicodeError):
            raise CollectionError('身份验证响应无法解析。') from None
        if not isinstance(data, dict):
            raise CollectionError('身份验证响应结构异常。')
        if data.get('status') == 401:
            raise AuthenticationExpired('Educoder 登录已失效。')
        if data.get('status') not in (None, 0, 200):
            raise CollectionError('身份验证接口拒绝请求，请检查系统时间和签名。')
        if 'login' not in data:
            raise CollectionError('身份验证缺少账号字段。')
        if data['login'] in ('', None):
            raise AuthenticationExpired('Educoder 登录已失效。')
        actual = data['login']
        if not isinstance(actual, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', actual):
            raise CollectionError('身份接口返回了无效的 login。')
        if username is not None and actual != username:
            raise IdentityMismatch('当前会话与缓存账号不同，需要重新登录确认身份。')
        return actual
    finally:
        await response.dispose()


@contextmanager
def recovery_lock():
    STATE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (STATE_DIR / 'login.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CollectionError('已有进程正在恢复登录，请稍后重试。') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def reserve_attempt(username, now=None):
    """Persist before submitting: at most once/30min and 3 times/rolling 24h."""
    now = time.time() if now is None else now
    path = STATE_DIR / 'auth.sqlite3'
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    db = sqlite3.connect(path)
    try:
        db.execute('CREATE TABLE IF NOT EXISTS login_attempts (username TEXT NOT NULL, attempted_at REAL NOT NULL)')
        with db:
            db.execute('BEGIN IMMEDIATE')
            recent = db.execute('SELECT attempted_at FROM login_attempts WHERE username=? AND attempted_at>? ORDER BY attempted_at DESC',
                                (username, now - 86400)).fetchall()
            if recent and now - recent[0][0] < 1800:
                raise CollectionError('自动登录处于 30 分钟冷却期，请检查登录配置后等待重试。')
            if len(recent) >= 3:
                raise CollectionError('24 小时内自动登录已尝试 3 次，已暂停密码重试。')
            db.execute('INSERT INTO login_attempts VALUES (?,?)', (username, now))
    finally:
        db.close()


def persist_credentials(token, cookie, username=None):
    # Replace the whole pair atomically. Preserve the password and other settings.
    fd, name = tempfile.mkstemp(prefix='.env-login-', dir=ENV_PATH.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(ENV_PATH.read_text())
        set_key(temporary, 'EDUCODER_TOKEN', token)
        set_key(temporary, 'EDUCODER_COOKIE', cookie)
        if username is not None:
            set_key(temporary, 'EDUCODER_CLASSROOMS_URL', f'https://www.educoder.net/users/{username}/classrooms')
        temporary.chmod(0o600)
        os.replace(temporary, ENV_PATH)
    except OSError:
        raise CollectionError('登录成功但无法保存 .env，请检查运行用户对项目目录的写权限。') from None
    finally:
        temporary.unlink(missing_ok=True)
    os.environ['EDUCODER_TOKEN'] = token
    os.environ['EDUCODER_COOKIE'] = cookie
    if username is not None:
        os.environ['EDUCODER_CLASSROOMS_URL'] = f'https://www.educoder.net/users/{username}/classrooms'


async def checked_context(playwright, username, headers):
    context = await playwright.request.new_context(extra_http_headers=headers, timeout=30000)
    try:
        await verify_identity(context, username)
        return context
    except BaseException:
        await context.dispose()
        raise


async def recover_session(playwright, username, headers, *, force_login=False):
    with recovery_lock():
        values = dotenv_values(ENV_PATH, interpolate=False)
        # A different process may already have refreshed the file.
        candidate = dict(headers)
        candidate['Pc-Authorization'] = values.get('EDUCODER_TOKEN') or ''
        candidate['Cookie'] = values.get('EDUCODER_COOKIE') or ''
        if not force_login:
            try:
                context = await checked_context(playwright, username, candidate)
            except (AuthenticationExpired, IdentityMismatch):
                pass
            else:
                os.environ['EDUCODER_TOKEN'] = candidate['Pc-Authorization']
                os.environ['EDUCODER_COOKIE'] = candidate['Cookie']
                return context
        account = values.get('EDUCODER_LOGIN_ACCOUNT') or os.environ.get('EDUCODER_LOGIN_ACCOUNT')
        password = values.get('EDUCODER_LOGIN_PASSWORD') or os.environ.get('EDUCODER_LOGIN_PASSWORD')
        if not account or not password:
            raise CollectionError('登录已失效，请在本地 .env 填写 EDUCODER_LOGIN_ACCOUNT 和 EDUCODER_LOGIN_PASSWORD，或更新 Cookie/Token。')
        try:
            # 禁止使用代理（含系统代理）：Chromium 默认会读取桌面环境的系统代理设置，
            # 代理不稳定/出口 IP 变化会触发平台风控，导致登录间歇性失败。强制直连。
            browser = await playwright.chromium.launch(headless=True, args=['--no-proxy-server'])
        except PlaywrightError:
            raise CollectionError('自动登录无法启动 Chromium；请以服务运行用户执行 uv run playwright install chromium，并安装系统依赖。') from None
        try:
            browser_context = await browser.new_context()
            page = await browser_context.new_page()
            page.set_default_timeout(30000)
            await page.goto('https://www.educoder.net/user/login', wait_until='domcontentloaded', timeout=45000)
            await page.locator('#login').fill(account)
            await page.locator('#password').fill(password)
            await page.locator('#autologin').check()
            reserve_attempt(hashlib.sha256(account.encode()).hexdigest())
            def is_login_response(response):
                url = urlsplit(response.url)
                return url.hostname == 'data.educoder.net' and url.path == '/api/accounts/login.json' and response.request.method == 'POST'
            async with page.expect_response(is_login_response, timeout=30000) as pending:
                await page.get_by_role('button', name='登录', exact=True).click()
            response = await pending.value
            raw = await response.text()
            try:
                payload = json.loads(raw)
            except (ValueError, UnicodeError):
                payload = {}
            # 登录接口本身返回失败（如“用户名或密码错误”/触发验证码）时，直接报出平台原因，
            # 而不是把真实原因吞成笼统的“未生成会话”。
            if (isinstance(payload, dict) and not payload.get('login') and not payload.get('user_id')
                    and any(key in payload for key in ('status', 'message', 'msg'))):
                detail = payload.get('message') or payload.get('msg') or f"status={payload.get('status')}"
                raise CollectionError(f'账号密码登录被拒绝：{detail}（网页端能登录时多为验证码/风控限制）')
            # _educoder_session 由页面 JS 在登录接口返回后异步写入，不能立刻读到；
            # 稍作轮询，避免把“登录其实成功了”误判成“未生成会话”。
            token = ''
            for _ in range(20):
                cookies = await browser_context.cookies('https://data.educoder.net/api/users/get_user_info.json')
                token = next((c['value'] for c in cookies if c['name'] == '_educoder_session'), '')
                if token:
                    break
                await page.wait_for_timeout(250)
            if not token:
                raise CollectionError('登录未生成会话，请检查账号密码或是否出现验证码；已限制重试频率。')
            cookie = '; '.join(f"{c['name']}={c['value']}" for c in cookies)
            candidate = {**headers, 'Pc-Authorization': token, 'Cookie': cookie}
            # Browser cookies alone are not proof of successful login.
            context = await checked_context(playwright, None, candidate)
            try:
                actual = await verify_identity(context)
                persist_credentials(token, cookie, actual)
            except BaseException:
                await context.dispose()
                raise
            print(f'Educoder 自动登录成功，已根据身份接口更新课堂地址：{actual}。', flush=True)
            return context
        except AuthenticationExpired:
            raise CollectionError('账号密码登录未成功，请检查本地凭据或验证码；已限制重试频率。') from None
        except PlaywrightError:
            # Playwright error text may include passwords used by fill().
            raise CollectionError('自动登录未完成：可能为网络故障、页面变化或需要验证码；不输出浏览器请求详情。') from None
        finally:
            await browser.close()
