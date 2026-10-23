"""只读诊断：打印某实验的完整关卡链，观察 UML 绘制题的 challenge 结构。

用法（在项目根目录）：
  uv run python scripts/diag_uml.py "面向对象分析之用例图"
  uv run python scripts/diag_uml.py "面向对象分析之类图"
不提交任何内容，仅 GET 平台接口。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from educoder_reminder.client import open_client
from educoder_reminder.errors import CollectionError
from educoder_reminder.submit import (
    fetch_homework_rows, match_homework, resolve_entry, walk_prev_to_head,
)


async def main(target_name: str):
    async with open_client() as client:
        # 课堂 code 固定为软件工程导论2026年下半年
        code = '2i6ng7vp'
        rows = await fetch_homework_rows(client, code)
        print(f'课堂 {code} 共 {len(rows)} 条实验作业。')
        target = target_name
        candidates = [r for r in rows if target in (r.get('name') or '')]
        if not candidates:
            print('未找到含该名称的实验，可用名称：')
            for r in rows:
                print('  ', r.get('name'), '| shixun=', r.get('shixun_identifier'), '| hw=', r.get('homework_id'))
            return
        for hw in candidates:
            print('\n===== 实验：', hw.get('name'), '=====')
            print('homework_id=', hw.get('homework_id'), 'shixun_identifier=', hw.get('shixun_identifier'))
            shixun_id = hw.get('shixun_identifier')
            hw_id = hw.get('homework_id')
            entry = await resolve_entry(client, shixun_id, hw_id)
            print('入口 game_identifier=', entry)
            if not entry:
                continue
            ordered, cache = await walk_prev_to_head(client, entry)
            print('关卡链长度=', len(ordered))
            # 沿 next_game 完整遍历（不只 prev 回退），打印每个关卡
            seen = set()
            queue = list(ordered)
            while queue:
                gid = queue.pop(0)
                if gid in seen:
                    continue
                seen.add(gid)
                detail = cache.get(gid) or await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False)
                game = detail.get('game') or {}
                challenge = detail.get('challenge') or {}
                subject = (challenge.get('subject') or '').strip()
                path = challenge.get('path')
                ctype = challenge.get('challenge_type') or challenge.get('type') or challenge.get('kind')
                print(f'\n--- {subject} ({gid}) ---')
                print(f'  game.status={game.get("status")!r} game.identifier={game.get("identifier")!r}')
                print(f'  challenge.id={challenge.get("id")!r}')
                print(f'  challenge.path={path!r}')
                print(f'  challenge keys={sorted(challenge.keys())}')
                print(f'  detail keys={sorted(detail.keys())}')
                nxt = detail.get('next_game')
                if nxt and str(nxt) not in seen:
                    queue.append(str(nxt))


if __name__ == '__main__':
    name = sys.argv[1] if len(sys.argv) > 1 else '面向对象分析之用例图'
    try:
        asyncio.run(main(name))
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
