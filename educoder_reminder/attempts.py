"""按实验保存「未提交成功」的答案脚本，方便人工修改后复用。

目录结构（每个实验一个文件夹，每个关卡一个子文件夹）：

    attempts/<实验名>/<关卡标题>/
        answer.py            # 最近一次尝试的答案（扩展名按原文件；UML 是 .mdj）
        feedback.txt         # 平台返回的编译/评测输出
        meta.json            # 课堂/关卡标识/时间/是否通过等

复用规则：
  - answers.json 里没有该关卡答案时，下次提交会优先读取这里的 answer.*；
  - 编辑 answer.* 即可复用，删除整个关卡文件夹可让工具重新用 AI 生成；
  - 提交通过后 meta.json 里的 passed 会更新为 true（文件保留作参考）。
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
ATTEMPTS_DIR = ROOT / 'attempts'
BEIJING = ZoneInfo('Asia/Shanghai')

# 可复用的答案脚本扩展名（.mdj 用于 UML/图形题）
ANSWER_SUFFIXES = (
    '.py', '.sql', '.java', '.c', '.h', '.cpp', '.cc', '.cs', '.js', '.ts',
    '.go', '.rs', '.php', '.rb', '.sh', '.m', '.txt', '.mdj', '.json',
)
CODE_SUFFIXES = tuple(s for s in ANSWER_SUFFIXES if s not in ('.mdj', '.json'))


def content_sha256(content: str) -> str:
    """答案内容的 sha256，用于判断存档是否和上次失败时一模一样。"""
    return hashlib.sha256(str(content or '').encode('utf-8')).hexdigest()


def last_failed_hash(experiment: str, subject: str) -> str:
    """存档 meta 里记录的上次失败答案哈希（没有则返回空串）。"""
    try:
        meta = json.loads((level_dir(experiment, subject) / 'meta.json')
                          .read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return ''
    return str(meta.get('answer_sha256') or '')


def safe_component(text: str, fallback: str = 'unnamed') -> str:
    """把实验名/关卡标题变成安全的目录名。"""
    text = str(text or '').strip()
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', text)
    text = re.sub(r'\s+', ' ', text).strip(' .')
    return (text or fallback)[:80]


def experiment_dir(experiment: str) -> Path:
    return ATTEMPTS_DIR / safe_component(experiment, '未命名实验')


def level_dir(experiment: str, subject: str) -> Path:
    return experiment_dir(experiment) / safe_component(subject, '未命名关卡')


def answer_suffix(path: str | None, kind: str) -> str:
    return _suffix(path, kind)


def _suffix(path: str | None, kind: str) -> str:
    if path:
        suffix = Path(str(path)).suffix.lower()
        if suffix in ANSWER_SUFFIXES:
            return suffix
    return '.mdj' if kind == 'uml' else '.txt'


def save_attempt(experiment: str, subject: str, content: str, *,
                 path: str | None = None, feedback: str = '', gid: str = '',
                 kind: str = 'code', classroom: str = '', passed: bool = False,
                 extra: dict | None = None) -> Path:
    """保存一次答案尝试（覆盖该关卡上一次的 answer.*）。"""
    if not content or not content.strip():
        raise ValueError('答案内容为空，未保存')
    target_dir = level_dir(experiment, subject)
    target_dir.mkdir(parents=True, exist_ok=True)
    for old in target_dir.glob('answer.*'):
        try:
            old.unlink()
        except OSError:
            pass
    suffix = _suffix(path, kind)
    target = target_dir / f'answer{suffix}'
    target.write_text(content, encoding='utf-8')
    (target_dir / 'missing.txt').unlink(missing_ok=True)
    if feedback is not None:
        (target_dir / 'feedback.txt').write_text((feedback or '').rstrip() + '\n',
                                                 encoding='utf-8')
    meta = {
        'experiment': experiment,
        'subject': subject,
        'gid': gid,
        'path': path or '',
        'kind': kind,
        'classroom': classroom,
        'passed': bool(passed),
        'answer_sha256': content_sha256(content),
        'updated_at': datetime.now(BEIJING).isoformat(timespec='seconds'),
        'file': target.name,
    }
    if extra:
        meta.update(extra)
    (target_dir / 'meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return target


def ensure_level(experiment: str, subject: str, *, gid: str = '', path: str = '',
                 kind: str = '', classroom: str = '', note: str = '') -> Path:
    """确保关卡文件夹存在（没有本地答案时也建一个，方便人工补答案）。"""
    target_dir = level_dir(experiment, subject)
    target_dir.mkdir(parents=True, exist_ok=True)
    meta_path = target_dir / 'meta.json'
    try:
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        meta = {}
    meta.update({
        'experiment': experiment,
        'subject': subject,
        'gid': gid or meta.get('gid', ''),
        'path': path or meta.get('path', ''),
        'kind': kind or meta.get('kind', ''),
        'classroom': classroom or meta.get('classroom', ''),
        'updated_at': datetime.now(BEIJING).isoformat(timespec='seconds'),
    })
    meta.setdefault('passed', False)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n',
                         encoding='utf-8')
    if note:
        (target_dir / 'missing.txt').write_text(note.rstrip() + '\n', encoding='utf-8')
    return target_dir


def _is_passed(experiment: str, subject: str) -> bool:
    try:
        meta = json.loads((level_dir(experiment, subject) / 'meta.json')
                          .read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return bool(meta.get('passed'))


def attempt_path(experiment: str, subject: str,
                 suffixes: tuple[str, ...] | None = None,
                 include_passed: bool = False) -> Path | None:
    """返回已保存的 answer.* 路径（不存在返回 None）。

    默认忽略已经提交通过的存档，避免下次运行又用回旧答案。
    """
    target_dir = level_dir(experiment, subject)
    if not target_dir.is_dir():
        return None
    if not include_passed and _is_passed(experiment, subject):
        return None
    allowed = tuple(s.lower() for s in (suffixes or ANSWER_SUFFIXES))
    for suffix in ANSWER_SUFFIXES:
        if suffix not in allowed:
            continue
        candidate = target_dir / f'answer{suffix}'
        if candidate.is_file():
            return candidate
    return None


def load_attempt(experiment: str, subject: str,
                 suffixes: tuple[str, ...] | None = None,
                 include_passed: bool = False) -> tuple[Path, str] | None:
    path = attempt_path(experiment, subject, suffixes, include_passed)
    if path is None:
        return None
    try:
        return path, path.read_text(encoding='utf-8')
    except OSError:
        return None


def attempt_target(experiment: str, subject: str) -> str:
    """关卡没有 challenge.path 时，可从 target.txt 或 meta.json 的 path 读取保存路径。"""
    target_dir = level_dir(experiment, subject)
    target_file = target_dir / 'target.txt'
    if target_file.is_file():
        try:
            text = target_file.read_text(encoding='utf-8').strip()
        except OSError:
            text = ''
        if text:
            return text
    try:
        meta = json.loads((target_dir / 'meta.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return ''
    return str(meta.get('path') or '').strip()


def mark_passed(experiment: str, subject: str) -> None:
    """提交通过后更新 meta.json（文件保留，方便以后复用）。"""
    meta_path = level_dir(experiment, subject) / 'meta.json'
    if not meta_path.is_file():
        return
    try:
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        meta = {}
    meta['passed'] = True
    meta['passed_at'] = datetime.now(BEIJING).isoformat(timespec='seconds')
    try:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n',
                             encoding='utf-8')
    except OSError:
        pass


def list_attempts() -> list[dict]:
    """列出所有已保存的尝试（用于人工检查）。"""
    out = []
    if not ATTEMPTS_DIR.is_dir():
        return out
    for experiment in sorted(ATTEMPTS_DIR.iterdir()):
        if not experiment.is_dir():
            continue
        for level in sorted(experiment.iterdir()):
            if not level.is_dir():
                continue
            meta_path = level / 'meta.json'
            try:
                meta = json.loads(meta_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                meta = {}
            answers = [p for p in level.glob('answer.*') if p.is_file()]
            out.append({
                'experiment': experiment.name,
                'subject': level.name,
                'passed': bool(meta.get('passed')),
                'updated_at': meta.get('updated_at', ''),
                'file': answers[0].name if answers else '',
            })
    return out
