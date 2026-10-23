"""只读：枚举课堂里所有含「图形化/UML 绘图」关卡的实验，并匹配本地 .mdj。"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from educoder_reminder.client import open_client
from educoder_reminder.errors import CollectionError
from educoder_reminder.submit import fetch_homework_rows, resolve_entry, walk_prev_to_head

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ['/home/headless/Desktop/workspace/myshixun/', 'workspace/myshixun/', 'workspace/']

# 本地 .mdj 来源：answer/<实验名> 以及根目录 submit* 文件夹
def collect_local_mdj():
    sources = []
    for base in sorted((ROOT / 'answer').iterdir()) if (ROOT / 'answer').is_dir() else []:
        if base.is_dir():
            sources.append((base.name, base))
    for name in ('submit', 'submit_1', 'submit_2'):
        p = ROOT / name
        if p.is_dir():
            sources.append((name, p))
    return sources


def index_mdj(base: Path):
    idx = {}
    for f in sorted(base.rglob('*.mdj')):
        m = re.search(r'step_?(\d+)', f.name)
        if m:
            idx.setdefault(int(m.group(1)), []).append(str(f.relative_to(base)))
    return idx


def strip_prefix(path):
    for p in PREFIXES:
        if p in path:
            return path.split(p, 1)[1]
    return path


def target_path(challenge, task_pass):
    text = re.sub(r'<[^>]+>', ' ', task_pass or '')
    dir_raw = None
    m = re.search(r'["“]([^"”]+)["”]\s*目录下', text)
    if m:
        dir_raw = m.group(1).strip()
    else:
        m = re.search(r'保存(?:到|至|于)?\s*["“]?([^"“”，。；;\s]+/下)', text)
        if m:
            dir_raw = m.group(1).rstrip('/下')
    filename = None
    nm = re.search(r'命名为\s*([A-Za-z0-9_]+)', text)
    fm = re.search(r'格式为\s*([A-Za-z0-9_]+)', text)
    if nm:
        filename = f'{nm.group(1)}.{fm.group(1) if fm else "mdj"}'
    elif dir_raw:
        dm = re.search(r'step(?:_detail)?_?(\d+)', dir_raw)
        if dm:
            filename = f'step{dm.group(1)}.mdj'
    if dir_raw:
        return strip_prefix(dir_raw.strip('/')) + '/' + (filename or '?')
    return None


async def main():
    sources = collect_local_mdj()
    print('本地 .mdj 来源：')
    for name, base in sources:
        idx = index_mdj(base)
        print(f'  {name}: {sum(len(v) for v in idx.values())} 个 .mdj, step 号 {sorted(idx)}')
    print()
    async with open_client() as client:
        rows = await fetch_homework_rows(client, '2i6ng7vp')
        for hw in rows:
            name = hw.get('name') or ''
            shixun_id = hw.get('shixun_identifier')
            hw_id = hw.get('homework_id')
            entry = await resolve_entry(client, shixun_id, hw_id)
            if not entry:
                continue
            ordered, cache = await walk_prev_to_head(client, entry)
            queue = list(ordered)
            seen = set()
            drawing = []
            while queue:
                gid = queue.pop(0)
                if gid in seen:
                    continue
                seen.add(gid)
                d = cache.get(gid) or await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False)
                ch = d.get('challenge') or {}
                subj = (ch.get('subject') or '').strip()
                is_graphic = bool(d.get('vnc_url')) or bool((d.get('shixun_environments') or [{}])[0].get('vnc_url'))
                tp = target_path(ch.get('path'), ch.get('task_pass'))
                if is_graphic or (tp and tp.endswith('.mdj')):
                    game = d.get('game') or {}
                    drawing.append((subj, tp, game.get('status')))
                nxt = d.get('next_game')
                if nxt and str(nxt) not in seen:
                    queue.append(str(nxt))
            if drawing:
                print(f'== {name} ==  ({len(drawing)} 个绘图关卡)')
                for subj, tp, st in drawing:
                    print(f'    status={st}  {subj}  ->  {tp}')
                print()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
