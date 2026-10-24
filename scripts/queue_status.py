"""查看多账号队列的运行状态（只读，不会提交任何东西）。

用法：
  uv run python scripts/queue_status.py            # 汇总所有账号
  uv run python scripts/queue_status.py --detail    # 附带每个账号的课堂进度
  uv run python scripts/queue_status.py --only 138xxx

显示内容：
- 队列里每个账号：密码是否就绪、上次运行结果与时间
- 真实登录态：当前 .env 是哪个账号、Token/Cookie 是否有效
- 登录冷却：是否处于 30 分钟冷却期
- 可选 --detail：联网读取每个账号的课堂/实验通过情况（较慢）
"""
import argparse
import asyncio
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ACCOUNTS = ROOT / 'data' / 'accounts.json'
STATE = ROOT / 'data' / 'queue_state.json'
AUTH_DB = ROOT / 'data' / 'auth.sqlite3'
ENV_PATH = ROOT / '.env'
LOG = ROOT / 'data' / 'queue.log'


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def read_env():
    from dotenv import dotenv_values
    return dotenv_values(ENV_PATH, interpolate=False) if ENV_PATH.exists() else {}


def login_cooldown(username_hash):
    """返回该账号距离可再次自动登录还需多少秒（0 表示不冷却）。"""
    if not AUTH_DB.exists():
        return 0
    db = sqlite3.connect(AUTH_DB)
    try:
        rows = db.execute(
            'SELECT attempted_at FROM login_attempts WHERE username=? AND attempted_at>? '
            'ORDER BY attempted_at DESC',
            (username_hash, time.time() - 86400)).fetchall()
    except sqlite3.Error:
        return 0
    finally:
        db.close()
    if not rows:
        return 0
    last = rows[0][0]
    if time.time() - last < 1800:
        return int(1800 - (time.time() - last))
    return 0


def fmt_age(ts_str):
    if not ts_str:
        return '-'
    try:
        ts = time.mktime(time.strptime(ts_str, '%Y-%m-%d %H:%M:%S'))
    except (ValueError, TypeError):
        return ts_str
    sec = int(time.time() - ts)
    if sec < 60:
        return f'{sec} 秒前'
    if sec < 3600:
        return f'{sec // 60} 分钟前'
    if sec < 86400:
        return f'{sec // 3600} 小时前'
    return f'{sec // 86400} 天前'


def show_queue(accounts, state):
    print('=' * 72)
    print('队列状态')
    print('=' * 72)
    if not accounts:
        print('队列为空。用 --add 或 --import-env 添加账号。')
        return
    print(f'{"账号":<14}{"备注":<10}{"状态":<9}{"密码":<22}{"最后运行":<10}')
    print('-' * 72)
    done = failed = pending = 0
    for a in accounts:
        acc = a.get('account', '')
        st = state.get(acc, {})
        status = st.get('status', 'pending')
        if status == 'done':
            done += 1
        elif status == 'failed':
            failed += 1
        else:
            pending += 1
        note = (a.get('note') or '')[:8]
        pwd = a.get('password') or ''
        pwd_show = '已加密' if pwd.startswith('enc:') else (pwd if pwd else '缺失')
        if len(pwd_show) > 20:
            pwd_show = pwd_show[:18] + '..'
        print(f'{acc:<14}{note:<10}{status:<9}{pwd_show:<22}{fmt_age(st.get("finished_at")):<10}')
        if status == 'done':
            print(f'{"":14}└ 提交 {st.get("submitted", 0)} / 失败 {st.get("failed", 0)}'
                  f' / 跳过已通过 {st.get("skipped_passed", 0)}')
        elif status == 'failed':
            print(f'{"":14}└ 错误：{st.get("error", "")[:70]}')
    print('-' * 72)
    print(f'总计 {len(accounts)} 个：完成 {done}，失败 {failed}，待处理 {pending}')


