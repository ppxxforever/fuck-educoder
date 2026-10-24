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
from pathlib import Path

from playwright.async_api import Error as PlaywrightError

from .ai import ai_configured
from .client import open_client
from .courses import fetch_courses
from .errors import CollectionError
from .submit import (
    fetch_homework_rows, load_answers, match_homework,
    process_experiment as process_choice_code,
)
from .submit_uml import process_experiment as process_uml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANSWERS = ROOT / 'answers.json'
# 只处理此日期（含）之后创建的课堂（本学季），过滤掉旧学期课堂
COURSE_CUTOFF = '2026-08-01'


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


async def run_all(apply, classroom_filter, limit, poll_timeout, experiment_filter,
                  use_ai, release_pods, release_envs, answers_path, delay=5.0):
    answers = load_answers(answers_path)
    stats = {
        'submitted': 0, 'would_submit': 0, 'skipped_passed': 0,
        'skipped_no_answer': 0, 'skipped_error': 0, 'failed': 0, 'processed': 0,
    }
    async with open_client() as client:
        courses = await fetch_courses(client)
        courses = [c for c in courses if (c.created_at or '') >= COURSE_CUTOFF]
        print(f'检测到 {len(courses)} 个本学期课堂（created_at >= {COURSE_CUTOFF}）。')
        for course in courses:
            code = course.identifier
            if classroom_filter and code != classroom_filter:
                continue
            print(f'\n===== 课堂：{course.name}（{code}）=====')
            try:
                rows = await fetch_homework_rows(client, code)
            except CollectionError as exc:
                stats['skipped_error'] += 1
                print(f'  ✗ 无法读取实验列表，跳过：{exc}')
                continue
            classroom = _find_classroom(answers, code, getattr(course, 'name', None))
            experiments = classroom.get('experiments', []) if classroom else []
            for hw in rows:
                name = hw.get('name') or ''
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
                try:
                    await process_choice_code(
                        client, hw, experiment, apply, stats, poll_timeout,
                        limit=limit, answers=answers, classroom_code=code, use_ai=use_ai,
                        delay=delay)
                except CollectionError as exc:
                    stats['skipped_error'] += 1
                    print(f'  ✗ 选择/代码题处理失败：{exc}')
                try:
                    await process_uml(
                        client, hw, apply, stats, poll_timeout, limit=limit,
                        experiment_filter=experiment_filter, use_ai=use_ai,
                        release_pods=release_pods, delay=delay, classroom=code)
                except CollectionError as exc:
                    stats['skipped_error'] += 1
                    print(f'  ✗ 图形题处理失败：{exc}')

    if apply and ai_configured():
        try:
            answers_path.write_text(
                json.dumps(answers, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f'\n已把 AI 答案写回 {answers_path}。')
        except OSError as exc:
            print(f'\n⚠️ 写回 {answers_path} 失败：{exc}')

    print('\n===== 汇总 =====')
    for key, value in stats.items():
        print(f'  {key}: {value}')
    if not apply:
        print('\n这是 dry-run 预览，未真实提交。确认无误后加 --apply 真实提交。')
    return stats


def main():
    parser = argparse.ArgumentParser(description='一键提交：选择题 + 代码题 + UML 绘图题（平台驱动）。')
    parser.add_argument('--apply', action='store_true', help='真实提交（默认 dry-run 只预览）。')
    parser.add_argument('--classroom', default=None, help='只处理指定课堂 code。')
    parser.add_argument('--limit', type=int, default=None, help='最多处理多少个关卡。')
    parser.add_argument('--poll-timeout', type=int, default=120, help='评测等待秒数。')
    parser.add_argument('--experiment', default=None, help='只处理名称包含该字符串的实验。')
    parser.add_argument('--no-ai', action='store_true', help='缺答案时不用 AI 自动生成。')
    parser.add_argument('--release-envs', action='store_true', help='运行前先释放所有 UML 环境 pod。')
    parser.add_argument('--no-release', action='store_true', help='UML 每个实验跑完不释放其 pod。')
    parser.add_argument('--delay', type=float, default=5.0, help='每个实验之间的等待秒数（避免环境启动过快）。')
    parser.add_argument('--answers', default=str(DEFAULT_ANSWERS), help='answers.json 路径。')
    args = parser.parse_args()
    try:
        asyncio.run(run_all(args.apply, args.classroom, args.limit,
                            args.poll_timeout, args.experiment, not args.no_ai,
                            not args.no_release, args.release_envs, Path(args.answers),
                            delay=args.delay))
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
    except PlaywrightError:
        raise SystemExit('Playwright 请求失败，请检查网络；认证详情不写入日志。') from None


if __name__ == '__main__':
    main()
