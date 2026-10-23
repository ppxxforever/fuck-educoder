"""只读诊断：打印一个 UML 绘制关卡的关键提交相关字段。"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from educoder_reminder.client import open_client
from educoder_reminder.errors import CollectionError

FIELDS = [
    'evaluation_method', 'code_editor', 'mirror_name', 'mirror_description',
    'mirror_description_multi', 'picture', 'vnc_url', 'wss_url', 'tomcat_url',
    'web_route', 'redirect_method', 'show_style', 'hideLeftPanel', 'hide_width_rate',
    'is_embed_third', 'embed_third_link', 'open_self_run', 'open_local_evaluate',
    'local_evaluate_languages', 'testCasesExp', 'testCasesType', 'test_sets_count',
    'is_last_game', 'is_submit_test_result', 'sec_key',
]


async def main(gid: str):
    async with open_client() as client:
        detail = await client.get(f'/api/tasks/{gid}.json', {}, strict_status=False)
        game = detail.get('game') or {}
        challenge = detail.get('challenge') or {}
        myshixun = detail.get('myshixun') or {}
        user = detail.get('user') or {}
        envs = detail.get('shixun_environments') or []
        print('===== challenge =====')
        print(json.dumps(challenge, ensure_ascii=False, indent=2))
        print('\n===== 关键字段 =====')
        for k in FIELDS:
            print(f'{k} = {json.dumps(detail.get(k), ensure_ascii=False)}')
        print('\n===== game =====')
        print(json.dumps(game, ensure_ascii=False, indent=2))
        print('\n===== myshixun =====')
        print(json.dumps(myshixun, ensure_ascii=False, indent=2))
        print('\n===== user =====')
        print(json.dumps(user, ensure_ascii=False, indent=2))
        print('\n===== shixun_environments =====')
        print(json.dumps(envs, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    gid = sys.argv[1]
    try:
        asyncio.run(main(gid))
    except CollectionError as exc:
        raise SystemExit(str(exc)) from None