def show_session():
    print()
    print('=' * 72)
    print('当前登录态（.env）')
    print('=' * 72)
    env = read_env()
    account = env.get('EDUCODER_LOGIN_ACCOUNT') or ''
    has_token = bool(env.get('EDUCODER_TOKEN'))
    has_cookie = bool(env.get('EDUCODER_COOKIE'))
    print(f'配置账号：{account or "（未配置）"}')
    print(f'Token：{"有" if has_token else "无"}   Cookie：{"有" if has_cookie else "无"}'
          f'   {"（会话可用，无需密码登录）" if has_token and has_cookie else "（下次运行会用密码登录）"}')
    if account:
        import hashlib
        wait = login_cooldown(hashlib.sha256(account.encode()).hexdigest())
        if wait > 0:
            print(f'登录冷却：还需等待 {wait // 60} 分 {wait % 60} 秒')
        else:
            print('登录冷却：无')


def show_log_tail(lines=15):
    print()
    print('=' * 72)
    print(f'日志尾部（{LOG}）')
    print('=' * 72)
    if not LOG.exists():
        print('（没有日志文件；用 nohup ... > data/queue.log 2>&1 & 启动才会产生）')
        return
    try:
        content = LOG.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError as exc:
        print(f'读取失败：{exc}')
        return
    for line in content[-lines:]:
        print(line)


async def show_detail(account, password):
    """联网读取该账号的课堂与关卡通过情况。"""
    from educoder_reminder.courses import fetch_courses
    from educoder_reminder.client import open_client
    from educoder_reminder.submit import fetch_homework_rows
    from educoder_reminder.submit_all import COURSE_CUTOFF

    print()
    print('=' * 72)
    print(f'联网检查：{account}')
    print('=' * 72)
    try:
        async with open_client() as client:
            courses = await fetch_courses(client)
            courses = [c for c in courses if (c.created_at or '') >= COURSE_CUTOFF]
            total_exp = done_exp = 0
            for course in courses:
                rows = await fetch_homework_rows(client, course.identifier)
                finished = sum(1 for h in rows if h.get('shixun_finished_status') == 1)
                total_exp += len(rows)
                done_exp += finished
                print(f'  {course.name}：实验 {finished}/{len(rows)} 已完成')
            print(f'  合计：实验 {done_exp}/{total_exp} 已完成')
    except Exception as exc:
        print(f'  ✗ 检查失败：{type(exc).__name__}: {exc}')


def main():
    parser = argparse.ArgumentParser(description='查看多账号队列运行状态（只读）')
    parser.add_argument('--detail', action='store_true', help='联网检查课堂进度（较慢）')
    parser.add_argument('--only', help='只检查指定账号')
    parser.add_argument('--log-lines', type=int, default=15, help='显示日志尾部行数')
    args = parser.parse_args()

    accounts = load_json(ACCOUNTS, [])
    state = load_json(STATE, {})
    if args.only:
        accounts = [a for a in accounts if a.get('account') == args.only]

    show_queue(accounts, state)
    show_session()
    show_log_tail(args.log_lines)

    if args.detail and accounts:
        target = accounts[0]
        pwd = target.get('password') or ''
        if pwd.startswith('enc:'):
            import importlib.util
            spec = importlib.util.spec_from_file_location('rq', ROOT / 'scripts' / 'run_queue.py')
            rq = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rq)
            pwd = rq.decrypt_password(pwd)
        if not pwd:
            print('\n该账号没有可用密码，跳过联网检查。')
        else:
            # 用该账号临时登录检查（会写 .env，检查后请重新跑 --import-env 无需）
            import importlib.util
            spec = importlib.util.spec_from_file_location('rq', ROOT / 'scripts' / 'run_queue.py')
            rq = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rq)
            rq.activate_account(target.get('account'), pwd)
            asyncio.run(show_detail(target.get('account'), pwd))


if __name__ == '__main__':
    main()
