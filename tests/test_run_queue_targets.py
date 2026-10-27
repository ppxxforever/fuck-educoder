"""多账号队列的「每个账号单独指定课程」测试（不联网、不写真实 .env）。"""
import argparse
import asyncio
import importlib.util
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from educoder_reminder import submit_all

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('run_queue_under_test',
                                              ROOT / 'scripts' / 'run_queue.py')
rq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rq)


def run_args(**overrides):
    values = dict(classroom=None, limit=None, poll_timeout=120, experiment=None,
                  no_ai=False, delay=0.0)
    values.update(overrides)
    return argparse.Namespace(**values)


class QueueTargetsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.accounts = self.root / 'accounts.json'
        self.accounts.write_text(json.dumps([
            {'account': 'a1', 'password': 'p1', 'note': '',
             'classrooms': ['c1', '数据库']},
            {'account': 'a2', 'password': 'p2', 'note': ''},
        ], ensure_ascii=False), encoding='utf-8')
        for target, value in (
            ('ACCOUNTS', self.accounts),
            ('STATE', self.root / 'queue_state.json'),
            ('ENV_PATH', self.root / '.env'),
            ('AUTH_DB', self.root / 'auth.sqlite3'),
            ('activate_account', lambda *a, **k: None),
            ('clear_login_limit', lambda *a, **k: 0),
        ):
            patcher = mock.patch.object(rq, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def read_accounts(self):
        return json.loads(self.accounts.read_text(encoding='utf-8'))

    def test_classrooms_of(self):
        self.assertEqual(rq.classrooms_of({'classrooms': ['c1', ' c1 ', '', 'c2']}),
                         ['c1', 'c2'])
        self.assertEqual(rq.classrooms_of({}), [])
        self.assertEqual(rq.classrooms_of({'classrooms': 'oops'}), [])

    async def test_run_one_uses_account_classrooms(self):
        calls = []

        async def fake_run_all(**kwargs):
            calls.append(kwargs['classroom_filter'])
            return {'submitted': 1, 'failed': 0, 'skipped_passed': 0}

        state = {}
        with mock.patch.object(submit_all, 'run_all', fake_run_all):
            ok = await rq.run_one('a1', 'p1', run_args(), state, ['c1', '数据库'])
            self.assertTrue(ok)
            # 命令行 --classroom 覆盖单个账号自己的设置
            await rq.run_one('a1', 'p1', run_args(classroom=['override']),
                             state, ['c1', '数据库'])
            # 账号没配课程 = 全部课堂（None）
            await rq.run_one('a2', 'p2', run_args(), state, [])
        self.assertEqual(calls, [['c1', '数据库'], ['override'], None])
        self.assertEqual(state['a1']['status'], 'done')
        self.assertEqual(state['a1']['submitted'], 1)

    async def test_run_one_failure_isolated(self):
        async def boom(**kwargs):
            raise RuntimeError('密码错误')

        state = {}
        with mock.patch.object(submit_all, 'run_all', boom):
            ok = await rq.run_one('a1', 'p1', run_args(), state, [])
        self.assertFalse(ok)
        self.assertEqual(state['a1']['status'], 'failed')
        self.assertIn('密码错误', state['a1']['error'])

    def test_set_classrooms_cli(self):
        rq.cmd_set_classrooms(
            argparse.Namespace(set_classrooms='a2', classroom=['c9'], encrypt=False))
        self.assertEqual(self.read_accounts()[1]['classrooms'], ['c9'])
        # 不传 --classroom 表示恢复全部课堂
        rq.cmd_set_classrooms(
            argparse.Namespace(set_classrooms='a2', classroom=None, encrypt=False))
        self.assertNotIn('classrooms', self.read_accounts()[1])
        with self.assertRaises(SystemExit):
            rq.cmd_set_classrooms(
                argparse.Namespace(set_classrooms='nope', classroom=['c1'],
                                   encrypt=False))

    def test_add_with_classrooms(self):
        rq.cmd_add(argparse.Namespace(add='a3', password='p3', note='新',
                                      classroom=['c1'], encrypt=False))
        accounts = self.read_accounts()
        self.assertEqual(accounts[2]['classrooms'], ['c1'])


if __name__ == '__main__':
    unittest.main()
