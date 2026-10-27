"""一键提交全部作业（平台驱动）。

流程：
  1. 检测当前登录用户所有进行中的课堂（/api/users/{login}/courses.json）；
  2. 逐个课堂拉取实验作业列表（type=4），过滤已完全通过的实验；
  3. 对未通过的实验，同时分发：
     - 选择/代码题 → educoder_reminder.submit（answers.json 匹配 + AI/测试文件补做）
     - 图形化 UML 题 → educoder_reminder.submit_uml（answer/ 匹配 + 抓评测脚本 + AI 兜底）

用法：
  uv run python -m educoder_reminder.submit_all            # 预览（不提交）
  uv run python -m educoder_reminder.submit_all --apply    # 真实提交
"""
import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

from . import levels as levelmod
from .ai import ai_configured
from .client import open_client
from .courses import fetch_courses
from .errors import CollectionError
from .submit import (
    ensure_classroom, fetch_homework_rows, homework_deadline, is_homework_closed,
    load_answers, match_homework, persist_answers, process_experiment as process_choice_code,
    resolve_entry,
)
from .submit_uml import process_experiment as process_uml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANSWERS = ROOT / 'answers.json'
# 未完成关卡的落盘报告：跑完就能看到「哪些实验还有几关没交」
UNFINISHED_REPORT = ROOT / 'data' / 'unfinished.json'
# 只处理此日期（含）之后创建的课堂（本学季），过滤掉旧学期课堂
COURSE_CUTOFF = '2026-08-01'


def split_filters(values):
    """把 --classroom 的多次传参 / 逗号分隔写法展开成列表。"""
    out = []
    for v in values or []:
        if v is None:
            continue
        for part in str(v).replace('，', ',').split(','):
            part = part.strip()
            if part:
                out.append(part)
    return out


def course_matches(course, filters):
    """课程是否命中筛选：code 精确 / 名称精确 / 名称包含（忽略大小写）。"""
    if not filters:
        return True
    code = course.identifier or ''
    name = (course.name or '')
    for f in filters:
        if code == f:
            return True
        if name == f:
            return True
        if f.lower() in name.lower():
            return True
    return False


def _find_classroom(answers, code, name=None):
    """按课堂 code 找本地答案；找不到再按课堂名匹配（换班后 code 变了也能复用）。"""
    classrooms = answers.get('classrooms', [])
    for c in classrooms:
        if c.get('code') == code:
            return c
    if name:
        norm = lambda x: (x or '').strip()
        for c in classrooms:
            if norm(c.get('name')) == norm(name):
                return c
    return None


async def audit_experiment(client, apply, stats, coverage, course, hw, report, entry=None):
    """实验收尾校验：跑完立刻独立复查关卡链。

    这是防「静默漏提交」的兜底。两条提交链（选择/代码题、图形题）本身就是
    两套独立的遍历，任何一条对某个关卡不敢下手都会 continue；2026-10-25 的
    「软件详细设计-2 / 面向数据流的设计方法-2」就是这么漏的。现在只要动过实验，
    不管两条链怎么说，这里都会按平台状态重新数一遍，没通关就报错 + 非 0 退出。

    「详情读不全」不算未通关（照样不能算校验成功）：计入 audit_error，
    下一轮会重查，不会变成随机的「未通关」误报。
    """
    name = hw.get('name') or ''
    try:
        findings = await levelmod.audit_experiment(client, hw, coverage, entry=entry)
    except CollectionError as exc:
        stats['audit_error'] += 1
        print(f'  ! 实验收尾校验失败（无法复查关卡链）：{exc}')
        return
    except PlaywrightError:
        raise
    except Exception as exc:                      # 校验失败不能拖死整轮
        stats['audit_error'] += 1
        print(f'  ! 实验收尾校验失败：{type(exc).__name__}: {exc}')
        return
    if findings is None:
        stats['audit_error'] += 1
        print('  ! 实验收尾校验跳过：拿不到入口关卡，请人工确认这个实验。')
        return

    unreadable = [f for f in findings if f.get('unreadable')]
    if unreadable:
        stats['audit_error'] += len(unreadable)
        print(f'  ! 实验收尾校验：{name} 有 {len(unreadable)} 个关卡的详情读不全，'
              '无法确认是否通关（下一轮重查）')
        for item in unreadable:
            print(f'      ? {item["subject"]}（{item["gid"]}）')
    findings = [f for f in findings if not f.get('unreadable')]
    if not findings:
        if not unreadable:
            print('  ✓ 实验收尾校验：全部关卡已通关')
        return

    stats['unowned'] += len([f for f in findings if not f.get('owner')])
    if apply:
        stats['unfinished'] += len(findings)
        print(f'  ✗ 实验收尾校验：{name} 仍未完成，还剩 {len(findings)} 关')
    else:
        print(f'  · 预览：{name} 还有 {len(findings)} 关待提交')
    for item in findings:
        owner = item.get('owner') or levelmod.UNOWNED_LABEL
        print(f'      · {item["subject"]}（{item["kind"]}，{owner}，'
              f'{item.get("action") or "未处理"}）')
    report.append({
        'course': course.name,
        'course_code': course.identifier,
        'homework': name,
        'homework_id': hw.get('homework_id'),
        'levels': findings,
    })


