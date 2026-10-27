"""多账号队列：依次给多个账号刷题。

账号清单：data/accounts.json（不进 Git，权限 600）
  [
    {"account": "13800000000", "password": "xxx", "note": "同学A"},
    {"account": "13900000000", "password": "yyy", "note": "同学B"}
  ]

每个账号可以单独指定要刷的课堂（写在 data/accounts.json 的 classrooms 字段）：
  {"account": "138...", "password": "xxx", "note": "同学A",
   "classrooms": ["2i6ng7vp", "数据库原理"]}
未配置 classrooms（或为空）表示该账号处理全部课堂；命令行 --classroom 会覆盖所有账号。

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
import random
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



KEY_FILE = ROOT / 'data' / '.queue_key'
_PREFIX = 'enc:'


def _fernet():
    """加载/生成队列加密密钥（600 权限，与 accounts.json 分开存放）。"""
    from cryptography.fernet import Fernet
    if KEY_FILE.exists():
        key = KEY_FILE.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        KEY_FILE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        KEY_FILE.write_bytes(key)
        try:
            KEY_FILE.chmod(0o600)
        except OSError:
            pass
    return Fernet(key)


def encrypt_password(plain, enabled=False):
    """把明文密码加密成 enc:<token>；enabled=False 时原样返回（默认明文）。"""
    if not plain or not enabled:
        return plain
    if plain.startswith(_PREFIX):
        return plain
    from cryptography.fernet import Fernet  # noqa: F401
    token = _fernet().encrypt(plain.encode('utf-8')).decode('ascii')
    return _PREFIX + token


def decrypt_password(stored):
    """解密；兼容历史上的明文记录（读到明文会自动重新加密）。"""
    if not stored:
        return ''
    if not stored.startswith(_PREFIX):
        return stored
    try:
        return _fernet().decrypt(stored[len(_PREFIX):].encode('ascii')).decode('utf-8')
    except Exception as exc:
        raise SystemExit(f'无法解密队列中的密码（密钥文件可能被替换）：{exc}') from None


def show_password(stored):
    """列表里显示密码：加密记录标注，明文直接显示（本地工具，方便核对）。"""
    if not stored:
        return '缺失'
    if stored.startswith(_PREFIX):
        return '已加密'
    return stored


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def save_accounts(accounts, encrypt=False):
    """写入账号清单。默认明文（数据只在本地，方便查看）；--encrypt 时加密。"""
    out = []
    for a in accounts:
        item = dict(a)
        item['password'] = encrypt_password(item.get('password', ''), enabled=encrypt)
        out.append(item)
    save_json(ACCOUNTS, out)


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


def classrooms_of(item):
    """读取某个账号自己的课堂筛选（空列表 = 全部课堂）。"""
    value = item.get('classrooms')
    out = []
    for part in value if isinstance(value, list) else []:
        part = str(part).strip()
        if part and part not in out:
            out.append(part)
    return out


def cmd_add(args):
    account = (args.add or '').strip()
    if not account:
        raise SystemExit('请用 --add <账号> 指定要添加的账号。')
    accounts = load_json(ACCOUNTS, [])
    if any(a.get('account') == account for a in accounts):
        raise SystemExit(f'账号 {account} 已在队列中（如需改密码请用 --import-env 或直接编辑文件）。')
    record = {'account': account, 'password': args.password or '',
              'note': args.note or ''}
    classrooms = classrooms_of({'classrooms': args.classroom})
    if classrooms:
        record['classrooms'] = classrooms
    accounts.append(record)
    save_accounts(accounts, args.encrypt)
    target = '、'.join(classrooms) if classrooms else '全部课堂'
    print(f'已添加账号 {account}  课程：{target}  （共 {len(accounts)} 个）')


def cmd_set_classrooms(args):
    """给某个账号单独指定课堂筛选；不传 --classroom 表示恢复全部课堂。"""
    account = (args.set_classrooms or '').strip()
    accounts = load_json(ACCOUNTS, [])
    for item in accounts:
        if item.get('account') == account:
            classrooms = classrooms_of({'classrooms': args.classroom})
            if classrooms:
                item['classrooms'] = classrooms
            else:
                item.pop('classrooms', None)
            save_accounts(accounts, getattr(args, 'encrypt', False))
            target = '、'.join(classrooms) if classrooms else '全部课堂'
            print(f'账号 {account} 的课程筛选已设为：{target}')
            return
    raise SystemExit(f'队列中没有账号 {account}')


def cmd_import_env(args):
    """把 .env 里当前的登录账号/密码导入队列（免去重新输入）。"""
    from dotenv import dotenv_values
    values = dotenv_values(ENV_PATH, interpolate=False)
    account = values.get('EDUCODER_LOGIN_ACCOUNT') or os.environ.get('EDUCODER_LOGIN_ACCOUNT')
    password = values.get('EDUCODER_LOGIN_PASSWORD') or os.environ.get('EDUCODER_LOGIN_PASSWORD')
    if not account or not password:
        raise SystemExit('当前 .env 里没有可用的 EDUCODER_LOGIN_ACCOUNT / EDUCODER_LOGIN_PASSWORD。')
    accounts = load_json(ACCOUNTS, [])
    for a in accounts:
        if a.get('account') == account:
            a['password'] = password
            if args.note:
                a['note'] = args.note
            save_accounts(accounts, getattr(args, 'encrypt', False))
            print(f'已更新队列中的账号 {account}')
            return
    accounts.append({'account': account, 'password': password, 'note': args.note or ''})
    save_accounts(accounts, getattr(args, 'encrypt', False))
    print(f'已从 .env 导入账号 {account}（共 {len(accounts)} 个）')


def cmd_list(args):
    accounts = load_json(ACCOUNTS, [])
    state = load_json(STATE, {})
    if not accounts:
        print('队列为空。用 --add 添加账号。')
        return
    print(f'{"账号":<16}{"密码":<18}{"备注":<8}{"课程":<20}{"状态":<8}最后运行')
    for a in accounts:
        acc = a.get('account', '')
        st = state.get(acc, {})
        pwd = show_password(a.get('password'))
        classrooms = classrooms_of(a)
        target = '、'.join(classrooms) if classrooms else '全部'
        if len(target) > 18:
            target = target[:17] + '…'
        print(f'{acc:<16}{pwd:<18}{(a.get("note") or ""):<8}'
              f'{target:<20}{st.get("status", "-"):<8}{st.get("finished_at", "-")}')


async def run_one(account, password, args, state, classrooms=None):
    from educoder_reminder.submit_all import run_all

    filters = args.classroom or classrooms or None
    print('\n' + '#' * 64)
    print(f'# 账号 {account}（{args_note(account)}）')
    print(f'# 课程：{"、".join(filters) if filters else "全部课堂"}')
    print('#' * 64)
    activate_account(account, password)
    cleared = clear_login_limit(account)
    if cleared:
        print(f'已清理该账号登录冷却记录 {cleared} 条')

    started = time.strftime('%Y-%m-%d %H:%M:%S')
    try:
        stats = await run_all(
            apply=True, classroom_filter=filters, limit=args.limit,
            poll_timeout=args.poll_timeout, experiment_filter=args.experiment,
            use_ai=not args.no_ai, release_pods=True, release_envs=False,
            answers_path=ROOT / 'answers.json', delay=args.delay,
            repair_status=getattr(args, 'repair_status', False),
            include_expired=getattr(args, 'include_expired', False))
    except Exception as exc:                      # 单账号失败不影响后续
        msg = f'{type(exc).__name__}: {exc}'
        # 账号密码错误属于永久性失败：标记 invalid，后续默认跳过（避免反复重试触发验证码）
        permanent = ('用户名或密码错误' in msg) or ('登录未生成会话' in msg) or ('验证码' in msg)
        state[account] = {
            'status': 'invalid' if permanent else 'failed',
            'error': msg,
            'started_at': started,
            'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        tag = '账号无效（密码错误/验证码），后续默认跳过；修正后加 --force 重跑' if permanent else '运行失败'
        print(f'\n✗ 账号 {account} {tag}：{msg}')
        return False
    unfinished = stats.get('unfinished', 0)
    unowned = stats.get('unowned', 0)
    audit_error = stats.get('audit_error', 0)
    # 状态就是契约：还有关卡没通关就不能算 done，否则下一轮会被 --skip-done 跳过，
    # 漏掉的实验就永远没人管了（2026-10-25 就是这么漏的）。
    left = unfinished + unowned + audit_error
    state[account] = {
        'status': 'pending' if left else 'done',
        'submitted': stats.get('submitted', 0),
        'failed': stats.get('failed', 0),
        'skipped_passed': stats.get('skipped_passed', 0),
        'unfinished': unfinished,
        'unowned': unowned,
        'audit_error': audit_error,
        'unconfirmed': stats.get('unconfirmed', 0),
        'stale_homework': stats.get('stale_homework', 0),
        'started_at': started,
        'finished_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    print(f'\n✓ 账号 {account} 完成：提交 {stats.get("submitted", 0)}，'
          f'失败 {stats.get("failed", 0)}，跳过已通过 {stats.get("skipped_passed", 0)}')
    if left:
        print(f'⚠️ 账号 {account} 仍有未完成项：未通关关卡 {unfinished}、'
              f'无主关卡 {unowned}、无法校验实验 {audit_error}；'
              '状态置为 pending，下轮会重试（明细见 data/unfinished.json）。')
    # 评测通过 ≠ 平台记通关（缺 sec_key 时平台只给分）。不阻塞完成判定（历史行为），
    # 但必须让人看到，否则就会出现「日志说通关、官网说未通关」。
    if stats.get('unconfirmed') or stats.get('stale_homework'):
        print(f'⚠️ 账号 {account} 有「评测通过但平台未记通关」：'
              f'关卡 {stats.get("unconfirmed", 0)} 个、实验 {stats.get("stale_homework", 0)} 个；'
              '可用 --repair-status 重修，或等平台自己同步。')
    return True


_NOTES = {}


def args_note(account):
    return _NOTES.get(account, '')


async def cmd_list_courses(args):
    """列出当前 .env 账号的课堂，方便拼 --classroom。"""
    from educoder_reminder.client import open_client
    from educoder_reminder.courses import fetch_courses
    async with open_client() as client:
        courses = await fetch_courses(client)
    print(f'当前账号可见 {len(courses)} 个进行中课堂：')
    print(f'{"code":<14}名称')
    print('-' * 60)
    for c in courses:
        print(f'{c.identifier:<14}{c.name}')
    print('\n用法示例：')
    print('  --classroom 2i6ng7vp')
    print('  --classroom 数据库')
    print('  --classroom "软件工程,数据库"')


async def cmd_run(args):
    accounts = load_json(ACCOUNTS, [])
    if not accounts:
        raise SystemExit('队列为空。用 --add 添加账号。')
    if args.only:
        accounts = [a for a in accounts if a.get('account') == args.only]
        if not accounts:
            raise SystemExit(f'队列中没有账号 {args.only}')
    state = load_json(STATE, {})
    if args.rerun_failed:
        reset = []
        for acc in accounts:
            st = state.get(acc.get('account'), {})
            if st.get('status') == 'done' and st.get('failed', 0) > 0:
                st['status'] = 'pending'
                st['prev_failed'] = st.get('failed', 0)
                reset.append(acc.get('account'))
        if reset:
            save_json(STATE, state)
            print(f'已把 {len(reset)} 个失败过的账号重新置为待处理：{"、".join(reset)}')
    if not args.force:
        before = len(accounts)
        done_list = [a for a in accounts
                     if state.get(a.get('account'), {}).get('status') in ('done', 'invalid')]
        accounts = [a for a in accounts if a not in done_list]
        if done_list:
            names = '、'.join(a.get('account', '') for a in done_list)
            print(f'跳过已完成/无效账号 {len(done_list)} 个（{names}）；要重跑加 --force')
    if not accounts:
        print('没有待处理的账号。')
        return

    for a in accounts:
        _NOTES[a.get('account', '')] = a.get('note') or ''
    print(f'共 {len(accounts)} 个账号待处理（串行执行，账号间隔 {args.gap}s）')
    print('课程安排：')
    for a in accounts:
        filters = args.classroom or classrooms_of(a)
        target = '、'.join(filters) if filters else '全部课堂'
        source = '（命令行覆盖）' if args.classroom else ''
        print(f'  {a.get("account", "")}: {target}{source}')
    ok = 0
    ran = 0
    for a in accounts:
        acc = a.get('account')
        pwd = decrypt_password(a.get('password') or '')
        if not acc or not pwd:
            print(f'跳过无效账号记录：{a}')
            continue
        if ran > 0 and args.gap > 0:
            wait = args.gap + random.randint(0, max(1, args.gap // 4))
            print(f'\n等待 {wait // 60} 分 {wait % 60} 秒再处理下一个账号'
                  f'（降低同 IP 连续登录的风控风险）…')
            await asyncio.sleep(wait)
        ran += 1
        if await run_one(acc, pwd, args, state, classrooms_of(a)):
            ok += 1
        save_json(STATE, state)                   # 每个账号后立即落盘，支持断点续跑
    print(f'\n===== 队列完成：{ok}/{len(accounts)} 个账号成功 =====')


def main():
    # nohup / 重定向到文件时 stdout 是块缓冲，日志会延迟很久才出现；
    # 改成行缓冲，tail -f 能实时看到进度
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)
        except Exception:
            pass

    parser = argparse.ArgumentParser(description='多账号队列刷题')
    parser.add_argument('--add', metavar='ACCOUNT', help='添加账号')
    parser.add_argument('--password', help='配合 --add 使用的密码')
    parser.add_argument('--note', default='', help='配合 --add 的备注')
    parser.add_argument('--set-classrooms', metavar='ACCOUNT',
                        help='给指定账号单独设置课程筛选（配合 --classroom；不传则恢复全部）')
    parser.add_argument('--list', action='store_true', help='查看队列')
    parser.add_argument('--import-env', action='store_true',
                        help='把 .env 里当前的账号密码导入队列')
    parser.add_argument('--encrypt', action='store_true',
                        help='把密码加密存储（默认明文，本地方便查看）')
    parser.add_argument('--list-courses', action='store_true',
                        help='列出当前账号可见的课堂（code 与名称），供 --classroom 使用')
    parser.add_argument('--apply', action='store_true', help='真实提交（不加只打印计划）')
    parser.add_argument('--only', help='只处理指定账号')
    parser.add_argument('--force', action='store_true',
                        help='强制重跑已完成账号（默认自动跳过，不再等待切换）')
    parser.add_argument('--rerun-failed', action='store_true',
                        help='把之前失败过（failed>0）的账号重新置为待处理，再跑队列')
    parser.add_argument('--skip-done', action='store_true',
                        help='（已默认开启，保留兼容）跳过已完成账号')
    parser.add_argument('--classroom', action='append', default=None,
                        help='只处理指定课堂：code 或课程名，可多次传或逗号分隔。'
                             '传了就覆盖所有账号；不传则用每个账号自己的 classrooms。'
                             '例：--classroom 2i6ng7vp --classroom 数据库')
    parser.add_argument('--limit', type=int, default=None, help='每个账号最多处理多少关卡')
    parser.add_argument('--poll-timeout', type=int, default=180, help='评测等待秒数')
    parser.add_argument('--experiment', default=None, help='只处理名称包含该字符串的实验')
    parser.add_argument('--no-ai', action='store_true', help='禁用 AI 自动做题')
    parser.add_argument('--repair-status', action='store_true',
                        help='重交「评测已通过但平台未记通关（status!=2）」的关卡')
    parser.add_argument('--include-expired', action='store_true',
                        help='连已截止/已归档的实验也处理（默认跳过）')
    parser.add_argument('--delay', type=float, default=5.0, help='实验之间等待秒数')
    parser.add_argument('--gap', type=int, default=300,
                        help='账号之间的间隔秒数（默认 300=5 分钟，降低风控风险；0 表示不等待）')
    args = parser.parse_args()

    if args.add:
        if not args.password:
            args.password = input('密码（会回显，方便核对）: ').strip()
        cmd_add(args)
        return
    if args.set_classrooms:
        cmd_set_classrooms(args)
        return
    if args.list_courses:
        asyncio.run(cmd_list_courses(args))
        return
    if args.import_env:
        cmd_import_env(args)
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
