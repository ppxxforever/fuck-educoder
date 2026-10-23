"""只读 dry-run：把 UML 绘图关卡映射到 answer/ 里的 .mdj，打印完整提交计划。

不写任何文件、不触发评测，仅 GET 平台接口 + 读本地 answer/ 目录。
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from educoder_reminder.client import open_client
from educoder_reminder.errors import CollectionError
from educoder_reminder.submit import fetch_homework_rows, resolve_entry, walk_prev_to_head

ROOT = Path(__file__).resolve().parents[1]
ANSWER = ROOT / 'answer'
PREFIXES = [
    '/home/headless/Desktop/workspace/myshixun/',
    'workspace/myshixun/',
    'workspace/',
]

KEYWORDS = ['用例图', '类图', '活动图', '顺序图', '数据流图', '状态转换图',
            '实体-联系图', '面向数据流的设计方法', '数据管理', '模块结构图']


def strip_prefix(path: str) -> str:
    for p in PREFIXES:
        if p in path:
            return path.split(p, 1)[1]
    return path


def extract_target(challenge_path, task_pass):
    """返回 (workspace相对目录, 文件名)。可能为 None。"""
    text = re.sub(r'<[^>]+>', ' ', task_pass or '')
    dir_raw = None
    # 目录：task 里 “保存到“.../xxx/”目录下” 或 “保存到.../下”
    m = re.search(r'["“]([^"”]+)["”]\s*目录下', text)
    if m:
        dir_raw = m.group(1).strip()
    else:
        m = re.search(r'保存(?:到|至|于)?\s*["“]?([^"“”，。；;\s]+/下)', text)
        if m:
            dir_raw = m.group(1).rstrip('/下')
    # 文件名：命名为stepN + 格式为mdj
    name_m = re.search(r'命名为\s*([A-Za-z0-9_]+)', text)
    fmt_m = re.search(r'格式为\s*([A-Za-z0-9_]+)', text)
    filename = None
    if name_m:
        ext = fmt_m.group(1) if fmt_m else 'mdj'
        filename = f'{name_m.group(1)}.{ext}'
    elif dir_raw:
        # 结构化类没有“命名为”指令，文件名从目录名里的 step 号推导
        dm = re.search(r'step(?:_detail)?_?(\d+)', dir_raw)
        if dm:
            filename = f'step{dm.group(1)}.mdj'
    if dir_raw:
        return strip_prefix(dir_raw.strip('/')) + '/', filename
    # 兜底：用 challenge.path（结构化类给的是 .../step_detail_N/.gitkeep 之类）
    if challenge_path:
        parts = [p for p in re.split(r'[；;]', challenge_path) if p.strip()]
        if parts:
            p = parts[0].strip()
            if p.endswith('.gitkeep'):
                d = p.rsplit('/', 1)[0] + '/'
                m = re.search(r'step(?:_detail)?_?(\d+)', d)
                fn = f'step{m.group(1)}.mdj' if m else None
                return d, fn
    return None, None


def answer_files(exp_name: str):
    """返回 answer/<exp>/ 下所有 .mdj 的 {step号: 相对路径}。"""
    base = ANSWER / exp_name
    out = {}
    if not base.is_dir():
        return out, None
    for f in sorted(base.rglob('*.mdj')):
        rel = f.relative_to(base)
        m = re.search(r'step_?(\d+)', rel.name)
        n = int(m.group(1)) if m else None
        if n is not None:
            out[n] = str(rel)
    return out, base


async def main():
    async with open_client() as client:
        rows = await fetch_homework_rows(client, '2i6ng7vp')
        total_matched = total_levels = 0
        for hw in rows:
            name = hw.get('name') or ''
            if not any(k in name for k in KEYWORDS):
                continue
            shixun_id = hw.get('shixun_identifier')
            hw_id = hw.get('homework_id')
            entry = await resolve_entry(client, shixun_id, hw_id)
            if not entry:
                continue
            ordered, cache = await walk_prev_to_head(client, entry)
            files, base = answer_files(name)
            print(f'\n===== {name} =====')
            print(f'answer 目录: {base}（{len(files)} 个 .mdj 按 step 号索引）')
            queue = list(ordered)
            seen = set()
            while queue:
                gid = queue.pop(0)
                if gid in seen:
                    continue
                seen.add(gid)
                detail = cache.get(gid) or await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False)
                game = detail.get('game') or {}
                challenge = detail.get('challenge') or {}
                subject = (challenge.get('subject') or '').strip()
                task_pass = challenge.get('task_pass') or ''
                d, fn = extract_target(challenge.get('path'), task_pass)
                if not d and not fn:
                    # 选择题等非绘图关卡
                    if '初体验' in subject or not task_pass:
                        print(f'  [跳过/选择题] {subject}（game.status={game.get("status")}）')
                    else:
                        print(f'  [无法解析路径] {subject}')
                    nxt = detail.get('next_game')
                    if nxt and str(nxt) not in seen:
                        queue.append(str(nxt))
                    continue
                m = re.search(r'step_?(\d+)', fn or '')
                step_n = int(m.group(1)) if m else None
                src = files.get(step_n) if step_n is not None else None
                total_levels += 1
                if src:
                    total_matched += 1
                    mark = '✔'
                else:
                    mark = '✗ 无对应 .mdj'
                print(f'  {mark} {subject}')
                print(f'       目标路径: {d}{fn or "?"}')
                print(f'       来源文件: answer/{name}/{src}' if src else '       来源文件: 未找到')
                nxt = detail.get('next_game')
                if nxt and str(nxt) not in seen:
                    queue.append(str(nxt))
        print(f'\n===== 汇总 =====')
        print(f'绘图关卡总数: {total_levels}')
        print(f'能匹配到 .mdj: {total_matched}')
        print(f'缺失 .mdj: {total_levels - total_matched}')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
