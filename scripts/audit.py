"""体检：列出本学期所有课堂里「尚未通过」的关卡。

用法：
  uv run python scripts/audit.py            # 全部课堂
  uv run python scripts/audit.py --classroom 2i6ng7vp
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from educoder_reminder.client import open_client
from educoder_reminder.courses import fetch_courses
from educoder_reminder.errors import CollectionError
from educoder_reminder.submit import (
    fetch_homework_rows, resolve_entry, walk_prev_to_head,
)
from educoder_reminder.submit_all import COURSE_CUTOFF


async def audit_classroom(client, course):
    code = course.identifier
    print(f'\n===== {course.name}（{code}）=====')
    try:
        rows = await fetch_homework_rows(client, code)
    except CollectionError as exc:
        print(f'  ✗ 无法读取实验列表：{exc}')
        return 0, 0
    total_unpassed = total = 0
    for hw in rows:
        name = hw.get('name') or ''
        finished = hw.get('shixun_finished_status') == 1
        entry = await resolve_entry(client, hw.get('shixun_identifier'), hw.get('homework_id'))
        if not entry:
            print(f'  ? {name}：无法解析入口（可能未开始）')
            continue
        ordered, cache = await walk_prev_to_head(client, entry)
        # 沿 next_game 走完整条链
        queue, seen, levels = list(ordered), set(), []
        while queue:
            gid = queue.pop(0)
            if gid in seen:
                continue
            seen.add(gid)
            d = cache.get(gid) or await client.get(f'/api/tasks/{gid}.json',
                                                   {}, strict_status=False)
            ch = d.get('challenge') or {}
            g = d.get('game') or {}
            levels.append((ch.get('subject') or '', g.get('status')))
            nxt = d.get('next_game')
            if nxt and str(nxt) not in seen:
                queue.append(str(nxt))
        total += len(levels)
        unpassed = [s for s, st in levels if st != 2]
        total_unpassed += len(unpassed)
        flag = '✓' if not unpassed else '✗'
        print(f'  {flag} {name}（平台标记完成={finished}，关卡 {len(levels) - len(unpassed)}/{len(levels)}）')
        for s in unpassed:
            print(f'      - 未通过：{s}')
    print(f'  —— 本课堂：{total - total_unpassed}/{total} 关卡通过')
    return total - total_unpassed, total


async def main():
    parser = argparse.ArgumentParser(description='列出尚未通过的关卡。')
    parser.add_argument('--classroom', default=None, help='只检查指定课堂 code')
    parser.add_argument('--all', action='store_true', help='包含旧学期课堂')
    args = parser.parse_args()
    async with open_client() as client:
        courses = await fetch_courses(client)
        if not args.all:
            courses = [c for c in courses if (c.created_at or '') >= COURSE_CUTOFF]
        passed_all = total_all = 0
        for course in courses:
            if args.classroom and course.identifier != args.classroom:
                continue
            p, t = await audit_classroom(client, course)
            passed_all += p
            total_all += t
        print(f'\n===== 总计：{passed_all}/{total_all} 关卡通过 =====')


if __name__ == '__main__':
    asyncio.run(main())
