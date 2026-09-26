"""Collect both homework types only within freshly discovered classrooms."""
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.async_api import Error as PlaywrightError

from .client import open_client
from .courses import Course, fetch_courses
from .errors import CollectionError

BEIJING = ZoneInfo('Asia/Shanghai')
KINDS = {4: ('课堂实验', 'shixun_homework'), 1: ('图文作业', 'common_homework')}


def parse_time(value):
    if value in (None, '', '--'):
        return None
    if not isinstance(value, str):
        raise CollectionError('作业时间格式异常。')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise CollectionError('无法解析作业时间，不猜测截止日期。') from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BEIJING)
    return parsed.astimezone(BEIJING).isoformat()


@dataclass(frozen=True)
class Homework:
    course_id: str
    course_name: str
    id: int
    kind: int
    name: str
    deadline: str | None
    publish_at: str | None
    archived: bool
    completed: bool | None
    status: list[str]
    url: str

    def reminder_state(self, now):
        if now.tzinfo is None:
            raise ValueError('now must be timezone-aware')
        if self.archived:
            return 'archived'
        if self.completed is True:
            return 'completed'
        if self.completed is None:
            return 'unknown_completion'
        if '未发布' in self.status:
            return 'unpublished'
        if self.publish_at is None:
            return 'unknown_publication'
        if datetime.fromisoformat(self.publish_at) > now:
            return 'unpublished'
        if self.deadline is None:
            return 'no_deadline'  # separately notify, as requested
        if datetime.fromisoformat(self.deadline) <= now:
            return 'overdue'
        return 'pending'


def read_deadline(row):
    # Prefer the precise personal/group deadline, never the late-submission time.
    value = row.get('end_time_s')
    if value in (None, '', '--'):
        value = row.get('end_time')
    return parse_time(value)


def parse_homework(row, course, kind):
    if not isinstance(row, dict) or type(row.get('homework_id')) is not int:
        raise CollectionError('作业 ID 格式异常。')
    if not isinstance(row.get('name'), str) or not row['name'].strip():
        raise CollectionError('作业名称缺失。')
    if type(row.get('is_archive')) is not bool:
        raise CollectionError('作业归档状态缺失。')
    status = row.get('status')
    if not isinstance(status, list) or any(not isinstance(s, str) for s in status):
        raise CollectionError('作业发布状态格式异常。')
    completed = None
    if kind == 4:
        value = row.get('shixun_finished_status')
        if type(value) is int and value in (0, 1):
            completed = value == 1
    else:
        value = row.get('un_commit_work')
        if type(value) is bool:
            completed = not value
    return Homework(
        course.identifier, course.name, row['homework_id'], kind, row['name'],
        read_deadline(row), parse_time(row.get('publish_time')),
        row['is_archive'], completed, status,
        f'https://www.educoder.net/classrooms/{course.identifier}/{KINDS[kind][1]}',
    )


async def collect_homeworks(client, course: Course, kind: int, allowed, limit=20, *, now=None):
    now = datetime.now(BEIJING) if now is None else now
    if now.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    cutoff = now - timedelta(days=5)
    if course.identifier not in allowed:
        raise CollectionError('拒绝访问本次已加入课堂清单以外的课堂。')
    if not course.can_visit:
        raise CollectionError('课堂当前不可访问，本次同步未保存。')
    if kind not in KINDS:
        raise CollectionError('仅支持课堂实验和图文作业。')
    seen = set()
    result = []
    expected = None
    for page in range(1, 1001):
        data = await client.get(f'/api/courses/{course.identifier}/homework_commons.json', {
            'limit': limit, 'page': page, 'status': 0, 'id': course.identifier,
            'type': kind, 'order': 0,
        })
        if data.get('homework_type') != kind or data.get('is_end') is not False:
            raise CollectionError('课堂状态或作业类型变化，请重新同步。')
        count, rows = data.get('query_total_count'), data.get('homeworks')
        if type(count) is not int or count < 0 or not isinstance(rows, list):
            raise CollectionError('作业接口缺少有效分页字段。')
        if expected is not None and expected != count:
            raise CollectionError('分页期间作业数量发生变化，请重试。')
        expected = count
        # The list endpoint includes archived rows even in the expired tab.
        # Count their IDs for pagination, but never parse/store their contents.
        ids = []
        parsed = []
        for row in rows:
            if not isinstance(row, dict) or type(row.get('homework_id')) is not int:
                raise CollectionError('作业 ID 格式异常。')
            if type(row.get('is_archive')) is not bool:
                raise CollectionError('作业归档状态缺失。')
            ids.append(row['homework_id'])
            if row['is_archive']:
                continue
            deadline = read_deadline(row)
            if deadline is not None and datetime.fromisoformat(deadline) < cutoff:
                continue
            parsed.append(parse_homework(row, course, kind))
        if len(ids) != len(set(ids)) or seen.intersection(ids):
            raise CollectionError('作业分页重复，拒绝保存不完整结果。')
        seen.update(ids)
        result.extend(parsed)
        if len(seen) == count:
            return result
        if not rows or len(seen) > count:
            raise CollectionError('作业分页数量不一致，拒绝保存不完整结果。')
        await asyncio.sleep(0.2)
    raise CollectionError('作业分页超出安全上限。')


async def crawl_homeworks():
    now = datetime.now(BEIJING)
    async with open_client() as client:
        courses = await fetch_courses(client)
        allowed = frozenset(course.identifier for course in courses)
        result = []
        for course in courses:
            for kind in KINDS:
                result.extend(await collect_homeworks(client, course, kind, allowed, now=now))
                await asyncio.sleep(0.2)
        return client.username, courses, result


def main():
    from .storage import save_snapshot
    try:
        username, courses, homeworks = asyncio.run(crawl_homeworks())
        now = datetime.now(BEIJING)
        path = Path('data/reminder.sqlite3')
        save_snapshot(path, username, homeworks, now)
        rows = [{**asdict(item), 'kind_name': KINDS[item.kind][0],
                 'reminder_state': item.reminder_state(now)} for item in homeworks]
        counts = {}
        for row in rows:
            state = row['reminder_state']
            counts[state] = counts.get(state, 0) + 1
        target = Path('data/homeworks.json')
        temp = target.with_suffix('.json.tmp')
        temp.write_text(json.dumps({'synced_at': now.isoformat(), 'counts': counts,
                                    'homeworks': rows}, ensure_ascii=False, indent=2) + '\n')
        temp.chmod(0o600)
        temp.replace(target)
        print(f'已同步 {len(courses)} 个课堂、{len(homeworks)} 项作业 → {path}')
        print(json.dumps(counts, ensure_ascii=False))
        for item in homeworks:
            if item.reminder_state(now) in ('pending', 'no_deadline'):
                print(f'{item.course_name} | {KINDS[item.kind][0]} | {item.name} | {item.deadline or "无截止时间（需单独提醒）"}')
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
    except PlaywrightError:
        raise SystemExit('Playwright 请求失败，请检查网络；认证详情不写入日志。') from None


if __name__ == '__main__':
    main()
