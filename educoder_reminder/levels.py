"""关卡题型判定 + 实验收尾校验。

历史坑（2026-10-25「软件详细设计-2 / 面向数据流的设计方法-2 一直显示未提交」）：
`submit.py`（选择/代码题）和 `submit_uml.py`（图形题）各自遍历关卡链，
遇到「不归自己管」的关卡时都是静默 `continue`。一旦平台返回的关卡详情缺少题型线索
（图形化实验里的选择题有时只回 VNC 环境、不回 chooses / challenge.path），
两条链就会互相推诿：关卡既不提交也不报错，实验永远停在「未提交」，
而整轮运行的退出码仍然是 0，看起来一切正常。

本模块把这件事收口成三层：

1. `classify_level()` —— 全项目唯一的题型判定口径（choice / code / graphic / unknown），
   两个提交器都用它，不再各自 `detect_kind` / `is_graphic` 各判一套。
2. `Coverage` —— 处理过程中记录「每个关卡由谁认领、结果如何」，
   谁都没认领的就是漏洞。
3. `audit_experiment()` —— 每个实验跑完后独立复查关卡链，
   把「未通关」和「无人负责」的关卡明确报出来，不再依赖处理链自己走全。
"""
from __future__ import annotations

import re

KIND_CHOICE = 'choice'
KIND_CODE = 'code'
KIND_GRAPHIC = 'graphic'
KIND_UNKNOWN = 'unknown'

# answers.json / solutions 里记过的题型别名，统一折成上面的四种口径
_KIND_ALIASES = {
    KIND_CHOICE: KIND_CHOICE,
    KIND_CODE: KIND_CODE,
    KIND_GRAPHIC: KIND_GRAPHIC,
    'uml': KIND_GRAPHIC,
    'draw': KIND_GRAPHIC,
    'drawing': KIND_GRAPHIC,
}

OWNER_SUBMIT = 'submit'   # 选择/代码题链（educoder_reminder.submit）
OWNER_UML = 'uml'         # 图形题链（educoder_reminder.submit_uml）

UNOWNED_LABEL = '无人负责（工具漏处理）'


def level_title(detail) -> str:
    """关卡标题；平台偶尔不给 challenge.subject，用占位符避免日志丢信息。"""
    challenge = (detail or {}).get('challenge') or {}
    subject = (challenge.get('subject') or '').strip()
    return subject or '(未命名关卡)'


def has_environment(detail) -> bool:
    """关卡是否挂着图形化（VNC）环境。"""
    detail = detail or {}
    if detail.get('vnc_url'):
        return True
    envs = detail.get('shixun_environments') or []
    return bool(envs) and bool((envs[0] or {}).get('vnc_url'))


def recorded_kind(kind):
    """把记录过的题型规整成统一口径；认不出来返回 None。"""
    return _KIND_ALIASES.get(str(kind or '').strip().lower())


def detail_has_clues(detail) -> bool:
    """关卡详情里有没有「找答案 + 判题型」要用的线索。

    平台在换了一轮尝试之后（关卡 gid 整体变新），第一次 GET `/api/tasks/{gid}.json`
    常常只回 `game` + 精简版 `challenge`（没有 subject / chooses / path），
    几秒后才补全。这种「残缺详情」如果直接拿去用，标题匹配、题型判定、
    选择题答案切分会同时失效（2026-10-26「紧耦合&高内聚」就是这么翻车的：
    本地明明存着答案，却因为详情里没有标题被判成 unknown）。
    """
    detail = detail or {}
    challenge = detail.get('challenge') or {}
    if str(challenge.get('subject') or '').strip():
        return True
    if detail.get('chooses') or str(challenge.get('path') or '').strip():
        return True
    if has_environment(detail):
        return True
    game = detail.get('game') or {}
    # 两种响应形状都算（详情嵌 game；game_status 把字段放顶层）
    return game.get('status') == 2 or detail.get('status') == 2 \
        or bool(detail.get('test_sets'))


def classify_level(detail, recorded=None) -> str:
    """判定关卡题型，返回 choice / code / graphic / unknown。

    顺序是刻意设计的（踩过的坑都在注释里）：

    1. `answers.json` 记过题型的关卡直接采信 —— 实测定型比平台详情可靠；
    2. 有 `chooses` 就是选择题 —— 图形化实验里的选择题同样带 VNC 环境，
       不能因为「有环境」就当成绘图题（这正是漏提交的根因）；
    3. 有 `challenge.path` 且不带图形环境 → 代码题；
    4. 带图形环境或 `.mdj` 保存路径 → 图形题；
    5. 其余一律 `unknown` —— 调用方必须上报，不许静默跳过。
    """
    detail = detail or {}
    # 本地题库的题型优先（含 uml → graphic）：平台详情在新建尝试的头几秒是残缺的，
    # 靠残缺详情猜题型会把答案交错关卡。
    known = recorded_kind(recorded)
    if known:
        return known

    challenge = detail.get('challenge') or {}
    path = str(challenge.get('path') or '')
    if detail.get('chooses'):
        return KIND_CHOICE
    if path and not has_environment(detail) and not path.lower().endswith('.mdj'):
        return KIND_CODE
    if has_environment(detail) or path.lower().endswith('.mdj'):
        return KIND_GRAPHIC
    return KIND_UNKNOWN


