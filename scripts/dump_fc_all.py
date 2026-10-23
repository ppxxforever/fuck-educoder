"""触发评测后把 secret/系统流程图/evaluate 下所有 demo*.py 全部抓回本地。"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from educoder_reminder.client import open_client
from educoder_reminder.submit_uml import _ssh_connect, _trigger_eval

OUT = Path('/tmp/fc_graders')


async def main():
    OUT.mkdir(exist_ok=True)
    async with open_client() as client:
        for gid in ('y72zvfgqs83t', 'ncexr3uz4klo'):
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
                print(f'{gid}: 启动失败')
                continue
            ssh = _ssh_connect(conn)
            await _trigger_eval(client, d, hw_id, gid)
            sftp = ssh.open_sftp()
            for _ in range(20):
                saved = 0
                for name in ('demo.py', 'demo2.py', 'demo3.py'):
                    remote = f'/data/workspace/myshixun/secret/系统流程图/evaluate/{name}'
                    try:
                        with sftp.file(remote, 'r') as f:
                            txt = f.read().decode('utf-8', 'replace')
                    except Exception:
                        continue
                    if txt.strip():
                        p = OUT / f'{gid}_{name}'
                        p.write_text(txt)
                        saved += 1
                if saved:
                    print(f'{gid}: 抓到 {saved} 个脚本')
                    break
                await asyncio.sleep(2)
            sftp.close()
            ssh.close()
    for p in sorted(OUT.glob('*.py')):
        print(f'--- {p.name} ({p.stat().st_size} 字节) ---')


if __name__ == '__main__':
    asyncio.run(main())
