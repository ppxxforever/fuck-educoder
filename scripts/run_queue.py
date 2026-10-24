"""多账号队列：依次给多个账号刷题。

账号清单：data/accounts.json（不进 Git，权限 600）
  [
    {"account": "13800000000", "password": "xxx", "note": "同学A"},
    {"account": "13900000000", "password": "yyy", "note": "同学B"}
  ]

进度记录：data/queue_state.json（记录每个账号最后一次运行结果，支持断点续跑）

用法：
  # 添加账号（会写入 data/accounts.json）
  uv run python scripts/run_queue.py --add 13800000000 --password 'xxx' --note 同学A

  # 查看队列
  uv run python scripts/run_queue.py --list

  # 依次刷所有账号（真实提交）
  uv run python scripts/run_queue.py --apply

  # 只刷指定账号 / 跳过已完成的 / 每账号限 N 关
  uv run python scripts/run_queue.py --apply --only 13800000000
  uv run python scripts/run_queue.py --apply --skip-done
  uv run python scripts/run_queue.py --apply --limit 10

设计要点：
- 串行执行，任何时刻只有一个账号在用 Chromium（1M 带宽/4G 内存足够）
- 每个账号独立：切凭据 → 清登录冷却 → 跑 submit_all → 记录结果
- 单个账号失败不影响后续账号
"""
import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ACCOUNTS = ROOT / 'data' / 'accounts.json'
STATE = ROOT / 'data' / 'queue_state.json'
ENV_PATH = ROOT / '.env'
AUTH_DB = ROOT / 'data' / 'auth.sqlite3'
SESSION_KEYS = ('EDUCODER_TOKEN', 'EDUCODER_COOKIE', 'EDUCODER_CLASSROOMS_URL')


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def save_json(path, data, mode=0o600):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        tmp.chmod(mode)
    except OSError:
        pass
    tmp.replace(path)


def set_env_key(lines, key, value):
    prefix = f'{key}='
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{key}='{value}'"
            return lines
    lines.append(f"{key}='{value}'")
    return lines


def activate_account(account, password):
    """把凭据写进 .env，并清空上一个账号的会话（否则会先用旧 Cookie 请求）。"""
    if not ENV_PATH.exists():
        example = ROOT / '.env.example'
        if example.exists():
            ENV_PATH.write_text(example.read_text(encoding='utf-8'), encoding='utf-8')
    lines = ENV_PATH.read_text(encoding='utf-8').splitlines()
    lines = set_env_key(lines, 'EDUCODER_LOGIN_ACCOUNT', account)
    lines = set_env_key(lines, 'EDUCODER_LOGIN_PASSWORD', password)
    for key in SESSION_KEYS:
        lines = set_env_key(lines, key, '')
    ENV_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    try:
        ENV_PATH.chmod(0o600)
    except OSError:
        pass
    # 进程内环境同步（避免继续用旧值）
    os.environ['EDUCODER_LOGIN_ACCOUNT'] = account
    os.environ['EDUCODER_LOGIN_PASSWORD'] = password
    for key in SESSION_KEYS:
        os.environ[key] = ''


def clear_login_limit(account=None):
    """清掉该账号的自动登录冷却记录。"""
    if not AUTH_DB.exists():
        return 0
    import hashlib
    db = sqlite3.connect(AUTH_DB)
    try:
        with db:
            if account:
                key = hashlib.sha256(account.encode()).hexdigest()
                cur = db.execute('DELETE FROM login_attempts WHERE username=?', (key,))
            else:
                cur = db.execute('DELETE FROM login_attempts')
            return cur.rowcount
    finally:
        db.close()


def cmd_add(args):
    accounts = load_json(ACCOUNTS, [])
    if any(a.get('account') == args.account for a in accounts):
        raise SystemExit(f'账号 {args.account} 已在队列中。')
    accounts.append({'account': args.account, 'password': args.password,
                     'note': args.note or ''})
    save_json(ACCOUNTS, accounts)
    print(f'已添加账号 {args.account}（共 {len(accounts)} 个）')


def cmd_list(args):
    accounts = load_json(ACCOUNTS, [])
    state = load_json(STATE, {})
    if not accounts:
        print('队列为空。用 --add 添加账号。')
        return
    print(f'{"账号":<16}{"备注":<12}{"状态":<10}最后运行')
    for a in accounts:
        acc = a.get('account', '')
        st = state.get(acc, {})
        print(f'{acc:<16}{(a.get("note") or ""):<12}{st.get("status", "-"):<10}{st.get("finished_at", "-")}')


