"""从本地题库（answers.json / answer/ / submit_*/ / attempts/）里找某个关卡的答案。"""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import levels as levelmod
from . import attempts, prepared, solutions
from .submit import detect_kind, match_homework, split_paths
from .submit_all import _find_classroom
from .submit_uml import collect_mdj, extract_target, is_graphic, resolve_answer_base


def _norm(text) -> str:
    return re.sub(r'\s+', '', str(text or ''))


def find_answer_level(experiment, subject):
    """在 answers.json 的实验里按关卡标题找答案（先精确，再包含匹配）。"""
    if not experiment:
        return None
    levels = experiment.get('levels') or []
    target = _norm(subject)
    for level in levels:
        if _norm(level.get('title')) == target:
            return level
    for level in levels:
        title = _norm(level.get('title'))
        if title and target and (title in target or target in title):
            return level
    return None


def local_code(answers, code, course_name, hw_name, subject):
    classroom = _find_classroom(answers, code, course_name)
    experiment = match_homework(hw_name, classroom.get('experiments', [])) if classroom else None
    level = find_answer_level(experiment, subject)
    if level and isinstance(level.get('answer'), dict):
        text = level['answer'].get('code') or ''
        if text.strip():
            return text
    return None


def local_choice(answers, code, course_name, hw_name, subject):
    classroom = _find_classroom(answers, code, course_name)
    experiment = match_homework(hw_name, classroom.get('experiments', [])) if classroom else None
    level = find_answer_level(experiment, subject)
    if level and level.get('answer'):
        return json.dumps({'title': subject, 'kind': 'choice',
                           'answer': level['answer']}, ensure_ascii=False, indent=2)
    return None


def local_mdj(hw_name, subject, step):
    base = resolve_answer_base(hw_name)
    if not base:
        return None, None
    mdj = collect_mdj(base)
    path = mdj.get(subject) or (mdj.get(step) if step is not None else None)
    if not path:
        return None, None
    try:
        return Path(path).read_text(encoding='utf-8'), str(path)
    except OSError:
        return None, None


def _recorded_level(answers, code, course_name, hw_name, subject):
    """answers.json 里记录的这道关卡（有记录才返回）。"""
    classroom = _find_classroom(answers, code, course_name)
    if not classroom:
        return None
    experiment = match_homework(hw_name, classroom.get('experiments', []))
    if not experiment:
        return None
    return find_answer_level(experiment, subject)


def answer_for_level(detail, answers, code, course_name, hw_name,
                     *, include_prepared=True):
    """返回 (content, kind, target_path, source)，找不到返回 (None, kind, path, '')。

    题型判定：本地题库记过的题型优先（answers.json 里的是实测定型），
    没记录时才退回平台详情推断。平台详情在新建尝试的头几秒是残缺的，
    拿它猜题型会把明明存着答案的关卡判成 unknown、归档成空。

    include_prepared=False 时忽略 prepared/（预生成的未验证 AI 答案）。prepare.py
    自己判断「要不要重新生成」时需要这样排除，否则会把刚生成的答案当成已有答案。
    """
    challenge = detail.get('challenge') or {}
    subject = (challenge.get('subject') or '').strip()
    recorded = _recorded_level(answers, code, course_name, hw_name, subject)
    kind = levelmod.recorded_kind(recorded.get('kind') if recorded else None)
    if not kind:
        kind = detect_kind(detail)
    target, step = extract_target(challenge.get('path'), challenge.get('task_pass'))
    if not target:
        target = attempts.attempt_target(hw_name, subject) or None
        if target:
            step_m = re.search(r'step(?:detail)?_?(\d+)', target)
            step = int(step_m.group(1)) if step_m else step
    path = target or (split_paths(challenge.get('path')) or [None])[0]

    content = None
    source = ''
    if kind == levelmod.KIND_CHOICE:
        content = local_choice(answers, code, course_name, hw_name, subject)
        source = 'answers.json' if content else ''
        path = 'answer.json'
    elif kind == levelmod.KIND_CODE:
        content = local_code(answers, code, course_name, hw_name, subject)
        source = 'answers.json' if content else ''
    elif kind == levelmod.KIND_GRAPHIC or is_graphic(detail):
        kind = 'uml'
        content, source = local_mdj(hw_name, subject, step)

    if not content:
        # solutions/ 只存「平台确认已通关」的答案，比 attempts/（存的是失败尝试）可靠，
        # 所以夹在两者之间：answers.json/answer/ → solutions/ → attempts/。
        saved = solutions.load_solution(hw_name, subject)
        if saved and saved[1].strip():
            content, source = saved[1], str(saved[0])
    if not content:
        saved = attempts.load_attempt(hw_name, subject, include_passed=True)
        if saved:
            content, source = saved[1], str(saved[0])
    if not content and include_prepared:
        # prepared/ 是「还没交给平台验证」的 AI 预生成答案，排在最后：
        # 只有前面几个可信来源都没有答案时才用，避免盖掉真实测过的结果。
        saved = prepared.load_prepared(hw_name, subject)
        if saved and saved[1].strip():
            content, source = saved[1], str(saved[0])
    return content, kind, path, source
