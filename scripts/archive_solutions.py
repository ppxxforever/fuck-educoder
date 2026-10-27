"""只读归档：把已完成（status==2）关卡的本地答案存进 solutions/。

与 attempts/ 分开：
  - attempts/  存未通过的尝试，改完可重交；
  - solutions/ 存平台确认已通关的答案，作为可复用题库。

用法：
  uv run python scripts/archive_solutions.py --no-archive            # 只列出
  uv run python scripts/archive_solutions.py --classroom 2i6ng7vp    # 归档
  uv run python scripts/archive_solutions.py --classroom 2i6ng7vp --cleanup-attempts
"""
import argparse
import asyncio
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from educoder_reminder import attempts, solutions
from educoder_reminder.answer_sources import answer_for_level
from educoder_reminder.client import open_client
from educoder_reminder.courses import fetch_courses
from educoder_reminder.errors import CollectionError
from educoder_reminder.submit import (
    DEFAULT_ANSWERS, _game_view, fetch_homework_rows, load_answers, resolve_entry,
    walk_prev_to_head,
)
from educoder_reminder.submit_all import COURSE_CUTOFF, course_matches, split_filters


async def archive_classroom(client, course, answers, *, write=True, cleanup_attempts=False):
    code = course.identifier
    print(f'\n===== {course.name}（{code}）=====')
    try:
        rows = await fetch_homework_rows(client, code)
    except CollectionError as exc:
        print(f'  ✗ 读取实验列表失败：{exc}')
        return 0, 0

    completed = saved = 0
    for hw in rows:
        hw_name = hw.get('name') or ''
        try:
            entry = await resolve_entry(client, hw.get('shixun_identifier'),
                                        hw.get('homework_id'))
            if not entry:
                continue
            ordered, cache = await walk_prev_to_head(client, entry)
        except CollectionError:
            continue

        queue, seen, levels = list(ordered), set(), []
        while queue:
            gid = queue.pop(0)
            if gid in seen:
                continue
            seen.add(gid)
            detail = cache.get(gid)
            if detail is None:
                try:
                    detail = await client.get(f'/api/tasks/{gid}.json', {},
                                              strict_status=False)
                except CollectionError:
                    continue
            cache[gid] = detail
            levels.append((gid, detail))
            nxt = detail.get('next_game')
            if nxt and str(nxt) not in seen:
                queue.append(str(nxt))

        for gid, detail in levels:
            game = _game_view(detail)
            if game.get('status') != 2:
                continue
            completed += 1
            challenge = detail.get('challenge') or {}
            subject = (challenge.get('subject') or '').strip() or gid
            content, kind, local_path, source = answer_for_level(
                detail, answers, code, course.name, hw_name)
            if not content:
                print(f'  · {hw_name} / {subject}：已完成，但本地没有答案可归档')
                continue
            label = '已归档' if write else '可归档'
            if write:
                try:
                    target = solutions.save_solution(
                        hw_name, subject, content, path=local_path, gid=gid,
                        kind=kind or '', classroom=code, source=source)
                    saved += 1
                    if cleanup_attempts:
                        level_attempts = attempts.level_dir(hw_name, subject)
                        if level_attempts.is_dir():
                            shutil.rmtree(level_attempts, ignore_errors=True)
                    print(f'  ✓ {hw_name} / {subject}（{gid}）：{label} '
                          f'{target.relative_to(ROOT)}  来源={source}')
                except Exception as exc:
                    print(f'  ✗ {hw_name} / {subject}：保存失败：{exc}')
            else:
                print(f'  ✓ {hw_name} / {subject}（{gid}）：{label}  来源={source}')
    print(f'  —— 已完成 {completed} 关；本次归档 {saved} 个')
    return completed, saved


async def main():
    parser = argparse.ArgumentParser(description='把已通关关卡的答案归档到 solutions/（只读）')
    parser.add_argument('--classroom', action='append', default=None,
                        help='只处理指定课堂：code 或名称，可多次/逗号分隔')
    parser.add_argument('--answers', default=str(DEFAULT_ANSWERS), help='answers.json 路径')
    parser.add_argument('--no-archive', action='store_true', help='只列出，不写 solutions/')
    parser.add_argument('--cleanup-attempts', action='store_true',
                        help='归档后删除 attempts/ 里对应关卡的旧失败存档')
    args = parser.parse_args()

    answers = load_answers(Path(args.answers))
    filters = split_filters(args.classroom)
    async with open_client() as client:
        courses = await fetch_courses(client)
        courses = [c for c in courses if (c.created_at or '') >= COURSE_CUTOFF]
        if filters:
            courses = [c for c in courses if course_matches(c, filters)]
        if not courses:
            raise SystemExit('没有匹配的进行中课堂。')
        total_completed = total_saved = 0
        for course in courses:
            completed, saved = await archive_classroom(
                client, course, answers, write=not args.no_archive,
                cleanup_attempts=args.cleanup_attempts)
            total_completed += completed
            total_saved += saved
        print(f'\n===== 合计：已完成 {total_completed} 关，归档 {total_saved} 个 =====')
        if not args.no_archive:
            print(f'答案库目录：{solutions.SOLUTIONS_DIR}')


if __name__ == '__main__':
    asyncio.run(main())