def report_path() -> Path:
    """未完成报告的落盘位置（测试/CI 可用环境变量覆盖）。"""
    return Path(os.environ.get('EDUCODER_UNFINISHED_REPORT') or UNFINISHED_REPORT)


def write_unfinished_report(report, apply, stats):
    """把未完成关卡写到 data/unfinished.json；本轮全清则删掉旧报告。

    只在「本轮真的动过关卡」时才落盘，避免测试 / 空跑把真实报告冲掉。
    """
    if not (stats.get('processed') or stats.get('unowned') or stats.get('unfinished')):
        return
    path = report_path()
    try:
        if not report:
            path.unlink(missing_ok=True)
            return
        payload = {
            'checked_at': datetime.now().astimezone().isoformat(timespec='seconds'),
            'account': os.environ.get('EDUCODER_LOGIN_ACCOUNT') or '',
            'apply': bool(apply),
            'unfinished_levels': stats.get('unfinished', 0),
            'unowned_levels': stats.get('unowned', 0),
            'experiments': report,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding='utf-8')
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except OSError as exc:
        print(f'  ! 写 {path} 失败：{exc}')


async def _cross_check_platform(client, code, touched, stats):
    """平台进度对账：本地日志说通关了，平台可能还没记。

    缺 sec_key 时平台只评分、不把关卡写成已通关，而本地可能已经打了「评测通过 ✔」；
    同样地，TUI/队列读的是 `data/homeworks.json` 的 `shixun_finished_status` 快照。
    这里重新拉一次课堂作业列表（一次请求）把这两种口径对齐，避免「日志说通过、
    平台/界面说未通过」。
    """
    try:
        rows = await fetch_homework_rows(client, code)
    except CollectionError as exc:
        print(f'  ! 平台进度对账失败（不影响已提交的关卡）：{exc}')
        return
    by_id = {row.get('homework_id'): row for row in rows}
    for hw_id, name in touched.items():
        row = by_id.get(hw_id)
        if row is None or row.get('shixun_finished_status') == 1:
            continue
        stats['stale_homework'] = stats.get('stale_homework', 0) + 1
        print(f'  ⚠ 平台仍显示未完成：{name}（本机已提交/评测通过，平台未记通关；'
              '下一轮会自动重交，也可稍后用 --repair-status 重修）')


