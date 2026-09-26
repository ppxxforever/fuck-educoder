"""Run with preview, once, run, or test. Preview never sends or crawls."""
import argparse
import asyncio
import fcntl
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

from .client import load_settings, open_client
from .courses import fetch_courses
from .errors import CollectionError
from .homeworks import BEIJING, KINDS, collect_homeworks, crawl_homeworks
from .notifications import connect, deliver, escape, quota_remaining, receiver_id, render, select_notices
from .serverchan import PushError, endpoint
from .storage import save_snapshot

ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / 'data/reminder.sqlite3'


@contextmanager
def process_lock():
    path = ROOT / 'data/reminder.lock'
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise CollectionError('已有提醒进程运行，请勿重复启动。') from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def options():
    username, _ = load_settings()
    key = os.environ.get('SERVERCHAN_SENDKEY', '').strip()
    provider, _ = endpoint(key)
    mode = os.environ.get('UNDATED_REMINDER_MODE', '').strip()
    policy = os.environ.get('QUOTA_POLICY', '').strip()
    if mode not in ('once', 'daily'):
        raise CollectionError('请确认无截止时间提醒频率，并设置 UNDATED_REMINDER_MODE=once 或 daily。')
    if policy not in ('defer', 'skip'):
        raise CollectionError('请设置 QUOTA_POLICY=defer（次日重判补发）或 skip（跳过当前阶段）。')
    try:
        limit = int(os.environ.get('SERVERCHAN_DAILY_LIMIT', '5'))
        sync_hours = float(os.environ.get('SYNC_INTERVAL_HOURS', '6'))
        check_seconds = int(os.environ.get('REMINDER_CHECK_INTERVAL_SECONDS', '60'))
    except ValueError:
        raise CollectionError('推送额度或运行间隔配置无效。') from None
    if limit < 1 or sync_hours <= 0 or check_seconds < 1:
        raise CollectionError('额度和间隔必须为正数。')
    if provider == 'Turbo' and limit > 5:
        raise CollectionError('当前只使用免费 Turbo，日发送上限不能超过 5 次。')
    return username, key, mode, policy, limit, sync_hours, check_seconds


async def recheck(username, notices):
    """Refresh only due course/type groups, after refreshing joined classrooms."""
    scopes = {(n.homework.course_id, n.homework.kind) for n in notices}
    async with open_client() as client:
        if client.username != username:
            raise CollectionError('账号配置已变化，请重启提醒进程。')
        courses = {c.identifier: c for c in await fetch_courses(client)}
        result = []
        now = datetime.now(BEIJING)
        for course_id, kind in sorted(scopes):
            if course_id in courses:
                result.extend(await collect_homeworks(client, courses[course_id], kind, courses, now=now))
    save_snapshot(DATABASE, username, result, now, scopes=scopes)
    return scopes


async def tick(config, *, preview=False):
    username, key, mode, policy, limit, sync_hours, _ = config
    receiver = receiver_id(key)
    db = connect(DATABASE)
    try:
        now = datetime.now(BEIJING)
        if not preview:
            table = db.execute("SELECT 1 FROM sqlite_master WHERE name='sync_state'").fetchone()
            last = db.execute('SELECT synced_at FROM sync_state WHERE username=?', (username,)).fetchone() if table else None
            if not last or now - datetime.fromisoformat(last[0]) >= timedelta(hours=sync_hours):
                actual_user, courses, homeworks = await crawl_homeworks()
                username = actual_user
                save_snapshot(DATABASE, username, homeworks, datetime.now(BEIJING))
                print(f'同步完成：{len(courses)} 个课堂，{len(homeworks)} 项作业。', flush=True)
        now = datetime.now(BEIJING)
        notices = select_notices(db, username, receiver, now, mode)
        if preview:
            print(f'本地预览：{len(notices)} 项到达提醒窗口；未联网、未发送。')
            if notices:
                title, body = render(notices, now)
                print(title + '\n' + body)
            return 'preview'
        if not notices:
            return 'nothing_due'
        if not quota_remaining(db, receiver, now, limit):
            if policy == 'skip':
                with db:
                    db.executemany('''INSERT INTO push_events(receiver,event,state) VALUES (?,?,'skipped')
                        ON CONFLICT(receiver,event) DO UPDATE SET state='skipped' ''',
                        [(receiver, n.event) for n in notices])
            return 'quota_exhausted'
        scopes = await recheck(username, notices)
        now = datetime.now(BEIJING)
        fresh = [n for n in select_notices(db, username, receiver, now, mode)
                 if (n.homework.course_id, n.homework.kind) in scopes]
        # Merge as much as fits; unselected events remain unsent for the next tick.
        batch = []
        for notice in fresh:
            if len(render(batch + [notice], now)[1].encode()) > 30000:
                break
            batch.append(notice)
        if fresh and not batch:
            raise PushError('单项通知内容过长，未发送；请检查作业名称。')
        return await deliver(db, key, batch, now, limit)
    finally:
        db.close()


