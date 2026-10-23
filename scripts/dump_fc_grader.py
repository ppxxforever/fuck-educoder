"""抓取系统流程图两关的评测脚本，打印元素/连线检查。
用法：uv run python scripts/dump_fc_grader.py
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from educoder_reminder.client import open_client
from educoder_reminder.submit_uml import _ssh_connect, _trigger_eval

SCAN = (
    'for f in $(find /data/workspace/myshixun/secret -name "*.py" 2>/dev/null); do '
    's=$(wc -c < "$f"); if [ "$s" != "0" ]; then echo "### $f"; '
    'grep -Eo "analyze_[a-z_]+[(][^)]*[)]" "$f" | head -30; '
    'echo "--- ids ---"; grep -Eo "[a-z_]+_id = get_id[(][^)]*[)]" "$f" | head -30; '
    'grep -Eo "analyze_line[(][^)]*[)]" "$f" | head -30; fi; done'
)


async def main():
    targets = [('y72zvfgqs83t', 2), ('ncexr3uz4klo', 3)]
    async with open_client() as client:
        for gid, step in targets:
            d = await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False)
            ms = d.get('myshixun') or {}
            game = d.get('game') or {}
            env = (d.get('shixun_environments') or [{}])[0]
            hw_id = d.get('homework_common_id')
            params = {
                'shixun_environment_id': env.get('shixun_environment_id', 0),
                'tab_type': env.get('tab_type', 3),
                'game_id': game.get('id', 0),
            }
            if hw_id:
                params['homework_common_id'] = hw_id
            conn = (await client.get(
                f'/api/myshixuns/{ms["identifier"]}/start.json', params)).get('data') or {}
            if not conn.get('ssh_address'):
                print(f'{gid}: 环境启动失败 {conn}')
                continue
            ssh = _ssh_connect(conn)
            await _trigger_eval(client, d, hw_id, gid)
            got = None
            for _ in range(20):
                _, o, _ = ssh.exec_command(SCAN, timeout=25)
                txt = o.read().decode('utf-8', 'replace')
                if txt.strip():
                    got = txt
                    break
                await asyncio.sleep(2)
            print(f'===== step{step} ({gid}) =====')
            print(got[:2000] if got else '(未抓到)')
            print()
            ssh.close()


if __name__ == '__main__':
    asyncio.run(main())