async def run_all(apply, classroom_filter, limit, poll_timeout, experiment_filter,
                  use_ai, release_pods, release_envs, answers_path, delay=5.0,
                  repair_status=False, include_expired=False):
    answers = load_answers(answers_path)
    stats = {
        'submitted': 0, 'would_submit': 0, 'skipped_passed': 0,
        'skipped_no_answer': 0, 'skipped_error': 0, 'skipped_closed': 0,
        'failed': 0, 'processed': 0,
        'unfinished': 0, 'unowned': 0, 'audit_error': 0, 'unconfirmed': 0,
        'stale_homework': 0,
    }
    report: list[dict] = []
    async with open_client() as client:
        courses = await fetch_courses(client)
        courses = [c for c in courses if (c.created_at or '') >= COURSE_CUTOFF]
        filters = split_filters(classroom_filter if isinstance(classroom_filter, (list, tuple))
                                else [classroom_filter])
        if filters:
            courses = [c for c in courses if course_matches(c, filters)]
            print(f'筛选「{"、".join(filters)}」后剩 {len(courses)} 个课堂。')
        else:
            print(f'检测到 {len(courses)} 个本学期课堂（created_at >= {COURSE_CUTOFF}）。')
        if not courses:
            print('没有匹配的课堂。可先运行：uv run python -m educoder_reminder.courses')
            return stats
        for course in courses:
            code = course.identifier
            print(f'\n===== 课堂：{course.name}（{code}）=====')
            try:
                rows = await fetch_homework_rows(client, code)
            except CollectionError as exc:
                stats['skipped_error'] += 1
                print(f'  ✗ 无法读取实验列表，跳过：{exc}')
                continue
            classroom = _find_classroom(answers, code, getattr(course, 'name', None))
            if classroom is None:
                # 本地没有的新课堂：先把条目建好（带真实课堂名），否则 AI 刷通的
                # 答案会在 save_level_answer 里找不到 classroom、静默丢掉——
                # 那就变成「每次换账号都得从头 AI 一遍」，闭环断了。
                classroom = ensure_classroom(answers, code, getattr(course, 'name', None))
                if apply and classroom is not None:
                    persist_answers(answers, answers_path)
                    print(f'  + 新建答案库条目：{course.name}（{code}）')
            experiments = classroom.get('experiments', []) if classroom else []
            touched_rows: dict[int, str] = {}
            for hw in rows:
                name = hw.get('name') or ''
                if not include_expired and is_homework_closed(hw):
                    stats['skipped_closed'] += 1
                    deadline = homework_deadline(hw)
                    when = f'（截止 {deadline:%Y-%m-%d %H:%M}）' if deadline else '（已归档）'
                    print(f'  - [跳过] 实验已截止{when}：{name}')
                    continue
                if hw.get('shixun_finished_status') == 1:
                    stats['skipped_passed'] += 1
                    print(f'  - [跳过] 实验已完成：{name}')
                    continue
                experiment = match_homework(name, experiments)
                if experiment is None:
                    experiment = {'name': name, 'levels': []}
                    tag = 'answers.json 未收录'
                else:
                    tag = 'answers.json 有记录'
                print(f'  ▸ 实验：{name}（homework_id={hw.get("homework_id")}，{tag}）')
                coverage = levelmod.Coverage()
                before = (stats['submitted'], stats['would_submit'], stats['processed'])
                # 一轮实验只解析一次入口，三条链（选择/代码、图形、收尾校验）共用。
                # 各解析一次的话，平台恰好换尝试时会出现「提交打在旧链、审计看新链」，
                # 表现就是评测通过却报未通关（gid 每轮尝试都会整体换新）。
                try:
                    entry = await resolve_entry(client, hw.get('shixun_identifier'),
                                                hw.get('homework_id'))
                except CollectionError as exc:
                    entry = None
                    print(f'  ! 解析实验入口失败，交由各链自己重试：{exc}')
                try:
                    await process_choice_code(
                        client, hw, experiment, apply, stats, poll_timeout,
                        limit=limit, answers=answers, classroom_code=code, use_ai=use_ai,
                        delay=delay, repair_status=repair_status, include_expired=True,
                        answers_path=answers_path, coverage=coverage, entry=entry)
                except CollectionError as exc:
                    stats['skipped_error'] += 1
                    print(f'  ✗ 选择/代码题处理失败：{exc}')
                try:
                    await process_uml(
                        client, hw, apply, stats, poll_timeout, limit=limit,
                        experiment_filter=experiment_filter, use_ai=use_ai,
                        release_pods=release_pods, delay=delay, classroom=code,
                        repair_status=repair_status, include_expired=True,
                        coverage=coverage, entry=entry)
                except CollectionError as exc:
                    stats['skipped_error'] += 1
                    print(f'  ✗ 图形题处理失败：{exc}')

                # 实验收尾校验：只要本轮动过这个实验，就独立复查一遍关卡链。
                # 任何「没通过」或「无人负责」的关卡都必须报出来，不许静默。
                touched = (stats['submitted'], stats['would_submit'],
                           stats['processed']) != before
                if touched:
                    if hw.get('homework_id') is not None:
                        touched_rows[hw['homework_id']] = name
                    await audit_experiment(client, apply, stats, coverage,
                                           course, hw, report, entry=entry)

            # 交叉校验：本地日志说「全通关」，平台却可能还没记通关（没 sec_key 时平台
            # 只给分不写 status=2）。重新拉一次作业列表（课堂级，一次请求）对账。
            if apply and touched_rows:
                await _cross_check_platform(client, code, touched_rows, stats)

    if apply:
        # 不再只在配了 AI 时写盘：从 solutions/ 复用回来的答案也需要落盘。
        try:
            answers_path.write_text(
                json.dumps(answers, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'\n已把答案写回 {answers_path}。')
        except OSError as exc:
            print(f'\n⚠️ 写回 {answers_path} 失败：{exc}')

    print('\n===== 汇总 =====')
    for key, value in stats.items():
        print(f'  {key}: {value}')
    write_unfinished_report(report, apply, stats)
    if stats['unowned']:
        print(f'\n⚠️  有 {stats["unowned"]} 个关卡无人负责（工具漏处理），'
              '请把上面标了 [无主关卡] 的日志贴出来。')
    if apply and stats['unfinished']:
        print(f'⚠️  有 {stats["unfinished"]} 个关卡仍未通关，明细见 {report_path()}。')
    if stats['audit_error']:
        print(f'⚠️  有 {stats["audit_error"]} 个关卡/实验无法做收尾校验，请人工确认。')
    if stats['unconfirmed']:
        print(f'⚠️  有 {stats["unconfirmed"]} 个关卡「评测通过但平台未记通关」（status≠2）；'
              f'可稍后跑 --repair-status 重修。')
    if stats.get('stale_homework'):
        print(f'⚠️  有 {stats["stale_homework"]} 个实验平台仍显示未完成，'
              '请到平台确认或等下一轮重交。')
    if not apply:
        print('\n这是 dry-run 预览，未真实提交。确认无误后加 --apply 真实提交。')
    return stats


def main():
    parser = argparse.ArgumentParser(description='一键提交：选择题 + 代码题 + UML 绘图题（平台驱动）。')
    parser.add_argument('--apply', action='store_true', help='真实提交（默认 dry-run 只预览）。')
    parser.add_argument('--classroom', action='append', default=None,
                        help='只处理指定课堂：code 或课程名，可多次传或逗号分隔。'
                             '例：--classroom 2i6ng7vp --classroom 数据库'
                             ' 或 --classroom "软件工程,数据库"')
    parser.add_argument('--limit', type=int, default=None, help='最多处理多少个关卡。')
    parser.add_argument('--poll-timeout', type=int, default=180, help='评测等待秒数。')
    parser.add_argument('--experiment', default=None, help='只处理名称包含该字符串的实验。')
    parser.add_argument('--no-ai', action='store_true', help='缺答案时不用 AI 自动生成。')
    parser.add_argument('--repair-status', action='store_true',
                        help='重交「评测已通过但平台未记通关（status!=2）」的关卡。')
    parser.add_argument('--include-expired', action='store_true',
                        help='连已截止/已归档的实验也处理（默认跳过）。')
    parser.add_argument('--release-envs', action='store_true', help='运行前先释放所有 UML 环境 pod。')
    parser.add_argument('--no-release', action='store_true', help='UML 每个实验跑完不释放其 pod。')
    parser.add_argument('--delay', type=float, default=5.0, help='每个实验之间的等待秒数（避免环境启动过快）。')
    parser.add_argument('--answers', default=str(DEFAULT_ANSWERS), help='answers.json 路径。')
    args = parser.parse_args()
    try:
        stats = asyncio.run(run_all(args.apply, args.classroom, args.limit,
                                    args.poll_timeout, args.experiment, not args.no_ai,
                                    not args.no_release, args.release_envs, Path(args.answers),
                                    delay=args.delay, repair_status=args.repair_status,
                                    include_expired=args.include_expired))
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
    except PlaywrightError:
        raise SystemExit('Playwright 请求失败，请检查网络；认证详情不写入日志。') from None
    # 退出码就是契约：有漏网的关卡就绝不能是 0，否则上层队列会当成「全部搞定」。
    if stats.get('unowned') or stats.get('audit_error') \
            or (args.apply and stats.get('unfinished')):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
