"""评测结果判定 / 评测状态接口的单元测试（不联网）。"""
import unittest
from unittest import mock

from educoder_reminder import submit
from educoder_reminder.submit import (
    _sig_equal, _traceback_clues, evaluation_sec_key, evaluate_sec_key,
    is_level_passed, verdict_signature, wait_for_completion, wait_for_verdict,
)


def detail(status=None, score=None, tests=None, evaluate_count=1):
    payload = {
        'game': {'status': status, 'final_score': score,
                 'evaluate_count': evaluate_count},
        'test_sets': tests or [],
    }
    return payload


def status_payload(status=None, tests=None, sec_key=None):
    payload = {'status': status, 'test_sets': tests or []}
    if sec_key is not None:
        payload['sec_key'] = sec_key
    return payload


class StubClient:
    """按顺序返回预设响应；用完后重复最后一个。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.paths = []

    async def get(self, path, params=None, *, strict_status=True):
        self.paths.append(path)
        if len(self.responses) > 1:
            return self.responses.pop(0)
        return self.responses[0]


async def no_sleep(*_args, **_kwargs):
    return None


class PassedTests(unittest.TestCase):
    def test_status_2(self):
        self.assertTrue(is_level_passed(detail(status=2)))
        self.assertTrue(is_level_passed(status_payload(status=2)))

    def test_score_without_status_is_not_pass(self):
        # final_score 是关卡分值，不是通关信号。实测「绘制销售额饼图」
        # status=0、final_score=100、唯一测试集 result=false（图像对比不一致）；
        # 只看分数会让没过的关卡被永久跳过（2026-10-26）。
        self.assertFalse(is_level_passed(detail(status=0, score=100)))
        self.assertFalse(is_level_passed(detail(
            status=0, score=100, tests=[{'result': False}])))
        # 测试集全过、只是 status 没同步，才算通过
        self.assertTrue(is_level_passed(status_payload(status=0, tests=[
            {'result': True, 'actual_output': 'ok'}])))

    def test_all_tests_true(self):
        self.assertTrue(is_level_passed(detail(
            status=0, score=0, tests=[{'result': True}, {'result': True}])))

    def test_any_test_false(self):
        self.assertFalse(is_level_passed(detail(
            status=0, score=0, tests=[{'result': True}, {'result': False}])))

    def test_unrated_tests_ignored(self):
        self.assertTrue(is_level_passed(detail(
            status=0, score=0, tests=[{'result': True}, {'result': None}])))
        self.assertFalse(is_level_passed(detail(status=0, score=0, tests=[
            {'result': None}])))

    def test_string_result_not_treated_as_true(self):
        # 平台理论上可能返回字符串；"false" 不能被当成通过
        self.assertFalse(is_level_passed(status_payload(
            status=0, tests=[{'result': 'false'}])))


class SignatureTests(unittest.TestCase):
    def test_both_shapes(self):
        nested = verdict_signature(detail(status=0, tests=[{'result': True}]))
        flat = verdict_signature(status_payload(status=0, tests=[{'result': True}]))
        self.assertEqual(nested[0], flat[0])
        self.assertEqual(nested[2], flat[2])

    def test_shapes_are_comparable(self):
        nested = verdict_signature(detail(status=0, tests=[{'result': True}]))
        flat = verdict_signature(status_payload(status=0, tests=[{'result': True}]))
        self.assertTrue(_sig_equal(nested, flat))
        other = verdict_signature(status_payload(status=0, tests=[{'result': False}]))
        self.assertFalse(_sig_equal(nested, other))
        self.assertFalse(_sig_equal(nested, None))

    def test_changes_with_result(self):
        before = verdict_signature(detail(status=0, tests=[{'result': True}]))
        after = verdict_signature(detail(status=0, tests=[{'result': False}]))
        self.assertNotEqual(before, after)


class EvaluationEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_sec_key_from_game_status(self):
        client = StubClient([status_payload(sec_key='abc123')])
        key = await evaluation_sec_key(client, 'gid1')
        self.assertEqual(key, 'abc123')
        self.assertEqual(client.paths, ['/api/tasks/gid1/game_status.json'])

    async def test_sec_key_prefers_detail(self):
        client = StubClient([status_payload(sec_key='from-status')])
        key = await evaluation_sec_key(client, 'gid1', {'sec_key': 'from-detail'})
        self.assertEqual(key, 'from-detail')
        self.assertEqual(client.paths, [])

    async def test_wait_for_verdict_polls_task_detail(self):
        client = StubClient([detail(status=1), detail(status=2)])
        with mock.patch.object(submit.asyncio, 'sleep', no_sleep):
            passed, data = await wait_for_verdict(client, 'gid1', timeout=30, poll=0)
        self.assertTrue(passed)
        self.assertEqual((data.get('game') or {}).get('status'), 2)
        self.assertTrue(all(p.endswith('/tasks/gid1.json') for p in client.paths))

    async def test_wait_for_verdict_failure(self):
        client = StubClient([detail(status=3)])
        with mock.patch.object(submit.asyncio, 'sleep', no_sleep):
            passed, _ = await wait_for_verdict(client, 'gid1', timeout=30, poll=0)
        self.assertFalse(passed)

    async def test_wait_for_verdict_ignores_baseline_until_changed(self):
        old = detail(status=0, tests=[{'result': True, 'actual_output': 'a'}],
                     evaluate_count=1)
        new = detail(status=0, tests=[{'result': False, 'actual_output': 'b'}],
                     evaluate_count=2)
        client = StubClient([old, old, new])
        with mock.patch.object(submit.asyncio, 'sleep', no_sleep):
            passed, _ = await wait_for_verdict(
                client, 'gid1', timeout=30, poll=0, baseline=verdict_signature(old))
        self.assertFalse(passed)

    async def test_identical_failure_after_new_evaluation_returns(self):
        # 同一个错误答案再交一次：test_sets 内容完全一样，但 evaluate_count 增加，
        # 必须立刻返回失败，不能一直等到 timeout。
        old = detail(status=0, tests=[{'result': False, 'actual_output': 'same'}],
                     evaluate_count=4)
        new = detail(status=0, tests=[{'result': False, 'actual_output': 'same'}],
                     evaluate_count=5)
        client = StubClient([new])
        with mock.patch.object(submit.asyncio, 'sleep', no_sleep):
            passed, _ = await wait_for_verdict(
                client, 'gid1', timeout=30, poll=0, baseline=verdict_signature(old))
        self.assertFalse(passed)
        self.assertEqual(len(client.paths), 1)

    async def test_wait_for_verdict_timeout_uses_last_result(self):
        old = detail(status=0, tests=[{'result': True, 'actual_output': 'a'}],
                     evaluate_count=1)
        new = detail(status=0, tests=[{'result': True, 'actual_output': 'b'}],
                     evaluate_count=2)
        client = StubClient([new])
        with mock.patch.object(submit.asyncio, 'sleep', no_sleep):
            passed, _ = await wait_for_verdict(
                client, 'gid1', timeout=0, poll=0, baseline=verdict_signature(old))
        # timeout=0 时不进循环，没有 last_detail
        self.assertIsNone(passed)


class SecKeyRetryTests(unittest.IsolatedAsyncioTestCase):
    """sec_key 缺失会让平台「只评分不记通关」，必须多问几次。"""

    async def test_retries_until_key_appears(self):
        client = StubClient([status_payload(), status_payload(),
                             status_payload(sec_key='KEY')])
        with mock.patch.object(submit.asyncio, 'sleep', no_sleep):
            key = await evaluate_sec_key(client, 'gid1')
        self.assertEqual(key, 'KEY')
        self.assertEqual(len(client.paths), 3)

    async def test_gives_up_and_returns_empty(self):
        client = StubClient([status_payload()])
        with mock.patch.object(submit.asyncio, 'sleep', no_sleep):
            self.assertEqual(await evaluate_sec_key(client, 'gid1', attempts=2), '')
        self.assertEqual(len(client.paths), 3)      # 首次 + 2 次重试


class CompletionTests(unittest.IsolatedAsyncioTestCase):
    """「评测通过 ✔」≠「平台已通关」：status≠2 时必须明确回报。"""

    async def test_completion_true_when_status_2(self):
        client = StubClient([detail(status=2)])
        self.assertTrue(await wait_for_completion(client, 'gid1', timeout=5, poll=0))

    async def test_completion_false_when_status_stuck_at_0(self):
        client = StubClient([detail(status=0, score=100)])
        self.assertFalse(await wait_for_completion(client, 'gid1', timeout=0, poll=0))

    async def test_wait_for_verdict_does_not_trust_score(self):
        # status=0 + final_score=100 + 测试集失败：不能判通过
        client = StubClient([detail(status=0, score=100, evaluate_count=2,
                                    tests=[{'result': False,
                                            'actual_output': '图像对比不一致'}])])
        with mock.patch.object(submit.asyncio, 'sleep', no_sleep):
            passed, _ = await wait_for_verdict(client, 'gid1', timeout=30, poll=0)
        self.assertIs(passed, False)

    async def test_code_level_passes_but_platform_not_marked(self):
        """测试集全过、status 一直是 0：打印通过，但要计 unconfirmed。"""

        class PostClient(StubClient):
            def __init__(self):
                super().__init__([
                    detail(status=0, evaluate_count=1,                     # baseline
                           tests=[{'result': False, 'actual_output': 'old'}]),
                    detail(status=0, evaluate_count=2,                     # 评测结果
                           tests=[{'result': True, 'actual_output': 'ok'}]),
                    detail(status=0, evaluate_count=2,                     # 等通关
                           tests=[{'result': True, 'actual_output': 'ok'}]),
                ])
                self.posts = []

            async def post(self, path, params, data):
                self.posts.append((path, data))
                if path.endswith('update_file.json'):
                    return {'sec_key': 'KEY', 'content': {'commitID': 'c1'}}
                return {'res': {'code': 0}}

        client = PostClient()
        stats = {'submitted': 0, 'skipped_no_answer': 0, 'skipped_error': 0,
                 'failed': 0, 'would_submit': 0}
        payload = {
            'challenge': {'id': 11, 'subject': '写代码', 'path': 'src/a.py'},
            'myshixun': {'identifier': 'm1', 'commit_id': 'old'},
            'user': {'user_id': 7},
            'game': {'id': 3, 'status': 0},
            'shixun_environments': [],
        }
        with mock.patch.object(submit.asyncio, 'sleep', no_sleep), \
                mock.patch.dict('os.environ', {'EVAL_CONFIRM_TIMEOUT': '0'}):
            passed = await submit.submit_code_game(
                client, 1, 'gid1', 'print(1)', payload, True, stats, 30)
        self.assertTrue(passed)
        self.assertEqual(stats['unconfirmed'], 1)
        # sec_key 一定交给了 game_build
        build = [d for p, d in client.posts if p.endswith('game_build.json')]
        self.assertEqual(build[0]['sec_key'], 'KEY')


class TracebackCluesTests(unittest.TestCase):
    """从评测回溯里提取测试程序线索（文件名 / 路径 / Python 版本）。"""

    def test_extracts_test_file_paths_and_python(self):
        fb = ('Traceback (most recent call last):\n'
              '  File "t0801/t0801.py", line 18, in <module>\n'
              '    fm.fontManager.addfont(font_path)\n'
              'AttributeError: \'FontManager\' object has no attribute \'addfont\'\n'
              'Traceback (most recent call last):\n'
              '  File "t0801_test.py", line 23, in <module>\n'
              '    a = Image.open("t0801/result/tu1.png")\n'
              '  File "/usr/local/lib/python3.6/site-packages/PIL/Image.py", line 2530, in open\n'
              'FileNotFoundError: No such file or directory: \'t0801/result/tu1.png\'\n')
        clues = _traceback_clues(fb)
        self.assertEqual(clues['test_files'], ['t0801_test.py'])
        self.assertEqual(clues['paths'], ['t0801/result/tu1.png'])
        self.assertEqual(clues['python'], '3.6')

    def test_ignores_student_file_and_site_packages(self):
        fb = ('  File "t0803/t0803.py", line 61, in <module>\n'
              '  File "/usr/local/lib/python3.6/site-packages/pandas/io/parsers.py", line 688\n')
        clues = _traceback_clues(fb)
        self.assertEqual(clues['test_files'], [])

    def test_empty_feedback(self):
        self.assertEqual(_traceback_clues(''),
                         {'test_files': [], 'paths': [], 'python': None})


if __name__ == '__main__':
    unittest.main()
