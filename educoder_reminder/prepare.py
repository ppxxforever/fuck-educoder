"""按课程批量爬题 + 集中用 AI 预生成答案（只写本地 prepared/，不提交）。

正常提交链是「走到哪一关、当场拿哪一关去问 AI」，AI 调用分散在一整轮提交里，
跑一次就花一次钱。这个命令把顺序倒过来：先把一门课（或全部进行中课堂）的题目
爬下来，集中把缺答案的关卡生成好，之后正常提交时直接复用，不再调用 AI。

流程：
  1. 取进行中课堂（--classroom 指定课程 code/名称），逐个课堂拉实验列表；
  2. 逐个实验沿关卡链爬题，题目原文写到 prepared/<实验>/<关卡>/question.md；
  3. 已有本地答案（answers.json / answer/ / solutions/ / attempts/ / prepared/）
     就跳过，绝不重复调用 AI；
  4. 没有答案才按题型生成：
     - 选择题：AI 选出答案字母；
     - 代码题：先读测试文件提取参考答案，再 AI 读模板/评测脚本/预期输出生成；
     - 图形题（UML）：先用 graders/ 缓存的评测脚本逆向构造（不烧 AI），
       没有缓存才让 AI 按题面生成 .mdj；
  5. 结果写进 prepared/<实验>/<关卡>/answer.*，提交链自动复用。

不提交、不触发评测、不占平台提交次数；唯一的外部成本是 AI 调用。
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

from . import attempts, levels as levelmod, prepared
from .ai import AIError, ai_configured
from .answer_sources import answer_for_level, find_answer_level
from .client import open_client
from .courses import fetch_courses
from .errors import CollectionError
from .submit import (
    DEFAULT_ANSWERS, _choice_solution_text, ai_solve_code, ai_solve_choice, detail_of,
    extract_field_tables, fetch_homework_rows, get_classroom_schema, homework_deadline,
    is_homework_closed, is_level_passed, load_answers, match_homework, postprocess_sql,
    read_grader_file, read_remote_file, read_sql_schema, resolve_entry, solve_code_from_test,
    split_paths, walk_prev_to_head,
)
from .submit_all import COURSE_CUTOFF, _find_classroom, course_matches, split_filters
from .submit_uml import (
    extract_target, load_generic_example, load_grader_cache, parse_target_from_script,
    solve_from_grader, ai_solve_uml,
)

ROOT = Path(__file__).resolve().parents[1]


def _display(path) -> str:
    """相对项目根目录显示路径（prepared/ 被测试或自定义到别处时原样显示）。"""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------- #
# 爬题
# --------------------------------------------------------------------------- #
async def walk_levels(client, hw):
    """从一个实验的入口关卡往前走一遍，返回 [(gid, detail), ...]；读不到返回 None。"""
    entry = await resolve_entry(client, hw.get('shixun_identifier'), hw.get('homework_id'))
    if not entry:
        return None
    ordered, cache = await walk_prev_to_head(client, entry)
    if not ordered:
        return None
    queue, seen, out = list(ordered), set(ordered), []
    while queue:
        gid = str(queue.pop(0))
        detail = await detail_of(client, cache, gid)
        out.append((gid, detail))
        nxt = detail.get('next_game')
        if nxt and str(nxt) not in seen:
            seen.add(str(nxt))
            queue.append(str(nxt))
    return out


def recorded_kind(answers, code, course_name, hw_name, subject):
    """answers.json 里记过的题型（实测定型，比平台详情可靠）。"""
    classroom = _find_classroom(answers, code, course_name)
    experiment = match_homework(hw_name, classroom.get('experiments', [])) if classroom else None
    level = find_answer_level(experiment, subject) if experiment else None
    return levelmod.recorded_kind((level or {}).get('kind'))


def question_text(detail, *, gid, kind, target=''):
    """把平台关卡详情整理成便于人工/AI 阅读的题目文本。"""
    challenge = detail.get('challenge') or {}
    subject = (challenge.get('subject') or '').strip()
    lines = [f'# {subject or gid}', '', f'- 关卡标识：`{gid}`', f'- 题型：{kind}']
    path = target or challenge.get('path') or ''
    if path:
        lines.append(f'- 目标文件：`{path}`')
    chooses = detail.get('chooses') or []
    if chooses:
        lines += ['', '## 题目']
        for index, q in enumerate(chooses, 1):
            lines += ['', f'### {index}. {(q.get("subject") or "").strip()}']
            for pos, option in enumerate(q.get('challenge_question') or []):
                lines.append(f'{chr(ord("A") + pos)}. {(option.get("option_name") or "").strip()}')
    task = (challenge.get('task_pass') or '').strip()
    if task:
        lines += ['', '## 题目原文', '', task]
    return '\n'.join(lines).rstrip() + '\n'


# --------------------------------------------------------------------------- #
# 生成答案
# --------------------------------------------------------------------------- #
async def generate_code(client, hw_id, gid, detail, *, code, path):
    """生成代码题答案：先读测试文件提取参考答案，再退回 AI。返回 (content, note)。"""
    challenge = detail.get('challenge') or {}
    task_pass = challenge.get('task_pass')
    try:
        from_test = await solve_code_from_test(client, gid, hw_id, path)
    except CollectionError:
        from_test = ''
    if from_test and from_test.strip():
        return from_test, '读测试文件提取参考答案'
    template = await read_remote_file(client, gid, hw_id, path)
    if path.endswith('.sql'):
        hint = await read_sql_schema(client, gid, hw_id, path)
        if not hint:
            hint = await get_classroom_schema(client, code, current_task_pass=task_pass)
        if not hint:
            hint = extract_field_tables(task_pass)
    else:
        hint = await read_grader_file(client, gid, hw_id, path)
    expected = '\n'.join(
        (t.get('output') or '').strip()
        for t in detail.get('test_sets') or []
        if (t.get('output') or '').strip())
    generated = await ai_solve_code(task_pass, path, grader_hint=hint,
                                    expected_output=expected, template=template)
    if generated and path.endswith('.sql'):
        generated = postprocess_sql(generated, template, task_pass)
    return generated, 'AI 生成'


async def generate_answer(client, hw, gid, detail, kind, *, code, course_name):
    """按题型生成答案，返回 (content, 目标路径, 说明)；失败时 content 为 None。"""
    hw_id = hw.get('homework_id')
    challenge = detail.get('challenge') or {}
    subject = (challenge.get('subject') or '').strip()

    if kind == levelmod.KIND_CHOICE:
        chooses = detail.get('chooses') or []
        if not chooses:
            return None, 'answer.json', '平台没有返回选择题题干（详情残缺），下次再试'
        selection = await ai_solve_choice(chooses)
        return _choice_solution_text(subject, selection), 'answer.json', 'AI 选择答案'

    if kind == levelmod.KIND_CODE:
        paths = split_paths(challenge.get('path'))
        if len(paths) != 1:
            return None, '', f'多文件关卡（{len(paths)} 个文件），AI 暂不支持'
        content, note = await generate_code(client, hw_id, gid, detail,
                                           code=code, path=paths[0])
        return content, paths[0], note

    if kind == levelmod.KIND_GRAPHIC:
        target, step = extract_target(challenge.get('path'), challenge.get('task_pass'))
        script = load_grader_cache(gid, subject, step)
        if script:
            content = solve_from_grader(script)
            if content:
                # 评测脚本里写明它实际读取的路径，以它为准（题目描述常与评测器不一致）
                real_target = parse_target_from_script(script)
                return content, real_target or target or '', '按缓存评测脚本逆向构造（未调用 AI）'
        if not ai_configured():
            return None, target or '', '没有缓存的评测脚本，且未配置 AI_API_KEY'
        content = await ai_solve_uml(challenge.get('task_pass'), load_generic_example())
        if not content:
            return None, target or '', 'AI 没有生成合法的 .mdj'
        return content, target or '', 'AI 生成 .mdj'

    return None, '', '题型无法判定'


# --------------------------------------------------------------------------- #
# 单关处理
# --------------------------------------------------------------------------- #
def _qualified(cached_script, kind):
    """这一关不调用 AI 也能出答案（图形题有缓存评测脚本）。"""
    return kind == levelmod.KIND_GRAPHIC and bool(cached_script)


async def prepare_level(client, course, hw, gid, detail, answers, args, stats):
    """处理一个关卡。返回 False 表示达到 --limit，应停止整轮。"""
    code = course.identifier
    hw_name = hw.get('name') or ''
    challenge = detail.get('challenge') or {}
    subject = (challenge.get('subject') or '').strip()
    stats['levels'] += 1

    if not subject:
        stats['skipped_error'] += 1
        print(f'    - [跳过] {gid}：平台没返回关卡标题（详情残缺），下一轮再试。')
        return True

    kind = recorded_kind(answers, code, course.name, hw_name, subject) \
        or levelmod.classify_level(detail)
    target, step = extract_target(challenge.get('path'), challenge.get('task_pass'))
    if not target:
        target = attempts.attempt_target(hw_name, subject)
    question_path = target or (challenge.get('path') or '').strip()

    if not args.dry_run:
        # 爬题：题目原文先落盘，AI 没生成成功也留下了题目
        prepared.save_question(
            hw_name, subject,
            question_text(detail, gid=gid, kind=kind, target=question_path),
            gid=gid, kind=kind, path=question_path, classroom=code)

    # 第一优先：prepared/ 里已经预生成过 → 不重复烧 AI（--overwrite 才重做）
    if not args.overwrite and prepared.prepared_path(hw_name, subject):
        stats['skipped_prepared'] += 1
        print(f'    ✓ {subject}：prepared/ 已有预生成答案，跳过（--overwrite 可重做）')
        return True
    # 第二优先：其它本地答案来源。这些是可信/已实测的记录，--overwrite 也不覆盖：
    # 答案在提交链里优先级高于 prepared/，重做只会白烧 AI，新答案反而用不上。
    content, _kind, _path, source = answer_for_level(
        detail, answers, code, course.name, hw_name, include_prepared=False)
    if content:
        stats['skipped_local'] += 1
        print(f'    ✓ {subject}：已有本地答案（{source}），不调用 AI')
        return True

    cached_script = None
    if kind == levelmod.KIND_GRAPHIC:
        cached_script = load_grader_cache(gid, subject, step)

    if args.dry_run:
        stats['planned'] += 1
        if _qualified(cached_script, kind):
            how = '用缓存评测脚本逆向构造（不调用 AI）'
        elif args.no_ai or not ai_configured():
            how = '缺答案但 AI 已禁用，真跑会跳过'
        else:
            how = '调用 AI 生成'
        print(f'    · {subject}（{kind}）：本地无答案 → {how}')
        return True

    if args.limit is not None and stats['generated'] >= args.limit:
        print(f'    … 达到 --limit {args.limit}，停止。')
        return False

    if kind == levelmod.KIND_UNKNOWN:
        stats['skipped_error'] += 1
        print(f'    - [跳过] {subject}：题型无法判定（平台详情残缺），下一轮再试。')
        return True

    if (args.no_ai or not ai_configured()) and not _qualified(cached_script, kind):
        stats['skipped_no_ai'] += 1
        reason = '已用 --no-ai 禁用 AI' if args.no_ai else '未配置 AI_API_KEY'
        print(f'    - [跳过] {subject}：本地无答案，且{reason}。')
        return True

    try:
        content, target_path, note = await generate_answer(
            client, hw, gid, detail, kind, code=code, course_name=course.name)
    except AIError as exc:
        stats['failed'] += 1
        print(f'    ✗ {subject}：AI 调用失败：{exc}')
        return True
    except CollectionError as exc:
        stats['failed'] += 1
        print(f'    ✗ {subject}：读取题目资料失败：{exc}')
        return True

    if not content or not content.strip():
        stats['skipped_error'] += 1
        print(f'    - [跳过] {subject}：{note or "没有生成答案"}')
        return True

    save_kind = 'uml' if kind == levelmod.KIND_GRAPHIC else kind
    saved = prepared.save_prepared(
        hw_name, subject, content, path=target_path or None, gid=gid,
        kind=save_kind, classroom=code, source='ai-prepare')
    stats['generated'] += 1
    print(f'    ✓ {subject}（{note}）→ {_display(saved) if saved else "(未保存)"}')
    return True


# --------------------------------------------------------------------------- #
# 课程 / 实验
# --------------------------------------------------------------------------- #
async def prepare_course(client, course, answers, args, stats):
    """处理一门课程。返回 False 表示达到 --limit，应停止整轮。"""
    code = course.identifier
    print(f'\n===== 课程：{course.name}（{code}）=====')
    try:
        rows = await fetch_homework_rows(client, code)
    except CollectionError as exc:
        stats['failed'] += 1
        print(f'  ✗ 读取实验列表失败：{exc}')
        return True
    print(f'  实验作业 {len(rows)} 条。')

    for hw in rows:
        hw_name = hw.get('name') or ''
        if not hw_name:
            continue
        if args.experiment and args.experiment not in hw_name:
            continue
        if hw.get('shixun_finished_status') == 1:
            stats['skipped_passed'] += 1
            print(f'  - [跳过] 实验已完成：{hw_name}')
            continue
        if not args.include_expired and is_homework_closed(hw):
            stats['skipped_closed'] += 1
            deadline = homework_deadline(hw)
            when = f'（截止 {deadline:%Y-%m-%d %H:%M}）' if deadline else '（已归档）'
            print(f'  - [跳过] 实验已截止{when}：{hw_name}')
            continue

        print(f'  ▸ 实验：{hw_name}')
        try:
            level_list = await walk_levels(client, hw)
        except CollectionError as exc:
            stats['failed'] += 1
            print(f'    ✗ 关卡链读取失败：{exc}')
            continue
        if not level_list:
            stats['failed'] += 1
            print('    ✗ 拿不到关卡链，跳过该实验。')
            continue

        for gid, detail in level_list:
            if is_level_passed(detail):
                stats['skipped_passed'] += 1
                continue
            if not await prepare_level(client, course, hw, gid, detail, answers, args, stats):
                return False
        if args.delay > 0:
            await asyncio.sleep(args.delay)
    return True


async def run(args):
    answers = load_answers(Path(args.answers))
    stats = {
        'levels': 0, 'generated': 0, 'skipped_local': 0, 'skipped_prepared': 0,
        'skipped_passed': 0, 'skipped_closed': 0, 'skipped_no_ai': 0,
        'skipped_error': 0, 'failed': 0, 'planned': 0,
    }
    filters = split_filters(args.classroom)
    async with open_client() as client:
        courses = await fetch_courses(client)
        if filters:
            courses = [c for c in courses if course_matches(c, filters)]
        else:
            # 不指定课程时只看本学季，避免历史课堂把 AI 额度全烧掉
            courses = [c for c in courses if (c.created_at or '') >= COURSE_CUTOFF]
        if not courses:
            raise SystemExit('没有匹配的进行中课堂。')
        print('课程：' + '、'.join(f'{c.name}（{c.identifier}）' for c in courses))
        for course in courses:
            if not await prepare_course(client, course, answers, args, stats):
                break
    print('\n===== 汇总 =====')
    for key, value in stats.items():
        print(f'  {key}: {value}')
    if args.dry_run:
        print('\n这是 --dry-run 预览：没有写 prepared/，也没有调用 AI。')
    else:
        print(f'\n预生成答案目录：{_display(prepared.PREPARED_DIR)}/')
        print('提交时会自动复用：answers.json / answer/ → solutions/ → attempts/ '
              '→ prepared/ → 现场调用 AI。')
    return stats


def main():
    parser = argparse.ArgumentParser(
        description='按课程爬取题目并集中预生成 AI 答案（只写本地 prepared/，不提交）。')
    parser.add_argument('--classroom', action='append', default=None,
                        help='只处理指定课程：code 或名称，可多次/逗号分隔；不填=本学季全部进行中课堂')
    parser.add_argument('--experiment', help='只处理名称包含该字符串的实验')
    parser.add_argument('--limit', type=int, default=None,
                        help='最多生成多少个答案（已有本地答案、已通关的不计）')
    parser.add_argument('--answers', default=str(DEFAULT_ANSWERS), help='answers.json 路径')
    parser.add_argument('--no-ai', action='store_true',
                        help='不调用 AI：只爬题并复用缓存评测脚本，缺答案的关卡跳过')
    parser.add_argument('--dry-run', action='store_true',
                        help='只列出计划，不写 prepared/、不调用 AI')
    parser.add_argument('--overwrite', action='store_true',
                        help='prepared/ 已有答案也重新生成（answers.json/solutions/attempts 仍视为已有答案）')
    parser.add_argument('--include-expired', action='store_true',
                        help='连已截止/已归档的实验也处理（默认跳过）')
    parser.add_argument('--delay', type=float, default=1.0,
                        help='每个实验之间的等待秒数（默认 1.0）')
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
    except PlaywrightError:
        raise SystemExit('Playwright 请求失败，请检查网络；认证详情不写入日志。') from None


if __name__ == '__main__':
    main()
