"""Authenticated read-only API transport."""
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from playwright.async_api import async_playwright

from .auth import signing_headers
from .errors import AuthenticationExpired, CollectionError, IdentityMismatch
from .login import persist_credentials, recover_session, verify_identity


class Client:
    def __init__(self, context, username, playwright=None, headers=None):
        self.context = context
        self.username = username
        self.playwright = playwright
        self.headers = headers or {}
        self.recovered = False

    async def recover(self, *, force_login=False):
        if self.recovered or self.playwright is None:
            raise AuthenticationExpired('登录恢复后会话仍无效，本次采集已停止。')
        self.recovered = True
        replacement = await recover_session(self.playwright, self.username, self.headers, force_login=force_login)
        await self.context.dispose()
        self.context = replacement
        self.username = await verify_identity(self.context)

    async def ensure_authenticated(self):
        try:
            actual = await verify_identity(self.context, self.username)
        except AuthenticationExpired:
            await self.recover()
        except IdentityMismatch:
            await self.recover(force_login=True)
        else:
            if self.username is None:
                if os.environ.get('EDUCODER_LOGIN_ACCOUNT') and os.environ.get('EDUCODER_LOGIN_PASSWORD'):
                    await self.recover(force_login=True)
                else:
                    persist_credentials(self.headers.get('Pc-Authorization', ''), self.headers.get('Cookie', ''), actual)
                    self.username = actual

    async def get(self, path, params):
        if not path.startswith('/api/') or '?' in path or '..' in path:
            raise CollectionError('无效的 API 路径。')
        original_username = self.username
        try:
            return await self._get(path, params)
        except (AuthenticationExpired, IdentityMismatch) as exc:
            await self.recover(force_login=isinstance(exc, IdentityMismatch))
        except CollectionError:
            # Permission/signature/format failures are not proof of expiration.
            try:
                await verify_identity(self.context, self.username)
            except (AuthenticationExpired, IdentityMismatch) as exc:
                await self.recover(force_login=isinstance(exc, IdentityMismatch))
            else:
                raise
        if self.username != original_username:
            raise CollectionError('登录身份已更新，请重新采集新账号课堂；未重试旧账号请求。')
        return await self._get(path, params)

    async def _get(self, path, params):
        response = await self.context.get(
            'https://data.educoder.net' + path,
            params={**params, 'zzud': self.username},
            headers={**signing_headers(), 'Referer': f'https://www.educoder.net/users/{self.username}/classrooms'}, max_redirects=0,
        )
        try:
            if response.status == 401:
                raise AuthenticationExpired('Educoder 登录已失效。')
            if response.status != 200:
                raise CollectionError(f'接口 HTTP {response.status}，未保存本次结果。')
            try:
                data = await response.json()
            except (ValueError, UnicodeError):
                raise CollectionError('接口未返回有效 JSON。') from None
            if not isinstance(data, dict):
                raise CollectionError('接口返回结构异常。')
            if data.get('status') == 401:
                raise AuthenticationExpired('Educoder 登录已失效。')
            if data.get('status') not in (None, 0, 200):
                raise CollectionError('接口拒绝请求，请检查登录凭据、系统时间及签名。')
            return data
        finally:
            await response.dispose()


def load_settings():
    load_dotenv(Path(__file__).resolve().parents[1] / '.env', interpolate=False)
    url = os.environ.get('EDUCODER_CLASSROOMS_URL', '')
    parts = urlsplit(url)
    match = re.fullmatch(r'/users/([A-Za-z0-9_-]+)/classrooms/?', parts.path)
    cached_username = match[1] if parts.scheme == 'https' and parts.netloc == 'www.educoder.net' and match else None
    has_session = all(os.environ.get(key) for key in ['EDUCODER_TOKEN', 'EDUCODER_COOKIE'])
    has_password = all(os.environ.get(key) for key in ['EDUCODER_LOGIN_ACCOUNT', 'EDUCODER_LOGIN_PASSWORD'])
    if not has_session and not has_password:
        raise CollectionError('请在 .env 中填写 Token/Cookie，或登录账号和密码。')
    headers = {
        'Accept': 'application/json', 'Content-Type': 'application/json; charset=utf-8',
        'Pc-Authorization': os.environ.get('EDUCODER_TOKEN', ''),
        'Cookie': os.environ.get('EDUCODER_COOKIE', ''), 'X-EDU-Type': 'pc',
        'Referer': 'https://www.educoder.net/', 'Origin': 'https://www.educoder.net',
        'X-Original-Protocol': 'https:', 'X-Original-Host': 'www.educoder.net',
        'X-Original-Origin': 'https://www.educoder.net',
    }
    return cached_username, headers


@asynccontextmanager
async def open_client():
    username, headers = load_settings()
    async with async_playwright() as p:
        context = await p.request.new_context(extra_http_headers=headers, timeout=30000)
        client = Client(context, username, p, headers)
        try:
            await client.ensure_authenticated()
            yield client
            # Do not commit a batch fetched while the session silently expired.
            await verify_identity(client.context, client.username)
        finally:
            await client.context.dispose()
