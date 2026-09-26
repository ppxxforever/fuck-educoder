"""Read only the configured user's ongoing classroom list."""
import asyncio
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from playwright.async_api import Error as PlaywrightError
from .client import open_client
from .errors import CollectionError


@dataclass(frozen=True)
class Course:
    id: int
    name: str
    identifier: str
    url: str
    can_visit: bool


def parse_page(data):
    if not isinstance(data, dict):
        raise CollectionError('接口返回结构异常。')
    if data.get('status') not in (None, 0, 200):
        raise CollectionError(f"接口拒绝请求（状态 {data.get('status')}），请检查认证及时间戳/签名。")
    count, rows = data.get('count'), data.get('courses')
    if type(count) is not int or count < 0 or not isinstance(rows, list):
        raise CollectionError('接口缺少有效的 count 或 courses，拒绝视为空课堂。')
    parsed = []
    ids = []
    for row in rows:
        if not isinstance(row, dict) or type(row.get('id')) is not int:
            raise CollectionError('课堂 ID 格式异常。')
        ids.append(row['id'])
        if type(row.get('is_end')) is not bool:
            raise CollectionError('课堂缺少明确的结束状态。')
        if row['is_end']:
            continue
        path = row.get('first_category_url', '')
        match = re.fullmatch(r'/classrooms/([A-Za-z0-9_-]+)/[A-Za-z0-9_/-]+', path)
        if not match or not isinstance(row.get('name'), str):
            raise CollectionError('课堂名称或链接格式异常。')
        parsed.append(Course(row['id'], row['name'], match[1],
                             'https://www.educoder.net' + path,
                             row.get('can_visited') is True))
    return count, ids, parsed


async def collect(fetch, per_page=15):
    seen = set()
    courses = {}
    expected = None
    for page in range(1, 1001):
        count, ids, parsed = parse_page(await fetch(page, per_page))
        if expected is not None and count != expected:
            raise CollectionError('采集期间课堂数量发生变化，请重试；未保存不完整结果。')
        expected = count
        if not ids:
            if len(seen) == count:
                return list(courses.values())
            raise CollectionError('分页提前结束，未保存不完整结果。')
        if len(ids) != len(set(ids)) or seen.intersection(ids):
            raise CollectionError('分页出现重复课堂，请重试。')
        seen.update(ids)
        courses.update((course.id, course) for course in parsed)
        if len(seen) == count:
            return list(courses.values())
        if len(seen) > count:
            raise CollectionError('返回课堂数超过 count。')
    raise CollectionError('超出分页安全上限。')


async def fetch_courses(client):
    async def fetch(page, per_page):
        return await client.get(f'/api/users/{client.username}/courses.json', {
            'category': '', 'status': 'processing', 'page': page,
            'per_page': per_page, 'sort_by': 'updated_at',
            'sort_direction': 'desc', 'username': client.username,
        })
    return await collect(fetch)


async def crawl():
    async with open_client() as client:
        return await fetch_courses(client)


def main():
    try:
        courses = asyncio.run(crawl())
        directory = Path('data')
        directory.mkdir(mode=0o700, exist_ok=True)
        target = directory / 'courses.json'
        temp = directory / 'courses.json.tmp'
        temp.write_text(json.dumps([asdict(c) for c in courses], ensure_ascii=False, indent=2) + '\n')
        temp.chmod(0o600)
        temp.replace(target)
        print(f'已获取 {len(courses)} 个进行中课堂，保存到 {target}')
        for course in courses:
            print(f'{course.id}\t{course.name}\t{course.identifier}')
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
    except PlaywrightError:
        raise SystemExit('Playwright 请求失败，请检查网络；认证详情不写入日志。') from None


if __name__ == '__main__':
    main()
