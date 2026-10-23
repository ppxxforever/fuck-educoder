"""一键切换 Educoder 账号：更新 .env 并清除旧会话缓存。

用法（在项目根目录）：
  uv run python scripts/switch_account.py                      # 交互输入
  uv run python scripts/switch_account.py --account 138xxx --password 'xxx'
  uv run python scripts/switch_account.py --account 138xxx     # 交互输入密码
  uv run python scripts/switch_account.py --clear-limit        # 顺带清除登录冷却记录

做的事：
  1. 写入 EDUCODER_LOGIN_ACCOUNT / EDUCODER_LOGIN_PASSWORD
  2. 清空 EDUCODER_TOKEN / EDUCODER_COOKIE / EDUCODER_CLASSROOMS_URL
     （这些都是上一个账号的会话，不清空会先用旧 Cookie 请求，再触发身份校验失败）
  3. --clear-limit 时清空 data/auth.sqlite3 里的自动登录冷却记录
下次运行 submit_all 时会用新账号自动登录。
"""
import argparse
import getpass
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / '.env'
AUTH_DB = ROOT / 'data' / 'auth.sqlite3'
SESSION_KEYS = ('EDUCODER_TOKEN', 'EDUCODER_COOKIE', 'EDUCODER_CLASSROOMS_URL')


def read_env(path):
    lines = []
    if path.exists():
        lines = path.read_text(encoding='utf-8').splitlines()
    return lines


def set_key(lines, key, value):
    prefix = f'{key}='
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{key}='{value}'"
            return lines
    lines.append(f"{key}='{value}'")
    return lines


def main():
    parser = argparse.ArgumentParser(description='切换 Educoder 账号并清除旧会话缓存。')
    parser.add_argument('--account', help='登录账号（手机号/邮箱/用户名）')
    parser.add_argument('--password', help='密码（不传则交互输入，不会回显）')
    parser.add_argument('--clear-limit', action='store_true', help='清除自动登录冷却记录')
    args = parser.parse_args()

    account = args.account or input('登录账号: ').strip()
    if not account:
        raise SystemExit('账号不能为空。')
    password = args.password or getpass.getpass('密码（不回显）: ')
    if not password:
        raise SystemExit('密码不能为空。')

    if not ENV_PATH.exists():
        example = ROOT / '.env.example'
        if example.exists():
            ENV_PATH.write_text(example.read_text(encoding='utf-8'), encoding='utf-8')
            print(f'已从 .env.example 创建 {ENV_PATH}')
    lines = read_env(ENV_PATH)
    lines = set_key(lines, 'EDUCODER_LOGIN_ACCOUNT', account)
    lines = set_key(lines, 'EDUCODER_LOGIN_PASSWORD', password)
    # 清空上一个账号的会话，避免先用旧凭据请求
    for key in SESSION_KEYS:
        lines = set_key(lines, key, '')
    ENV_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    try:
        ENV_PATH.chmod(0o600)
    except OSError:
        pass
    print(f'已更新 {ENV_PATH.name}：账号={account}，旧 Token/Cookie/课堂地址已清空')

    if args.clear_limit:
        if AUTH_DB.exists():
            db = sqlite3.connect(AUTH_DB)
            try:
                with db:
                    db.execute('DELETE FROM login_attempts')
            finally:
                db.close()
            print('已清除自动登录冷却记录')
        else:
            print('没有登录记录需要清除')

    print('\n验证（会联网登录一次）：')
    print('  uv run python -m educoder_reminder.courses')
    print('做题：')
    print('  uv run python -m educoder_reminder.submit_all --apply')


if __name__ == '__main__':
    main()
