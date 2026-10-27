"""TUI 数据层：读取本地状态（课堂/作业/队列/日志），并做少量必要的写操作。

只读逻辑全部集中在这里，方便脱离界面测试：
  - 不改动平台、不发请求；
  - 唯一的写操作是账号队列（data/accounts.json）和当前账号（.env），
    以及清除登录冷却记录（data/auth.sqlite3），与 scripts/ 下的脚本行为一致。
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / 'data'
ENV_PATH = ROOT / '.env'
ENV_EXAMPLE = ROOT / '.env.example'
ACCOUNTS = DATA_DIR / 'accounts.json'
QUEUE_STATE = DATA_DIR / 'queue_state.json'
# 一键提交的收尾校验报告：记录「哪些实验还有几关没交」
UNFINISHED_JSON = DATA_DIR / 'unfinished.json'
COURSES_CACHE = DATA_DIR / 'courses.json'
HOMEWORKS_JSON = DATA_DIR / 'homeworks.json'
REMINDER_DB = DATA_DIR / 'reminder.sqlite3'
AUTH_DB = DATA_DIR / 'auth.sqlite3'
QUEUE_LOG = DATA_DIR / 'queue.log'
TUI_LOG = DATA_DIR / 'tui.log'

BEIJING = ZoneInfo('Asia/Shanghai')
SESSION_KEYS = ('EDUCODER_TOKEN', 'EDUCODER_COOKIE', 'EDUCODER_CLASSROOMS_URL')

KIND_NAMES = {4: '课堂实验', 1: '图文作业'}

STATE_LABELS = {
    'pending': '待完成',
    'overdue': '已逾期',
    'completed': '已完成',
    'archived': '已归档',
    'unpublished': '未发布',
    'no_deadline': '无截止时间',
    'unknown_completion': '完成状态未知',
    'unknown_publication': '发布状态未知',
}

# Textual/Rich 颜色名
STATE_COLORS = {
    'pending': 'yellow',
    'overdue': 'red',
    'completed': 'green',
    'archived': 'grey62',
    'unpublished': 'grey62',
    'no_deadline': 'magenta',
    'unknown_completion': 'orange3',
    'unknown_publication': 'orange3',
}

STATE_ORDER = {
    'pending': 0,
    'overdue': 1,
    'no_deadline': 2,
    'unknown_completion': 3,
    'unknown_publication': 4,
    'unpublished': 5,
    'completed': 6,
    'archived': 7,
}


# --------------------------------------------------------------------------- #
# 通用读写
# --------------------------------------------------------------------------- #
def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def save_json(path: Path, data, mode: int = 0o600) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    try:
        tmp.chmod(mode)
    except OSError:
        pass
    tmp.replace(path)


def read_env() -> dict:
    """按字面读取 .env（不做环境变量替换，密码里的 $ 不会被展开）。"""
    if not ENV_PATH.exists():
        return {}
    values = {}
    for line in ENV_PATH.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _set_env_key(lines: list[str], key: str, value: str) -> list[str]:
    prefix = f'{key}='
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{key}='{value}'"
            return lines
    lines.append(f"{key}='{value}'")
    return lines


# --------------------------------------------------------------------------- #
# 会话 / 账号
# --------------------------------------------------------------------------- #
def session() -> dict:
    env = read_env()
    account = env.get('EDUCODER_LOGIN_ACCOUNT', '')
    tokens = bool(env.get('EDUCODER_TOKEN')) and bool(env.get('EDUCODER_COOKIE'))
    return {
        'account': account,
        'has_token': bool(env.get('EDUCODER_TOKEN')),
        'has_cookie': bool(env.get('EDUCODER_COOKIE')),
        'session_ready': tokens,
        'classrooms_url': env.get('EDUCODER_CLASSROOMS_URL', ''),
        'ai_configured': bool(env.get('AI_API_KEY')),
        'ai_model': env.get('AI_MODEL', ''),
        'sendkey': bool(env.get('SERVERCHAN_SENDKEY')),
        'sync_hours': env.get('SYNC_INTERVAL_HOURS', ''),
        'cooldown': cooldown_seconds(account),
        'env_exists': ENV_PATH.exists(),
    }


def cooldown_seconds(account: str) -> int:
    """自动登录冷却剩余秒数（同账号 30 分钟内不允许再次密码登录）。"""
    if not account or not AUTH_DB.exists():
        return 0
    key = hashlib.sha256(account.encode()).hexdigest()
    try:
        db = sqlite3.connect(AUTH_DB)
        try:
            row = db.execute(
                'SELECT attempted_at FROM login_attempts WHERE username=? '
                'ORDER BY attempted_at DESC LIMIT 1', (key,)).fetchone()
        finally:
            db.close()
    except sqlite3.Error:
        return 0
    if not row:
        return 0
    elapsed = time.time() - float(row[0])
    return max(0, int(1800 - elapsed)) if elapsed < 1800 else 0


def accounts() -> list[dict]:
    data = load_json(ACCOUNTS, [])
    return [a for a in data if isinstance(a, dict)] if isinstance(data, list) else []


def account_names() -> list[str]:
    return [str(a.get('account', '')) for a in accounts() if a.get('account')]


def clean_classrooms(values) -> list[str]:
    """把课程筛选值整理成去重列表（兼容列表 / 逗号分隔字符串 / 中文逗号）。"""
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    for value in values or []:
        for part in str(value).replace('，', ',').split(','):
            part = part.strip()
            if part and part not in out:
                out.append(part)
    return out


def add_account(account: str, password: str, note: str = '',
                classrooms=None) -> None:
    account = account.strip()
    if not account:
        raise ValueError('账号不能为空')
    if not password:
        raise ValueError('密码不能为空')
    items = accounts()
    cleaned = None if classrooms is None else clean_classrooms(classrooms)
    for item in items:
        if item.get('account') == account:
            item['password'] = password
            item['note'] = note or item.get('note', '')
            if cleaned is None:
                pass                     # 不传 classrooms 时保留原有课程设置
            elif cleaned:
                item['classrooms'] = cleaned
            else:
                item.pop('classrooms', None)
            break
    else:
        record = {'account': account, 'password': password, 'note': note}
        if cleaned:
            record['classrooms'] = cleaned
        items.append(record)
    save_json(ACCOUNTS, items)


def account_classrooms(account: str) -> list[str]:
    """该账号指定的课堂筛选；空列表表示处理全部课堂。"""
    for item in accounts():
        if item.get('account') == account:
            return clean_classrooms(item.get('classrooms'))
    return []


def set_account_classrooms(account: str, classrooms) -> None:
    items = accounts()
    for item in items:
        if item.get('account') == account:
            cleaned = clean_classrooms(classrooms)
            if cleaned:
                item['classrooms'] = cleaned
            else:
                item.pop('classrooms', None)
            save_json(ACCOUNTS, items)
            return
    raise ValueError(f'队列中没有账号 {account}')


def remove_account(account: str) -> bool:
    items = accounts()
    kept = [a for a in items if a.get('account') != account]
    if len(kept) == len(items):
        return False
    save_json(ACCOUNTS, kept)
    return True


def decrypt_password(stored: str) -> str:
    """兼容 enc: 前缀的加密记录；没有 cryptography 或解密失败时原样返回。"""
    if not stored or not stored.startswith('enc:'):
        return stored
    try:
        from cryptography.fernet import Fernet
        key_file = DATA_DIR / '.queue_key'
        key = key_file.read_bytes().strip()
        return Fernet(key).decrypt(stored[4:].encode('ascii')).decode('utf-8')
    except Exception:
        return ''


def password_display(item: dict, reveal: bool = False) -> str:
    stored = str(item.get('password') or '')
    if not stored:
        return '缺失'
    if stored.startswith('enc:'):
        if not reveal:
            return '已加密'
        plain = decrypt_password(stored)
        return mask(plain) if plain else '无法解密'
    return stored if reveal else mask(stored)


def mask(text: str) -> str:
    if not text:
        return ''
    if len(text) <= 3:
        return '***'
    return text[:3] + '***'


def queue_state() -> dict:
    data = load_json(QUEUE_STATE, {})
    return data if isinstance(data, dict) else {}


QUEUE_STATUSES = ('pending', 'done', 'failed')
QUEUE_STATUS_LABELS = {'pending': '待处理', 'done': '已完成', 'failed': '失败'}


def set_queue_status(account: str, status: str, *, error: str = '',
                     reset_progress: bool = False) -> None:
    """手动设置队列状态（TUI 用）。

    pending: 重新进入待处理队列；done: run_queue 默认跳过；failed: 记录失败原因。
    reset_progress=True 时同时清空历史计数。
    """
    if status not in QUEUE_STATUSES:
        raise ValueError(f'未知状态：{status}')
    if account not in account_names():
        raise ValueError(f'队列中没有账号 {account}')
    state = queue_state()
    item = dict(state.get(account) or {})
    item['status'] = status
    item['manual'] = True
    if status == 'failed':
        item['error'] = error or '手动标记失败'
        item['finished_at'] = datetime.now(BEIJING).strftime('%Y-%m-%d %H:%M:%S')
    elif status == 'done':
        item.pop('error', None)
        item['finished_at'] = datetime.now(BEIJING).strftime('%Y-%m-%d %H:%M:%S')
    else:
        item.pop('error', None)
    if reset_progress:
        for key in ('submitted', 'failed', 'skipped_passed', 'started_at',
                    'finished_at', 'error'):
            item.pop(key, None)
    state[account] = item
    save_json(QUEUE_STATE, state)


def update_account(old_account: str, account: str | None = None,
                   password: str | None = None, note: str | None = None,
                   classrooms=None) -> str:
    """修改队列里已有账号的信息；账号可以改名（队列状态一起搬过去）。

    password 为 None/空 时保留原密码；classrooms 为 None 时保留原课程设置。
    返回最终的账号字符串。
    """
    items = accounts()
    index = next((i for i, item in enumerate(items)
                  if item.get('account') == old_account), None)
    if index is None:
        raise ValueError(f'队列中没有账号 {old_account}')
    record = items[index]
    new_account = (account or old_account).strip() or old_account
    if new_account != old_account and any(
            item.get('account') == new_account for i, item in enumerate(items)
            if i != index):
        raise ValueError(f'账号 {new_account} 已存在')
    record['account'] = new_account
    if password:
        record['password'] = password
    if note is not None:
        record['note'] = note
    if classrooms is not None:
        cleaned = clean_classrooms(classrooms)
        if cleaned:
            record['classrooms'] = cleaned
        else:
            record.pop('classrooms', None)
    save_json(ACCOUNTS, items)
    if new_account != old_account:
        state = queue_state()
        if old_account in state:
            state[new_account] = state.pop(old_account)
            save_json(QUEUE_STATE, state)
    return new_account


def queue_rows() -> list[dict]:
    state = queue_state()
    out = []
    for item in accounts():
        account = str(item.get('account') or '')
        st = state.get(account, {}) or {}
        out.append({
            'account': account,
            'note': str(item.get('note') or ''),
            'password': str(item.get('password') or ''),
            'status': str(st.get('status') or 'pending'),
            'manual': bool(st.get('manual')),
            'submitted': st.get('submitted', 0),
            'failed': st.get('failed', 0),
            'skipped_passed': st.get('skipped_passed', 0),
            'error': str(st.get('error') or ''),
            'started_at': str(st.get('started_at') or ''),
            'finished_at': str(st.get('finished_at') or ''),
            'cooldown': cooldown_seconds(account),
            'classrooms': clean_classrooms(item.get('classrooms')),
        })
    return out


def queue_summary() -> dict:
    rows = queue_rows()
    counts = {'done': 0, 'failed': 0, 'pending': 0}
    for row in rows:
        counts[row['status'] if row['status'] in counts else 'pending'] += 1
    return {'total': len(rows), **counts}


def activate_account(account: str, password: str, *, clear_limit: bool = False) -> None:
    """切换 .env 里的登录账号，并清空上一个账号的 Token/Cookie/课堂地址。"""
    if not account or not password:
        raise ValueError('账号和密码都不能为空')
    if not ENV_PATH.exists() and ENV_EXAMPLE.exists():
        ENV_PATH.write_text(ENV_EXAMPLE.read_text(encoding='utf-8'), encoding='utf-8')
        try:
            ENV_PATH.chmod(0o600)
        except OSError:
            pass
    lines = ENV_PATH.read_text(encoding='utf-8').splitlines() if ENV_PATH.exists() else []
    lines = _set_env_key(lines, 'EDUCODER_LOGIN_ACCOUNT', account)
    lines = _set_env_key(lines, 'EDUCODER_LOGIN_PASSWORD', password)
    for key in SESSION_KEYS:
        lines = _set_env_key(lines, key, '')
    ENV_PATH.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    try:
        ENV_PATH.chmod(0o600)
    except OSError:
        pass
    os.environ['EDUCODER_LOGIN_ACCOUNT'] = account
    os.environ['EDUCODER_LOGIN_PASSWORD'] = password
    for key in SESSION_KEYS:
        os.environ[key] = ''
    if clear_limit:
        clear_login_limit(account)


def clear_login_limit(account: str | None = None) -> int:
    if not AUTH_DB.exists():
        return 0
    db = sqlite3.connect(AUTH_DB)
    try:
        with db:
            if account:
                key = hashlib.sha256(account.encode()).hexdigest()
                cur = db.execute('DELETE FROM login_attempts WHERE username=?', (key,))
            else:
                cur = db.execute('DELETE FROM login_attempts')
        return cur.rowcount
    except sqlite3.Error:
        return 0
    finally:
        db.close()


# --------------------------------------------------------------------------- #
# 课堂 / 作业
# --------------------------------------------------------------------------- #
def courses() -> list[dict]:
    data = load_json(COURSES_CACHE, [])
    return [c for c in data if isinstance(c, dict)] if isinstance(data, list) else []


def sync_times() -> dict:
    if not REMINDER_DB.exists():
        return {}
    try:
        db = sqlite3.connect(REMINDER_DB)
        try:
            rows = db.execute('SELECT username, synced_at FROM sync_state').fetchall()
        finally:
            db.close()
    except sqlite3.Error:
        return {}
    return {str(user): str(synced) for user, synced in rows}


def latest_username() -> str:
    times = sync_times()
    if not times:
        return ''
    return max(times.items(), key=lambda kv: kv[1])[0]


def classify(record: dict, now: datetime) -> str:
    """与 Homework.reminder_state 保持一致，按当前时间重新判断状态。"""
    if record.get('archived'):
        return 'archived'
    completed = record.get('completed')
    if completed is True:
        return 'completed'
    if completed is None:
        return 'unknown_completion'
    status = record.get('status') or []
    if isinstance(status, list) and '未发布' in status:
        return 'unpublished'
    publish_at = _parse_time(record.get('publish_at'))
    if publish_at is None:
        return 'unknown_publication'
    if publish_at > now:
        return 'unpublished'
    deadline = _parse_time(record.get('deadline'))
    if deadline is None:
        return 'no_deadline'
    if deadline <= now:
        return 'overdue'
    return 'pending'


def _parse_time(value) -> datetime | None:
    if not value or value in ('--', ''):
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING)
    return parsed.astimezone(BEIJING)


def format_deadline(value, now: datetime | None = None) -> str:
    parsed = _parse_time(value)
    if parsed is None:
        return '-'
    now = now or datetime.now(BEIJING)
    text = parsed.strftime('%m-%d %H:%M')
    return text if parsed.year == now.year else parsed.strftime('%Y-%m-%d %H:%M')


def minutes_left(deadline, now: datetime | None = None) -> float | None:
    """距离截止还有多少分钟（负数表示已逾期）。"""
    parsed = _parse_time(deadline)
    if parsed is None:
        return None
    now = now or datetime.now(BEIJING)
    return (parsed - now).total_seconds() / 60


def format_remaining(deadline, now: datetime | None = None) -> str:
    parsed = _parse_time(deadline)
    if parsed is None:
        return '-'
    now = now or datetime.now(BEIJING)
    delta = parsed - now
    total = int(delta.total_seconds())
    if total < 0:
        return '逾期 ' + _span(-total)
    return '剩 ' + _span(total)


def _span(seconds: int) -> str:
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f'{days}天{hours}小时'
    if hours:
        return f'{hours}小时{minutes}分'
    if minutes:
        return f'{minutes}分'
    return '<1分'


def human_age(iso_or_stamp: str | None, now: datetime | None = None) -> str:
    """把 ISO 时间或 'YYYY-mm-dd HH:MM:SS' 转成「N 分钟前」。"""
    if not iso_or_stamp:
        return '-'
    parsed = _parse_time(iso_or_stamp)
    if parsed is None:
        try:
            parsed = datetime.strptime(iso_or_stamp, '%Y-%m-%d %H:%M:%S').replace(tzinfo=BEIJING)
        except ValueError:
            return str(iso_or_stamp)
    now = now or datetime.now(BEIJING)
    seconds = int((now - parsed).total_seconds())
    if seconds < 0:
        return _span(-seconds) + '后'
    if seconds < 60:
        return f'{seconds} 秒前'
    if seconds < 3600:
        return f'{seconds // 60} 分钟前'
    if seconds < 86400:
        return f'{seconds // 3600} 小时前'
    return f'{seconds // 86400} 天前'


def _record_rows() -> tuple[str, list[dict]]:
    """优先读 SQLite（按最近同步的账号），缺失时回退到 homeworks.json。"""
    username = latest_username()
    rows: list[dict] = []
    db_available = False
    if REMINDER_DB.exists():
        try:
            db = sqlite3.connect(REMINDER_DB)
            try:
                cur = db.execute(
                    'SELECT username, payload FROM homeworks WHERE present=1')
                for user, payload in cur.fetchall():
                    try:
                        record = json.loads(payload)
                    except (TypeError, ValueError):
                        continue
                    record['_username'] = user
                    rows.append(record)
                db_available = True
            finally:
                db.close()
        except sqlite3.Error:
            rows = []
            db_available = False
    # 数据库存在但为空时表示确实没有作业，不用旧 JSON 覆盖
    if not db_available:
        data = load_json(HOMEWORKS_JSON, {})
        for record in data.get('homeworks', []) if isinstance(data, dict) else []:
            if isinstance(record, dict):
                record['_username'] = record.get('_username', '')
                rows.append(record)
        username = rows[0]['_username'] if rows and rows[0]['_username'] else username
    if username:
        rows = [r for r in rows if r.get('_username') in ('', username)]
    return username, rows


def homework_rows(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(BEIJING)
    username, records = _record_rows()
    out = []
    for record in records:
        state = classify(record, now)
        deadline = record.get('deadline')
        out.append({
            'username': username,
            'course_id': record.get('course_id', ''),
            'course_name': record.get('course_name', ''),
            'kind': record.get('kind', 0),
            'kind_name': KIND_NAMES.get(record.get('kind'), '其他'),
            'name': record.get('name', ''),
            'deadline': deadline,
            'deadline_text': format_deadline(deadline, now),
            'state': state,
            'state_label': STATE_LABELS.get(state, state),
            'remaining': format_remaining(deadline, now) if state != 'completed' else '-',
            'url': record.get('url', ''),
        })
    out.sort(key=_sort_key)
    return out


def _sort_key(row: dict) -> tuple:
    order = STATE_ORDER.get(row['state'], 9)
    deadline = _parse_time(row.get('deadline'))
    if row['state'] in ('pending', 'overdue') and deadline is not None:
        return (order, deadline.isoformat())
    return (order, '9999-12-31')


def summary(rows: list[dict], now: datetime | None = None) -> dict:
    now = now or datetime.now(BEIJING)
    counts: dict[str, int] = {key: 0 for key in STATE_LABELS}
    urgent_24h = urgent_1h = 0
    for row in rows:
        counts[row['state']] = counts.get(row['state'], 0) + 1
        if row['state'] != 'pending':
            continue
        deadline = _parse_time(row.get('deadline'))
        if deadline is None:
            continue
        seconds = (deadline - now).total_seconds()
        if 0 < seconds <= 3600:
            urgent_1h += 1
        if 0 < seconds <= 86400:
            urgent_24h += 1
    return {'counts': counts, 'urgent_24h': urgent_24h, 'urgent_1h': urgent_1h,
            'total': len(rows)}


# --------------------------------------------------------------------------- #
# 日志
# --------------------------------------------------------------------------- #
def display_path(path: Path) -> str:
    """项目内文件显示相对路径，临时/外部路径原样显示。"""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def log_tail(path: Path, lines: int = 300) -> list[str]:
    if not path.exists():
        return []
    try:
        content = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return []
    return content[-lines:]


def append_tui_log(message: str) -> None:
    try:
        TUI_LOG.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with TUI_LOG.open('a', encoding='utf-8') as handle:
            handle.write(f'{datetime.now(BEIJING).strftime("%Y-%m-%d %H:%M:%S")} {message}\n')
    except OSError:
        pass


def unfinished_report() -> dict:
    """读取一键提交的收尾校验报告（没有就是空）。"""
    data = load_json(UNFINISHED_JSON, {})
    return data if isinstance(data, dict) else {}


def summarize_feeds(now: datetime | None = None) -> dict:
    """给概览页用的汇总信息。"""
    now = now or datetime.now(BEIJING)
    rows = homework_rows(now)
    return {
        'session': session(),
        'queue': queue_summary(),
        'homeworks': summary(rows, now),
        'rows': rows,
        'courses': courses(),
        'sync_times': sync_times(),
        'latest_username': latest_username(),
        'unfinished': unfinished_report(),
        'now': now,
    }
