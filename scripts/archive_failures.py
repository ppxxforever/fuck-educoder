"""只读归档：把当前未通过关卡的本地答案和平台反馈存进 attempts/。

不会提交、不会修改平台数据。用途：
  - 找出「明明交了却没通过」的关卡；
  - 按实验/关卡生成文件夹，保存当前答案脚本与评测输出，方便人工修改后复用。

用法：
  uv run python scripts/archive_failures.py                 # 所有进行中课堂（只读）
  uv run python scripts/archive_failures.py --no-archive    # 只列出未通过关卡
  uv run python scripts/archive_failures.py --classroom HCEAP94S --classroom 2i6ng7vp
  uv run python scripts/archive_failures.py --generate-missing   # 缺答案的图形题用 AI 生成初稿
"""
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from educoder_reminder import attempts
from educoder_reminder.ai import ai_configured
from educoder_reminder.answer_sources import answer_for_level
from educoder_reminder.client import open_client
from educoder_reminder.courses import fetch_courses
from educoder_reminder.errors import CollectionError
from educoder_reminder.submit import (
    DEFAULT_ANSWERS, _game_view, _verdict_feedback, fetch_homework_rows, load_answers,
    resolve_entry, walk_prev_to_head,
)
from educoder_reminder.submit_all import COURSE_CUTOFF, course_matches, split_filters
from educoder_reminder.submit_uml import (
    ai_solve_uml, is_graphic, load_generic_example,
)


async def archive_classroom(client, course, answers, *, write=True, generate=False):
    code = course.identifier
    print(f'\n===== {course.name}（{code}）=====')
    try:
        rows = await fetch_homework_rows(client, code)
    except CollectionError as exc:
        print(f'  ✗ 读取实验列表失败：{exc}')
        return 0, 0

    failed = total = archived = 0
    for hw in rows:
        hw_name = hw.get('name') or ''
        try:
            entry = await resolve_entry(client, hw.get('shixun_identifier'),
                                        hw.get('homework_id'))
            if not entry:
                print(f'  ? {hw_name}：无法解析入口关卡')
                continue
            ordered, cache = await walk_prev_to_head(client, entry)
        except CollectionError as exc:
            print(f'  ✗ {hw_name}：读取关卡链失败：{exc}')
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
            total += 1
            game = _game_view(detail)
            status = game.get('status')
            if status == 2:
                continue
            failed += 1
            challenge = detail.get('challenge') or {}
            subject = (challenge.get('subject') or '').strip() or gid
            score = game.get('final_score')
            feedback = _verdict_feedback(detail) or (
                f'平台未记通关（status={status}，final_score={score}）')
            content, kind, local_path, source = answer_for_level(
                detail, answers, code, course.name, hw_name)

            if (not content and write and generate and ai_configured()
                    and (kind == 'uml' or is_graphic(detail))):
                try:
                    content = await ai_solve_uml(challenge.get('task_pass'),
                                                 load_generic_example())
                    source = 'AI 生成'
                    kind = 'uml'
                    print(f'    · 用 AI 生成 {subject} 的 .mdj 作为初始答案')
                except Exception as exc:
                    print(f'    · AI 生成失败：{type(exc).__name__}: {exc}')
                    content = None

            label = '已存档' if (write and content) else (
                '只建文件夹（缺答案）' if write else '未存档')
            if write:
                try:
                    if content:
                        attempts.save_attempt(
                            hw_name, subject, content, path=local_path, gid=gid,
                            kind=kind or 'code', classroom=code, passed=False,
                            feedback=feedback, extra={'source': source})
                        archived += 1
                    else:
                        note = ('本地题库没有该关卡的答案。\n'
                                f'课堂：{course.name}（{code}）\n实验：{hw_name}\n'
                                f'关卡：{subject}\ngid：{gid}\nkind：{kind}\n')
                        attempts.ensure_level(
                            hw_name, subject, gid=gid, path=local_path or '',
                            kind=kind or '', classroom=code, note=note)
                except Exception as exc:
                    print(f'    · 保存失败：{exc}')
                    label = '保存失败'
            print(f'  ✗ {hw_name} / {subject}（{gid}）：status={status} score={score} '
                  f'kind={kind} 来源={source or "无"} → {label}')
    print(f'  —— 未通过 {failed}/{total} 关；本次存档 {archived} 个')
    return failed, archived


async def main():
    parser = argparse.ArgumentParser(description='把未通过关卡的答案与反馈归档到 attempts/（只读）')
    parser.add_argument('--classroom', action='append', default=None,
                        help='只处理指定课堂：code 或名称，可多次/逗号分隔')
    parser.add_argument('--answers', default=str(DEFAULT_ANSWERS), help='answers.json 路径')
    parser.add_argument('--no-archive', action='store_true', help='只列出，不写 attempts/')
    parser.add_argument('--generate-missing', action='store_true',
                        help='缺本地答案的图形题用 AI 生成一份 .mdj 初始答案（不提交）')
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
        total_failed = total_archived = 0
        for course in courses:
            failed, archived = await archive_classroom(
                client, course, answers, write=not args.no_archive,
                generate=args.generate_missing)
            total_failed += failed
            total_archived += archived
        print(f'\n===== 合计：未通过 {total_failed} 关，归档 {total_archived} 个 =====')
        if not args.no_archive:
            print(f'存档目录：{attempts.ATTEMPTS_DIR}')


if __name__ == '__main__':
    asyncio.run(main())
