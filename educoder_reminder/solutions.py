"""已完成关卡的答案库：只保存平台确认 status==2 的答案。

目录结构与 attempts/ 一致，方便对照和复用：

    solutions/<实验名>/<关卡标题>/
        answer.py|.sql|.java|.mdj|.json
        meta.json   # 课堂、gid、远端路径、来源、完成时间

与 attempts/ 的区别：
  - attempts/ 存的是「没提交成功」的尝试，供修改后重交；
  - solutions/ 存的是「已完成（status==2）」的答案，供复用/备份。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .attempts import ANSWER_SUFFIXES, answer_suffix, safe_component

ROOT = Path(__file__).resolve().parents[1]
SOLUTIONS_DIR = ROOT / 'solutions'
BEIJING = ZoneInfo('Asia/Shanghai')


def experiment_dir(experiment: str) -> Path:
    return SOLUTIONS_DIR / safe_component(experiment, '未命名实验')


def level_dir(experiment: str, subject: str) -> Path:
    return experiment_dir(experiment) / safe_component(subject, '未命名关卡')


def save_solution(experiment: str, subject: str, content: str, *,
                  path: str | None = None, gid: str = '', kind: str = '',
                  classroom: str = '', source: str = '') -> Path | None:
    """保存一份已完成的答案（覆盖同关卡旧文件）。内容为空则不保存。"""
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
    meta = {
        'experiment': experiment,
        'subject': subject,
        'gid': gid,
        'path': path or '',
        'kind': kind,
        'classroom': classroom,
        'source': source,
        'completed_at': datetime.now(BEIJING).isoformat(timespec='seconds'),
        'file': target.name,
    }
    (target_dir / 'meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return target


def solution_path(experiment: str, subject: str) -> Path | None:
    target_dir = level_dir(experiment, subject)
    if not target_dir.is_dir():
        return None
    for suffix in ANSWER_SUFFIXES:
        candidate = target_dir / f'answer{suffix}'
        if candidate.is_file():
            return candidate
    return None


def load_solution(experiment: str, subject: str) -> tuple[Path, str] | None:
    path = solution_path(experiment, subject)
    if path is None:
        return None
    try:
        return path, path.read_text(encoding='utf-8')
    except OSError:
        return None


def list_solutions() -> list[dict]:
    out = []
    if not SOLUTIONS_DIR.is_dir():
        return out
    for experiment in sorted(SOLUTIONS_DIR.iterdir()):
        if not experiment.is_dir():
            continue
        for level in sorted(experiment.iterdir()):
            if not level.is_dir():
                continue
            try:
                meta = json.loads((level / 'meta.json').read_text(encoding='utf-8'))
            except (OSError, ValueError):
                meta = {}
            answer = solution_path(experiment.name, level.name)
            out.append({
                'experiment': experiment.name,
                'subject': level.name,
                'kind': meta.get('kind', ''),
                'completed_at': meta.get('completed_at', ''),
                'file': answer.name if answer else '',
            })
    return out