def match_unlabelled_level(ordered, gid, levels, consumed):
    """平台不给关卡标题时，按关卡链顺序把本地记录对上号。

    只在「链上关卡数 == 本地记录数」时启用：数量对不上，顺序配对的假设就不成立，
    宁可报 unknown 也不能把 A 关的答案交到 B 关。
    """
    chain = [str(g) for g in (ordered or [])]
    if not levels or len(chain) != len(levels) or str(gid) not in chain:
        return None
    idx = chain.index(str(gid))
    if consumed.get(idx, 0) >= len(levels[idx].get('identifiers') or [1]):
        return None
    return idx


def find_recorded_level(recorded_levels, subject):
    """按标题在 answers.json 的 levels 里找记录（精确 → 忽略空白 → 包含匹配）。

    作为 submit.py 标题索引的兜底：平台标题带章节前缀、或多一层括号时，
    原来的索引匹配不到，记录里的答案就被白放着不用了。
    """
    target = re.sub(r'\s+', '', str(subject or ''))
    if not target:
        return None
    levels = list(recorded_levels or [])
    for level in levels:
        if re.sub(r'\s+', '', str(level.get('title') or '')) == target:
            return level
    for level in levels:
        title = re.sub(r'\s+', '', str(level.get('title') or ''))
        if title and (title in target or target in title):
            return level
    return None


class Coverage:
    """记录每个关卡被哪条链认领、结果如何。"""

    def __init__(self):
        self.records: dict[str, dict] = {}

    def note(self, gid, *, kind=None, subject=None, owner=None,
             action=None, passed=None) -> dict:
        gid = str(gid)
        record = self.records.setdefault(gid, {
            'gid': gid, 'subject': '', 'kind': KIND_UNKNOWN,
            'owner': None, 'action': None, 'passed': None,
        })
        if subject:
            record['subject'] = subject
        if kind:
            record['kind'] = kind
        if owner:
            record['owner'] = owner
        if action:
            record['action'] = action
        if passed is not None:
            record['passed'] = bool(passed)
        return record

    def get(self, gid):
        return self.records.get(str(gid))

    def unowned(self) -> list[dict]:
        """既没通过、也没有任何一条链认领的关卡 —— 这些就是会静默漏掉的关卡。"""
        return [r for r in self.records.values()
                if r['owner'] is None and not r['passed']]

    def __len__(self) -> int:
        return len(self.records)


async def audit_experiment(client, hw, coverage: Coverage | None = None,
                           limit: int = 200, entry=None) -> list[dict] | None:
    """独立复查一个实验的关卡链，返回未通关的关卡列表；无法复查时返回 None。

    不依赖两条提交链的遍历结果：从链头和当前入口各往后走一遍 `next_game`，
    因此「处理时没走到的关卡」也会被检查到。

    entry：由 submit_all 解析好的入口，与提交链共用同一个，避开「提交打在旧链、
    审计看新链」的窗口（平台换尝试时 gid 会整体换新）。

    区分两件事：
    - 「关卡没过」→ 正常报出来（owner/action 来自 Coverage）；
    - 「详情读不全」（payload 没有 challenge/game/chooses）→ 标 `unreadable`，
      由调用方计入 audit_error，不能当成未通过。2026-10-26 已证实同一个 gid
      可以在几秒内从残缺变完整，把残缺当成未通过会变成随机误报。
    """
    # 延迟导入：submit.py 模块级会 import levels，这里反向引用会造成循环导入。
    from .submit import detail_of, is_level_passed, resolve_entry, walk_prev_to_head

    entry = entry or await resolve_entry(client, hw.get('shixun_identifier'),
                                         hw.get('homework_id'))
    if not entry:
        return None
    ordered, cache = await walk_prev_to_head(client, entry)
    if not ordered:
        return None

    chain: dict[str, dict] = {}
    for start in (str(ordered[0]), str(entry)):
        cursor = start
        walked = set()
        while cursor and cursor not in walked and len(walked) < limit:
            walked.add(cursor)
            detail = await detail_of(client, cache, cursor)
            chain[cursor] = detail
            nxt = detail.get('next_game')
            cursor = str(nxt) if nxt else ''

    findings = []
    for gid, detail in chain.items():
        if is_level_passed(detail):
            continue
        record = (coverage.get(gid) if coverage is not None else None) or {}
        if not detail_has_clues(detail):
            # 读不到关卡详情 ≠ 关卡没过：再强刷一次，仍然残缺就报「无法校验」。
            cache.pop(gid, None)
            detail = await detail_of(client, cache, gid)
            if is_level_passed(detail):
                continue
            if not detail_has_clues(detail):
                findings.append({
                    'gid': gid,
                    'subject': record.get('subject') or level_title(detail),
                    'kind': record.get('kind') or KIND_UNKNOWN,
                    'owner': record.get('owner'),
                    'action': record.get('action'),
                    'unreadable': True,
                })
                continue
        findings.append({
            'gid': gid,
            'subject': record.get('subject') or level_title(detail),
            'kind': record.get('kind') or classify_level(detail),
            'owner': record.get('owner'),
            'action': record.get('action'),
        })
    return findings
