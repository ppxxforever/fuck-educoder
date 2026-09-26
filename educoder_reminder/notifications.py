"""Durable reminder selection, merging, quotas and retry bookkeeping."""
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from .homeworks import BEIJING, Homework, KINDS
from .serverchan import PushError, receiver_id, send


@dataclass(frozen=True)
class Notice:
    event: str
    homework: Homework
    stage: str


def connect(path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    db = sqlite3.connect(path)
    db.executescript('''
        CREATE TABLE IF NOT EXISTS push_attempts (
            id INTEGER PRIMARY KEY, receiver TEXT NOT NULL, day TEXT NOT NULL,
            attempted_at TEXT NOT NULL, status TEXT NOT NULL, error TEXT
        );
        CREATE TABLE IF NOT EXISTS push_events (
            receiver TEXT NOT NULL, event TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            state TEXT NOT NULL, last_attempt TEXT, attempt_id INTEGER,
            PRIMARY KEY(receiver, event)
        );
    ''')
    return db


def select_notices(db, username, receiver, now, undated_mode):
    if undated_mode not in ('once', 'daily'):
        raise ValueError('请设置 UNDATED_REMINDER_MODE=once 或 daily。')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='homeworks'").fetchone():
        return []
    rows = db.execute('''SELECT h.payload,
        (SELECT count(*) FROM deadline_changes d WHERE d.username=h.username
         AND d.course_id=h.course_id AND d.kind=h.kind AND d.homework_id=h.homework_id)
        FROM homeworks h WHERE h.username=? AND h.present=1''', (username,)).fetchall()
    result = []
    for payload, revision in rows:
        item = Homework(**json.loads(payload))
        state = item.reminder_state(now)
        if state == 'no_deadline':
            stage = 'undated'
            bucket = now.astimezone(BEIJING).date().isoformat() if undated_mode == 'daily' else 'once'
        elif state == 'pending':
            remaining = datetime.fromisoformat(item.deadline) - now
            if remaining > timedelta(hours=24):
                continue
            # Within one hour only the urgent stage is selected, never both.
            stage = '1h' if remaining <= timedelta(hours=1) else '24h'
            bucket = ''
        else:
            continue
        event = hashlib.sha256(json.dumps([username, item.course_id, item.kind, item.id,
            item.deadline, revision, stage, bucket], ensure_ascii=False).encode()).hexdigest()
        previous = db.execute('SELECT state,attempts,last_attempt FROM push_events WHERE receiver=? AND event=?',
                              (receiver, event)).fetchone()
        if previous:
            status, attempts, last = previous
            if status in ('sent', 'skipped') or attempts >= 3:
                continue
            delay = timedelta(minutes=5 if attempts == 1 else 30)
            if last and now < datetime.fromisoformat(last) + delay:
                continue
        result.append(Notice(event, item, stage))
    return sorted(result, key=lambda n: ({'1h': 0, '24h': 1, 'undated': 2}[n.stage], n.homework.deadline or '', n.homework.id))


def escape(text):
    return re.sub(r'([\\`*_{}\[\]()#+!|<>])', r'\\\1', ' '.join(text.split()))


def render(notices, now):
    title = f'作业提醒：{len(notices)} 项待处理'
    lines = [f'北京时间：{now.astimezone(BEIJING):%Y-%m-%d %H:%M}', '']
    for notice in notices:
        item = notice.homework
        label = {'1h': '不足或剩余 1 小时', '24h': '24 小时内截止', 'undated': '未设置截止时间'}[notice.stage]
        lines.append(f'### {label} · {escape(item.course_name)}')
        lines.append(f'{KINDS[item.kind][0]}：{escape(item.name)}')
        if item.deadline:
            lines.append(f'截止：{datetime.fromisoformat(item.deadline).astimezone(BEIJING):%Y-%m-%d %H:%M:%S}')
        else:
            lines.append('请查看课程要求，确认提交时间。')
        lines.append(f'[打开课堂作业列表]({item.url})')
    return title, '\n\n'.join(lines)


def quota_remaining(db, receiver, now, daily_limit):
    day = now.astimezone(BEIJING).date().isoformat()
    used = db.execute('SELECT count(*) FROM push_attempts WHERE receiver=? AND day=?', (receiver, day)).fetchone()[0]
    return max(0, daily_limit - used)


async def deliver(db, key, notices, now, daily_limit, *, transport=send, test=False, test_message=None):
    if test and notices:
        raise ValueError('测试发送不能包含正式提醒事件。')
    if test_message is not None and not test:
        raise ValueError('自定义测试内容必须使用测试模式。')
    receiver = receiver_id(key)
    if not quota_remaining(db, receiver, now, daily_limit):
        return 'quota_exhausted'
    title, body = ('作业提醒工具 · 测试通知', '推送通道已连接。此消息仅用于测试，不代表有作业即将截止。') if test else render(notices, now)
    if test_message is not None:
        title, body = test_message
    if not test and not notices:
        return 'nothing_due'
    if len(body.encode()) > 30000:
        raise PushError('合并消息超过本地长度限制，请减少单批数量；未标记为已发送。')
    with db:
        attempt = db.execute('INSERT INTO push_attempts(receiver,day,attempted_at,status) VALUES (?,?,?,?)',
            (receiver, now.astimezone(BEIJING).date().isoformat(), now.isoformat(), 'inflight')).lastrowid
        for notice in notices:
            db.execute('''INSERT INTO push_events(receiver,event,attempts,state,last_attempt,attempt_id)
                VALUES (?,?,1,'inflight',?,?) ON CONFLICT(receiver,event) DO UPDATE SET
                attempts=attempts+1,state='inflight',last_attempt=excluded.last_attempt,attempt_id=excluded.attempt_id''',
                (receiver, notice.event, now.isoformat(), attempt))
    try:
        await transport(key, title, body)
    except PushError as exc:
        with db:
            db.execute("UPDATE push_attempts SET status='failed',error=? WHERE id=?", (str(exc), attempt))
            db.execute("UPDATE push_events SET state='failed' WHERE attempt_id=?", (attempt,))
        raise
    with db:
        db.execute("UPDATE push_attempts SET status='sent' WHERE id=?", (attempt,))
        db.execute("UPDATE push_events SET state='sent' WHERE attempt_id=?", (attempt,))
    return 'sent'
