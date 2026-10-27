"""--repair-status 参数的传递测试（不联网、不提交）。"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from educoder_reminder import submit_all


class FakeClient:
    username = 'tester'

    async def get(self, *args, **kwargs):
        return {}


class FakeClientContext:
    async def __aenter__(self):
        return FakeClient()

    async def __aexit__(self, *exc_info):
        return False


class SubmitRepairTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_all_forwards_repair_status(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        answers = Path(tmp.name) / 'answers.json'
        answers.write_text(json.dumps({'kind': 'class-answers', 'classrooms': []}),
                           encoding='utf-8')

        calls = []

        async def fake_choice(client, hw, experiment, apply, stats, poll, **kwargs):
            calls.append(('choice', kwargs.get('repair_status')))

        async def fake_uml(client, hw, apply, stats, poll, **kwargs):
            calls.append(('uml', kwargs.get('repair_status')))

        course = SimpleNamespace(identifier='c1', name='课堂', created_at='2026-09-01')

        async def fake_courses(client):
            return [course]

        async def fake_rows(client, code):
            return [{'name': '实验', 'homework_id': 1,
                     'shixun_finished_status': 0}]

        with mock.patch.multiple(
                submit_all,
                open_client=FakeClientContext,
                fetch_courses=fake_courses,
                fetch_homework_rows=fake_rows,
                process_choice_code=fake_choice,
                process_uml=fake_uml):
            stats = await submit_all.run_all(
                True, None, None, 10, None, False, False, False, answers,
                delay=0, repair_status=True)

        self.assertEqual(calls, [('choice', True), ('uml', True)])
        self.assertIn('skipped_passed', stats)

    async def test_run_all_defaults_to_no_repair(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        answers = Path(tmp.name) / 'answers.json'
        answers.write_text(json.dumps({'kind': 'class-answers', 'classrooms': []}),
                           encoding='utf-8')
        calls = []

        async def fake_choice(client, hw, experiment, apply, stats, poll, **kwargs):
            calls.append(kwargs.get('repair_status'))

        async def fake_uml(client, hw, apply, stats, poll, **kwargs):
            calls.append(kwargs.get('repair_status'))

        course = SimpleNamespace(identifier='c1', name='课堂', created_at='2026-09-01')

        async def fake_courses(client):
            return [course]

        async def fake_rows(client, code):
            return [{'name': '实验', 'homework_id': 1, 'shixun_finished_status': 0}]

        with mock.patch.multiple(
                submit_all,
                open_client=FakeClientContext,
                fetch_courses=fake_courses,
                fetch_homework_rows=fake_rows,
                process_choice_code=fake_choice,
                process_uml=fake_uml):
            await submit_all.run_all(
                True, None, None, 10, None, False, False, False, answers, delay=0)

        self.assertEqual(calls, [False, False])


if __name__ == '__main__':
    unittest.main()
