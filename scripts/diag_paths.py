"""只读诊断：提取每个 UML 绘制关卡的保存路径指令与 challenge.path。

用于确认 answer/ 里的 .mdj 应该写到工作区的哪个路径。
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from educoder_reminder.client import open_client
from educoder_reminder.errors import CollectionError
from educoder_reminder.submit import (
    fetch_homework_rows, resolve_entry, walk_prev_to_head,
)

SAVE_RE = re.compile(r'(保存到|保存至|保存文件到|保存到路径|存放|保存于)\s*([^\s，。；;]+(?:/[^\s，。；;]+)*)', re.I)
NAME_RE = re.compile(r'(命名为|名字为|命名为|文件名|格式为|命名为)\s*([^\s，。；;、]+)', re.I)


def extract_save(task_pass: str):
    """从 task_pass 里抓保存路径和文件名。"""
    if not task_pass:
        return None, None
    text = re.sub(r'<[^>]+>', ' ', task_pass)
    m = SAVE_RE.search(text)
    save = m.group(2) if m else None
    # 命名的文件名
    n = re.search(r'命名为\s*([A-Za-z0-9_]+)', text)
    name = n.group(1) if n else None
    fmt = re.search(r'格式为\s*([A-Za-z0-9_]+)', text)
    fmt = fmt.group(1) if fmt else None
    return save, (name, fmt)


async def main():
    async with open_client() as client:
        code = '2i6ng7vp'
        rows = await fetch_homework_rows(client, code)
        keywords = ['用例图', '类图', '活动图', '顺序图', '数据流图', '状态转换图',
                    '实体-联系图', '面向数据流的设计方法', '数据管理']
        for hw in rows:
            name = hw.get('name') or ''
            if not any(k in name for k in keywords):
                continue
            shixun_id = hw.get('shixun_identifier')
            hw_id = hw.get('homework_id')
            entry = await resolve_entry(client, shixun_id, hw_id)
            if not entry:
                print(f'\n== {name}：无入口 ==')
                continue
            ordered, cache = await walk_prev_to_head(client, entry)
            print(f'\n================ {name} ================')
            print(f'关卡数={len(ordered)}')
            queue = list(ordered)
            seen = set()
            idx = 0
            while queue:
                gid = queue.pop(0)
                if gid in seen:
                    continue
                seen.add(gid)
                detail = cache.get(gid) or await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False)
                challenge = detail.get('challenge') or {}
                subject = (challenge.get('subject') or '').strip()
                path = challenge.get('path')
                task_pass = challenge.get('task_pass') or ''
                save, (name_f, fmt) = extract_save(task_pass)
                if save or path:
                    idx += 1
                    print(f'\n[{idx}] {subject}')
                    print(f'    challenge.path = {path!r}')
                    print(f'    task_pass 保存 = {save!r}  命名={name_f!r} 格式={fmt!r}')
                nxt = detail.get('next_game')
                if nxt and str(nxt) not in seen:
                    queue.append(str(nxt))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