def upcoming_message(homeworks, now):
    until = now + timedelta(days=5)
    selected = sorted([h for h in homeworks if h.reminder_state(now) == 'pending'
                       and now < datetime.fromisoformat(h.deadline) <= until],
                      key=lambda h: (h.deadline, h.course_id, h.id))
    title = f'作业测试汇总：5 天内截止 {len(selected)} 项'
    lines = [f'北京时间：{now:%Y-%m-%d %H:%M}', f'范围：现在起至 {until:%Y-%m-%d %H:%M}。']
    for item in selected:
        lines.extend([f'### {escape(item.course_name)}', f'{KINDS[item.kind][0]}：{escape(item.name)}',
                      f'截止：{datetime.fromisoformat(item.deadline).astimezone(BEIJING):%Y-%m-%d %H:%M:%S}',
                      f'[打开课堂作业列表]({item.url})'])
    if not selected:
        lines.append('未来 5 天内没有未完成且未归档的到期作业。')
    lines.append('这是手动测试汇总，不影响正式的 24 小时和 1 小时提醒。')
    return title, '\n\n'.join(lines)


async def test_upcoming(config):
    username, key, _, _, limit, _, _ = config
    db = connect(DATABASE)
    try:
        if not quota_remaining(db, receiver_id(key), datetime.now(BEIJING), limit):
            print('本地今日额度已用尽，未发送。')
            return
        actual, _, homeworks = await crawl_homeworks()
        username = actual
        now = datetime.now(BEIJING)
        save_snapshot(DATABASE, username, homeworks, now)
        message = upcoming_message(homeworks, now)
        result = await deliver(db, key, [], now, limit, test=True, test_message=message)
        print(message[0])
        print('汇总已被 Server 酱接受，请查看 App。' if result == 'sent' else '本地今日额度已用尽，未发送。')
    finally:
        db.close()


async def execute(command):
    if command == 'auth-check':
        async with open_client() as client:
            actual = client.username
        print(f'Educoder 登录有效，当前课堂地址：https://www.educoder.net/users/{actual}/classrooms')
        return
    if command == 'test':
        load_settings()
        key = os.environ.get('SERVERCHAN_SENDKEY', '').strip()
        endpoint(key)
        db = connect(DATABASE)
        try:
            result = await deliver(db, key, [], datetime.now(BEIJING), 5, test=True)
            print('测试通知已被 Server 酱接受，请在接收端确认。' if result == 'sent' else '本地今日额度已用尽，未发送测试通知。')
        finally:
            db.close()
        return
    config = options()
    if command == 'test-upcoming':
        await test_upcoming(config)
        return
    if command == 'check':
        print(f'配置有效：{endpoint(config[1])[0]}；同步间隔 {config[-2]:g} 小时；检查间隔 {config[-1]} 秒。')
        return
    if command == 'preview':
        await tick(config, preview=True)
        return
    if command == 'run':
        print(f'定时任务已启动：每 {config[-2]:g} 小时同步，每 {config[-1]} 秒检查提醒。', flush=True)
    while True:
        config = options()
        started = asyncio.get_running_loop().time()
        try:
            result = await tick(config)
            if result != 'nothing_due':
                print(f'{datetime.now(BEIJING):%Y-%m-%d %H:%M:%S} 提醒检查：{result}', flush=True)
        except (CollectionError, PushError, PlaywrightError) as exc:
            if command != 'run':
                raise
            # Never emit Playwright request URLs/headers.
            print(str(exc) if not isinstance(exc, PlaywrightError) else '采集网络请求失败，下次检查重试。', flush=True)
        if command != 'run':
            return
        # Avoid adding the API request duration to every polling interval.
        elapsed = asyncio.get_running_loop().time() - started
        await asyncio.sleep(max(1, config[-1] - elapsed))


def main():
    parser = argparse.ArgumentParser(description='check 配置检查；auth-check 验证登录并按需恢复；preview 本地预览；once 检查一次；run 持续运行；test 推送测试')
    parser.add_argument('command', choices=['check', 'auth-check', 'preview', 'once', 'run', 'test', 'test-upcoming'])
    args = parser.parse_args()
    try:
        if args.command == 'check':
            asyncio.run(execute(args.command))
        else:
            with process_lock():
                asyncio.run(execute(args.command))
    except (CollectionError, PushError) as exc:
        raise SystemExit(str(exc)) from None
    except PlaywrightError:
        raise SystemExit('采集网络请求失败，未发送提醒。') from None
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
