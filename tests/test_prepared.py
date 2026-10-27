"""prepared/ 预生成答案缓存 + prepare.py 的「本地有答案就不调 AI」逻辑。"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from educoder_reminder import answer_sources, prepare, prepared, submit


def detail(subject='关卡', *, chooses=None, path=None, vnc=False, task=''):
    data = {
        'challenge': {'subject': subject, 'path': path, 'task_pass': task},
        'chooses': chooses or [],
    }
    if vnc:
        data['shixun_environments'] = [{'vnc_url': 'vnc://example'}]
    return data


class PreparedStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(prepared, 'PREPARED_DIR', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_and_load_code(self):
        target = prepared.save_prepared(
            '实验', '关卡', 'print(1)\n', path='src/step1/main.py', gid='g1',
            kind='code', classroom='c1')
        self.assertEqual(target.name, 'answer.py')
        self.assertEqual(prepared.load_prepared('实验', '关卡'), (target, 'print(1)\n'))
        meta = json.loads((self.root / '实验' / '关卡' / 'meta.json')
                          .read_text(encoding='utf-8'))
        self.assertEqual(meta['gid'], 'g1')
        self.assertEqual(meta['classroom'], 'c1')
        self.assertEqual(meta['source'], 'ai-prepare')
        self.assertEqual(prepared.prepared_target('实验', '关卡'), 'src/step1/main.py')

    def test_uml_and_choice_suffix(self):
        prepared.save_prepared('e', 'uml', '{}', path='submit/step1.mdj', kind='uml')
        prepared.save_prepared('e', 'choice', '[]', path='answer.json', kind='choice')
        self.assertTrue((self.root / 'e' / 'uml' / 'answer.mdj').is_file())
        self.assertTrue((self.root / 'e' / 'choice' / 'answer.json').is_file())

    def test_question_and_overwrite(self):
        prepared.save_question('e', 'lv', '# 题目\n', gid='g1', kind='code',
                               path='a.py', classroom='c1')
        self.assertTrue((self.root / 'e' / 'lv' / 'question.md').is_file())
        old = prepared.save_prepared('e', 'lv', 'old', path='a.py', kind='code')
        new = prepared.save_prepared('e', 'lv', 'new', path='b.sql', kind='code')
        self.assertFalse(old.exists())
        self.assertEqual(prepared.load_prepared('e', 'lv'), (new, 'new'))
        meta = json.loads((self.root / 'e' / 'lv' / 'meta.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['question'], 'question.md')   # 覆盖答案不会丢题目
        self.assertEqual(prepared.list_prepared()[0]['file'], 'answer.sql')

    def test_empty_rejected(self):
        self.assertIsNone(prepared.save_prepared('e', 'lv', '   ', path='a.py'))
        self.assertIsNone(prepared.save_prepared('', 'lv', 'x', path='a.py'))
        self.assertIsNone(prepared.save_question('e', 'lv', '  '))

    def test_missing(self):
        self.assertIsNone(prepared.prepared_path('no', 'no'))
        self.assertIsNone(prepared.load_prepared('no', 'no'))
        self.assertEqual(prepared.prepared_target('no', 'no'), '')

    def test_rejected_not_reused_until_regenerated(self):
        prepared.save_prepared('e', 'lv', 'wrong', path='a.py', kind='code')
        prepared.mark_rejected('e', 'lv', '提交未通过')
        self.assertTrue(prepared.is_rejected('e', 'lv'))
        self.assertIsNone(prepared.prepared_path('e', 'lv'))
        self.assertIsNone(prepared.load_prepared('e', 'lv'))
        # 文件还在，方便人工查看；列表里能看到被标记
        self.assertTrue(prepared.prepared_path('e', 'lv', include_rejected=True).is_file())
        self.assertTrue(prepared.list_prepared()[0]['rejected'])
        # 重新生成后标记自动清除
        prepared.save_prepared('e', 'lv', 'fixed', path='a.py', kind='code')
        self.assertFalse(prepared.is_rejected('e', 'lv'))
        self.assertEqual(prepared.load_prepared('e', 'lv')[1], 'fixed')


class AnswerSourcePreparedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(prepared, 'PREPARED_DIR', Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        for mod, name in ((answer_sources.solutions, 'load_solution'),
                          (answer_sources.attempts, 'load_attempt')):
            p = mock.patch.object(mod, name, return_value=None)
            p.start()
            self.addCleanup(p.stop)

    def test_prepared_is_last_resort(self):
        answers = {'classrooms': []}
        prepared.save_prepared('实验', '写代码', 'print(1)', path='src/a.py', kind='code')
        d = detail('写代码', path='src/a.py')
        content, kind, path, source = answer_sources.answer_for_level(
            d, answers, 'c1', '课堂', '实验')
        self.assertEqual(content, 'print(1)')
        self.assertEqual(kind, 'code')
        self.assertEqual(path, 'src/a.py')
        self.assertIn(str(prepared.PREPARED_DIR), source)

    def test_include_prepared_false_ignores_it(self):
        answers = {'classrooms': []}
        prepared.save_prepared('实验', '写代码', 'print(1)', path='src/a.py', kind='code')
        content, *_ = answer_sources.answer_for_level(
            detail('写代码', path='src/a.py'), answers, 'c1', '课堂', '实验',
            include_prepared=False)
        self.assertIsNone(content)


class PrepareLevelTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(prepared, 'PREPARED_DIR', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.course = SimpleNamespace(name='课堂', identifier='c1')
        self.hw = {'name': '实验', 'homework_id': 1}
        self.answers = {'classrooms': []}

    @staticmethod
    def args(**kw):
        base = {'dry_run': False, 'overwrite': False, 'limit': None,
                'no_ai': False, 'experiment': None, 'delay': 0,
                'include_expired': False}
        base.update(kw)
        return SimpleNamespace(**base)

    @staticmethod
    def stats():
        return {'levels': 0, 'generated': 0, 'skipped_local': 0, 'skipped_prepared': 0,
                'skipped_passed': 0, 'skipped_closed': 0, 'skipped_no_ai': 0,
                'skipped_error': 0, 'failed': 0, 'planned': 0}

    async def test_local_answer_skips_ai(self):
        stats = self.stats()
        with mock.patch.object(prepare, 'answer_for_level',
                               return_value=('code', 'code', 'a.py', 'answers.json')) as local, \
             mock.patch.object(prepare, 'ai_solve_choice') as ai:
            done = await prepare.prepare_level(
                None, self.course, self.hw, 'g1', detail('写代码', path='a.py'),
                self.answers, self.args(), stats)
        self.assertTrue(done)
        local.assert_called_once()
        ai.assert_not_called()
        self.assertEqual(stats['skipped_local'], 1)
        self.assertEqual(stats['generated'], 0)
        # 题目原文仍然落盘（爬题不依赖有没有答案）
        self.assertTrue((self.root / '实验' / '写代码' / 'question.md').is_file())

    async def test_prepared_answer_skips_ai(self):
        prepared.save_prepared('实验', '写代码', 'old', path='a.py', kind='code')
        stats = self.stats()
        with mock.patch.object(prepare, 'answer_for_level') as local, \
             mock.patch.object(prepare, 'ai_solve_choice') as ai:
            done = await prepare.prepare_level(
                None, self.course, self.hw, 'g1', detail('写代码', path='a.py'),
                self.answers, self.args(), stats)
        self.assertTrue(done)
        local.assert_not_called()      # 连本地查找都不用做
        ai.assert_not_called()
        self.assertEqual(stats['skipped_prepared'], 1)
        self.assertEqual(prepared.load_prepared('实验', '写代码')[1], 'old')

    async def test_overwrite_regenerates_prepared(self):
        prepared.save_prepared('实验', '选择题', 'old', path='answer.json', kind='choice')
        stats = self.stats()
        chooses = [{'subject': '1+1=?',
                    'challenge_question': [{'option_name': '2'}, {'option_name': '3'}]}]
        d = detail('选择题', chooses=chooses)
        with mock.patch.object(prepare, 'answer_for_level',
                               return_value=(None, 'choice', 'answer.json', '')), \
             mock.patch.object(prepare, 'ai_configured', return_value=True), \
             mock.patch.object(prepare, 'ai_solve_choice', return_value=['A']) as ai:
            done = await prepare.prepare_level(
                None, self.course, self.hw, 'g1', d, self.answers,
                self.args(overwrite=True), stats)
        self.assertTrue(done)
        ai.assert_called_once()
        self.assertEqual(stats['generated'], 1)
        content = prepared.load_prepared('实验', '选择题')[1]
        self.assertEqual(json.loads(content)['answer'][0]['selected'], ['A'])

    async def test_overwrite_keeps_verified_answer(self):
        stats = self.stats()
        with mock.patch.object(prepare, 'answer_for_level',
                               return_value=('code', 'code', 'a.py', 'answers.json')), \
             mock.patch.object(prepare, 'ai_solve_choice') as ai:
            done = await prepare.prepare_level(
                None, self.course, self.hw, 'g1', detail('写代码', path='a.py'),
                self.answers, self.args(overwrite=True), stats)
        self.assertTrue(done)
        ai.assert_not_called()
        self.assertEqual(stats['skipped_local'], 1)
        self.assertEqual(stats['generated'], 0)

    async def test_dry_run_writes_nothing(self):
        stats = self.stats()
        with mock.patch.object(prepare, 'answer_for_level', return_value=(None, '', '', '')), \
             mock.patch.object(prepare, 'ai_solve_choice') as ai:
            done = await prepare.prepare_level(
                None, self.course, self.hw, 'g1', detail('写代码', path='a.py'),
                self.answers, self.args(dry_run=True), stats)
        self.assertTrue(done)
        ai.assert_not_called()
        self.assertEqual(stats['planned'], 1)
        self.assertFalse(self.root.exists() and any(self.root.iterdir()))

    async def test_limit_stops(self):
        stats = self.stats()
        stats['generated'] = 1
        done = await prepare.prepare_level(
            None, self.course, self.hw, 'g1', detail('写代码', path='a.py'),
            self.answers, self.args(limit=1), stats)
        self.assertFalse(done)


class QuestionTextTests(unittest.TestCase):
    def test_question_text_contains_clues(self):
        d = detail('事务型结构图', chooses=[
            {'subject': '事务的边界', 'challenge_question': [
                {'option_name': 'BEGIN'}, {'option_name': 'COMMIT'}]}],
            path='answer.json', task='<p>选择正确答案</p>')
        text = prepare.question_text(d, gid='g9', kind='choice', target='answer.json')
        for piece in ('事务型结构图', 'g9', 'choice', 'answer.json', '事务的边界',
                      'A. BEGIN', 'B. COMMIT', '选择正确答案'):
            self.assertIn(piece, text)


class LoadPreparedSolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(prepared, 'PREPARED_DIR', Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_choice(self):
        payload = json.dumps({'title': '选择', 'kind': 'choice',
                              'answer': [{'number': 1, 'selected': ['A']}]})
        prepared.save_prepared('实验', '选择', payload, path='answer.json', kind='choice')
        level = submit.load_prepared_solution('实验', '选择', 'choice')
        self.assertEqual(level['answer'], [{'number': 1, 'selected': ['A']}])
        self.assertTrue(level['answered'])

    def test_code_and_uml(self):
        prepared.save_prepared('实验', '代码', 'print(1)', path='a.py', kind='code')
        self.assertEqual(submit.load_prepared_solution('实验', '代码', 'code')['answer'],
                         {'language': '', 'code': 'print(1)'})
        # 图形题由 submit_uml 读取，这里必须返回 None
        prepared.save_prepared('实验', '画图', '{}', path='step1.mdj', kind='uml')
        self.assertIsNone(submit.load_prepared_solution('实验', '画图', 'uml'))

    def test_missing(self):
        self.assertIsNone(submit.load_prepared_solution('no', 'no', 'code'))
        self.assertIsNone(submit.load_prepared_solution('', 'no', 'code'))

    def test_rejected_not_reused(self):
        prepared.save_prepared('实验', '代码', 'print(1)', path='a.py', kind='code')
        prepared.mark_rejected('实验', '代码', '提交未通过')
        self.assertIsNone(submit.load_prepared_solution('实验', '代码', 'code'))


if __name__ == '__main__':
    unittest.main()