async def run_one(account, password, args, state):
    from educoder_reminder.submit_all import run_all

    print('\n' + '#' * 64)
    print(f'# 账号 {account}（{args_note(account)}）')
    print('#' * 64)
    activate_account(account, password)
    cleared = clear_login_limit(account)
    if cleared:
        print(f'已清理该账号登录冷却记录 {cleared} 条')

    started = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        stats = await run_all(
            apply=True, classroom_filter=args.classroom, limit=args.limit,
            poll_timeout=args.poll_timeout, experiment_filter=args.experiment,
            use_ai=not args.no_ai, release_pods=True, release_envs=False,
            answers_path=ROOT / 'answers.json', delay=args.delay)
    except Exception as exc:                      # 单账号失败不影响后续
        state[account] = {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}',
                          'started_at': started,
                          'finished_at': time.strftime('%Y-%m-%d %H:%M:%S')}
        print(f'\n✗ 账号 {account} 运行失败：{type(exc).__name__}: {exc}')
        return False
    state[account] = {
        'status': 'done',
        'submitted': stats.get('submitted', 0),
        'failed': stats.get('failed', 0),
        'skipped_passed': stats.get('skipped_passed', 0),
        'started_at': started,
        'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    print(f'\n✓ 账号 {account} 完成：提交 {stats.get("submitted", 0)}，'
          f'失败 {stats.get("failed", 0)}，跳过已通过 {stats.get("skipped_passed", 0)}')
    return True


_NOTES = {}


def args_note(account):
    return _NOTES.get(account, '')


async def cmd_run(args):
    accounts = load_json(ACCOUNTS, [])
    if not accounts:
        raise SystemExit('队列为空。用 --add 添加账号。')
    if args.only:
        accounts = [a for a in accounts if a.get('account') == args.only]
        if not accounts:
            raise SystemExit(f'队列中没有账号 {args.only}')
    state = load_json(STATE, {})
    if args.skip_done:
        before = len(accounts)
        accounts = [a for a in accounts if state.get(a.get('account'), {}).get('status') != 'done']
        print(f'跳过已完成账号 {before - len(accounts)} 个')

    for a in accounts:
        _NOTES[a.get('account', '')] = a.get('note') or ''
    print(f'共 {len(accounts)} 个账号待处理（串行执行）')
    ok = 0
    for a in accounts:
        acc, pwd = a.get('account'), a.get('password')
        if not acc or not pwd:
            print(f'跳过无效账号记录：{a}')
            continue
        if await run_one(acc, pwd, args, state):
            ok += 1
        save_json(STATE, state)                   # 每个账号后立即落盘，支持断点续跑
    print(f'\n===== 队列完成：{ok}/{len(accounts)} 个账号成功 =====')


def main():
    parser = argparse.ArgumentParser(description='多账号队列刷题')
    parser.add_argument('--add', metavar='ACCOUNT', help='添加账号')
    parser.add_argument('--password', help='配合 --add 使用的密码')
    parser.add_argument('--note', default='', help='配合 --add 的备注')
    parser.add_argument('--list', action='store_true', help='查看队列')
    parser.add_argument('--apply', action='store_true', help='真实提交（不加只打印计划）')
    parser.add_argument('--only', help='只处理指定账号')
    parser.add_argument('--skip-done', action='store_true', help='跳过已完成账号')
    parser.add_argument('--classroom', default=None, help='只处理指定课堂 code')
    parser.add_argument('--limit', type=int, default=None, help='每个账号最多处理多少关卡')
    parser.add_argument('--poll-timeout', type=int, default=120, help='评测等待秒数')
    parser.add_argument('--experiment', default=None, help='只处理名称包含该字符串的实验')
    parser.add_argument('--no-ai', action='store_true', help='禁用 AI 自动做题')
    parser.add_argument('--delay', type=float, default=5.0, help='实验之间等待秒数')
    args = parser.parse_args()

    if args.add:
        if not args.password:
            import getpass
            args.password = getpass.getpass('密码（不回显）: ')
        cmd_add(args)
        return
    if args.list:
        cmd_list(args)
        return
    if not args.apply:
        print('当前是预览模式，不会真实提交。加 --apply 执行。')
        cmd_list(args)
        return
    asyncio.run(cmd_run(args))


if __name__ == '__main__':
    main()
