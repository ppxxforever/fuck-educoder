"""逐个验证队列里账号的密码是否正确（只登录，不做题）。

用法：
  uv run python scripts/verify_accounts.py            # 验证所有账号
  uv run python scripts/verify_accounts.py --only 138xxx
  uv run python scripts/verify_accounts.py --clear-limit   # 验证前先清该账号登录冷却

说明：
- 每个账号独立验证（切凭据 → 清该账号冷却 → 用浏览器真实登录一次）
- 会覆盖 .env 里的登录账号，验证结束后请用
  `uv run python scripts/run_queue.py --import-env` 重新同步，或直接开始跑队列
- 平台限制：同一账号 30 分钟内最多尝试 1 次密码登录，24 小时 3 次
"""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

ACCOUNTS = ROOT / 'data' / 'accounts.json'
AUTH_DB = ROOT / 'data' / 'auth.sqlite3'

_spec = importlib.util.spec_from_file_location('rq', ROOT / 'scripts' / 'run_queue.py')
rq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rq)


def clear_limit(account):
    if not AUTH_DB.exists():
        return 0
    key = hashlib.sha256(account.encode()).hexdigest()
    db = sqlite3.connect(AUTH_DB)
    try:
        with db:
            cur = db.execute('DELETE FROM login_attempts WHERE username=?', (key,))
            return cur.rowcount
    finally:
        db.close()


async def try_login(account, password):
    """用 Playwright 真实登录一次，返回 (是否成功, 说明)。"""
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        # 禁止使用代理（含系统代理）：强制直连，避免系统代理干扰登录结果。
        browser = await p.chromium.launch(headless=True, args=['--no-proxy-server'])
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            page.set_default_timeout(30000)
            await page.goto('https://www.educoder.net/user/login',
                            wait_until='domcontentloaded', timeout=45000)
            await page.locator('#login').fill(account)
            await page.locator('#password').fill(password)
            async with page.expect_response(
                    lambda r: r.url.endswith('/api/accounts/login.json')
                    and r.request.method == 'POST', timeout=30000) as pending:
                await page.get_by_role('button', name='登录', exact=True).click()
            resp = await pending.value
            body = await resp.text()
            if resp.status != 200:
                return False, f'HTTP {resp.status}'
            try:
                data = json.loads(body)
            except ValueError:
                return False, f'返回非 JSON：{body[:80]}'
            # 成功时平台直接返回用户信息（含 login / user_id），失败时返回 status=-3 等
            if data.get('login') or data.get('user_id'):
                return True, f"登录成功（{data.get('login')}）"
            status = data.get('status')
            return False, data.get('message') or data.get('msg') or f'status={status}'
        finally:
            await browser.close()


async def main():
    parser = argparse.ArgumentParser(description='验证队列账号密码是否正确')
    parser.add_argument('--only', help='只验证指定账号')
    parser.add_argument('--clear-limit', action='store_true', help='验证前清除该账号登录冷却')
    args = parser.parse_args()

    accounts = rq.load_json(ACCOUNTS, [])
    if args.only:
        accounts = [a for a in accounts if a.get('account') == args.only]
    if not accounts:
        raise SystemExit('队列为空或没有匹配的账号。')

    print(f'待验证 {len(accounts)} 个账号\n')
    results = []
    for a in accounts:
        acc = a.get('account')
        pwd = rq.decrypt_password(a.get('password') or '')
        if not acc or not pwd:
            print(f'{acc or "(空)"}: 缺少账号或密码，跳过')
            results.append((acc, False, '缺少密码'))
            continue
        if args.clear_limit:
            n = clear_limit(acc)
            if n:
                print(f'{acc}: 已清登录冷却记录 {n} 条')
        ok, msg = await try_login(acc, pwd)
        print(f'{acc}: {"✓ " if ok else "✗ "}{msg}')
        results.append((acc, ok, msg))

    print('\n===== 汇总 =====')
    good = sum(1 for _, ok, _ in results if ok)
    print(f'可用 {good}/{len(results)}')
    for acc, ok, msg in results:
        if not ok:
            print(f'  ✗ {acc}: {msg}')
    if good:
        print('\n下一步：直接跑队列（会自动切换账号）')
        print('  uv run python scripts/run_queue.py --apply --skip-done')


if __name__ == '__main__':
    asyncio.run(main())
