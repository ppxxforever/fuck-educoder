"""预生成的 AI 答案缓存：只写本地，不提交、不触发评测。

目录结构与 solutions/、attempts/ 一致：

    prepared/<实验名>/<关卡标题>/
        answer.py|.sql|.mdj|.json   # 预生成的答案（提交时直接复用）
        question.md                 # 爬到的题目原文（题干 / 选项 / 目标文件）
        meta.json                   # 课堂、gid、题型、目标路径、来源、生成时间

三个答案库的分工：
  - solutions/ 只存平台确认已通关（status==2）的答案，最可信；
  - attempts/  存提交失败的尝试，带平台反馈，供人工修改后重交；
  - prepared/  存「还没交给平台验证」的 AI 预生成答案，用于把 AI 调用提前集中做完。

复用顺序（见 answer_sources.answer_for_level / submit.py）：
  answers.json / answer/ → solutions/ → attempts/ → prepared/ → 现场调用 AI。

prepared/ 属于可再生的中间产物，默认不进 git（见 .gitignore）。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .attempts import ANSWER_SUFFIXES, answer_suffix, safe_component

ROOT = Path(__file__).resolve().parents[1]
PREPARED_DIR = ROOT / 'prepared'
BEIJING = ZoneInfo('Asia/Shanghai')


def experiment_dir(experiment: str) -> Path:
    return PREPARED_DIR / safe_component(experiment, '未命名实验')


def level_dir(experiment: str, subject: str) -> Path:
    return experiment_dir(experiment) / safe_component(subject, '未命名关卡')


def _read_meta(target_dir: Path) -> dict:
    try:
        data = json.loads((target_dir / 'meta.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_meta(target_dir: Path, meta: dict) -> None:
    try:
        (target_dir / 'meta.json').write_text(
            json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    except OSError:
        pass


def save_question(experiment: str, subject: str, text: str, *,
                  gid: str = '', kind: str = '', path: str = '',
                  classroom: str = '') -> Path | None:
    """保存爬到的题目原文（question.md），供人工核对和 AI 提示复用。"""
    if not text or not text.strip() or not experiment or not subject:
        return None
    target_dir = level_dir(experiment, subject)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / 'question.md'
    target.write_text(text.rstrip() + '\n', encoding='utf-8')
    meta = _read_meta(target_dir)
    meta.update({
        'experiment': experiment,
        'subject': subject,
        'gid': gid or meta.get('gid', ''),
        'kind': kind or meta.get('kind', ''),
        'path': path or meta.get('path', ''),
        'classroom': classroom or meta.get('classroom', ''),
        'question': target.name,
        'crawled_at': datetime.now(BEIJING).isoformat(timespec='seconds'),
    })
    _write_meta(target_dir, meta)
    return target


def save_prepared(experiment: str, subject: str, content: str, *,
                  path: str | None = None, gid: str = '', kind: str = '',
                  classroom: str = '', source: str = 'ai-prepare') -> Path | None:
    """保存一份预生成的答案（覆盖该关卡旧的 answer.*）；内容为空则不保存。"""
    if not content or not content.strip() or not experiment or not subject:
        return None
    target_dir = level_dir(experiment, subject)
    target_dir.mkdir(parents=True, exist_ok=True)
    for old in target_dir.glob('answer.*'):
        try:
            old.unlink()
        except OSError:
            pass
    target = target_dir / f'answer{answer_suffix(path, kind)}'
    target.write_text(content, encoding='utf-8')
    meta = _read_meta(target_dir)
    # 重新生成后清掉「提交未通过」标记，新答案重新参与复用
    for key in ('rejected', 'rejected_at', 'rejected_reason'):
        meta.pop(key, None)
    meta.update({
        'experiment': experiment,
        'subject': subject,
        'gid': gid or meta.get('gid', ''),
        'path': path or meta.get('path', ''),
        'kind': kind or meta.get('kind', ''),
        'classroom': classroom or meta.get('classroom', ''),
        'source': source,
        'file': target.name,
        'prepared_at': datetime.now(BEIJING).isoformat(timespec='seconds'),
    })
    _write_meta(target_dir, meta)
    return target


def mark_rejected(experiment: str, subject: str, reason: str = '') -> None:
    """标记这份预生成答案「提交没通过」，提交链不再复用它。

    不删文件（留着方便人工看），只把 meta.json 标成 rejected：
    之后 prepare.py 会认为这一关没有预生成答案，重新生成一份（覆盖时自动清标记）。
    否则一份错误的 AI 答案会被每轮提交反复重交，永远轮不到现场 AI 重做。
    """
    target_dir = level_dir(experiment, subject)
    meta = _read_meta(target_dir)
    meta['rejected'] = True
    meta['rejected_at'] = datetime.now(BEIJING).isoformat(timespec='seconds')
    if reason:
        meta['rejected_reason'] = reason
    _write_meta(target_dir, meta)


def is_rejected(experiment: str, subject: str) -> bool:
    return bool(_read_meta(level_dir(experiment, subject)).get('rejected'))


def prepared_path(experiment: str, subject: str,
                  suffixes: tuple[str, ...] | None = None,
                  *, include_rejected: bool = False) -> Path | None:
    """返回该关卡预生成的 answer.* 路径（不存在返回 None）。

    默认忽略被标记为 rejected（提交未通过）的答案，让提交链回落到 AI 重做。
    """
    target_dir = level_dir(experiment, subject)
    if not target_dir.is_dir():
        return None
    if not include_rejected and _read_meta(target_dir).get('rejected'):
        return None
    allowed = tuple(s.lower() for s in (suffixes or ANSWER_SUFFIXES))
    for suffix in ANSWER_SUFFIXES:
        if suffix not in allowed:
            continue
        candidate = target_dir / f'answer{suffix}'
        if candidate.is_file():
            return candidate
    return None


def load_prepared(experiment: str, subject: str,
                  suffixes: tuple[str, ...] | None = None,
                  *, include_rejected: bool = False) -> tuple[Path, str] | None:
    path = prepared_path(experiment, subject, suffixes,
                         include_rejected=include_rejected)
    if path is None:
        return None
    try:
        return path, path.read_text(encoding='utf-8')
    except OSError:
        return None


def prepared_target(experiment: str, subject: str) -> str:
    """预生成答案记录的目标文件路径（图形题可能只能从这里拿到保存路径）。"""
    return str(_read_meta(level_dir(experiment, subject)).get('path') or '').strip()


def list_prepared() -> list[dict]:
    out = []
    if not PREPARED_DIR.is_dir():
        return out
    for experiment in sorted(PREPARED_DIR.iterdir()):
        if not experiment.is_dir():
            continue
        for level in sorted(experiment.iterdir()):
            if not level.is_dir():
                continue
            meta = _read_meta(level)
            answer = prepared_path(experiment.name, level.name,
                                   include_rejected=True)
            out.append({
                'experiment': experiment.name,
                'subject': level.name,
                'kind': meta.get('kind', ''),
                'prepared_at': meta.get('prepared_at', ''),
                'file': answer.name if answer else '',
                'rejected': bool(meta.get('rejected')),
            })
    return out
