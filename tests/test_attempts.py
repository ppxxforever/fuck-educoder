"""attempts/ 归档目录的读写测试。"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from educoder_reminder import attempts


class AttemptsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(attempts, 'ATTEMPTS_DIR', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_safe_component(self):
        self.assertEqual(attempts.safe_component('a/b:c*?"<>|'), 'a_b_c______')
        self.assertEqual(attempts.safe_component('  '), 'unnamed')
        self.assertLessEqual(len(attempts.safe_component('x' * 200)), 80)

    def test_save_and_load_code(self):
        target = attempts.save_attempt(
            '软件详细设计-2', 'McCabe方法', 'print(1)\n',
            path='src/step3/main.py', gid='g1', kind='code',
            classroom='c1', feedback='compile error', passed=False)
        self.assertEqual(target.name, 'answer.py')
        level = self.root / '软件详细设计-2' / 'McCabe方法'
        self.assertTrue((level / 'feedback.txt').is_file())
        meta = json.loads((level / 'meta.json').read_text(encoding='utf-8'))
        self.assertEqual(meta['gid'], 'g1')
        self.assertEqual(meta['classroom'], 'c1')
        self.assertFalse(meta['passed'])

        loaded = attempts.load_attempt('软件详细设计-2', 'McCabe方法')
        self.assertEqual(loaded, (target, 'print(1)\n'))
        self.assertEqual(attempts.attempt_path('软件详细设计-2', 'McCabe方法',
                                               ('.mdj',)), None)

    def test_save_removes_missing_marker_and_old_answer(self):
        attempts.ensure_level('exp', 'lv', gid='g1', note='没有答案')
        self.assertTrue((self.root / 'exp' / 'lv' / 'missing.txt').is_file())
        attempts.save_attempt('exp', 'lv', 'x', path='a.sql', gid='g1')
        self.assertFalse((self.root / 'exp' / 'lv' / 'missing.txt').exists())
        self.assertTrue((self.root / 'exp' / 'lv' / 'answer.sql').is_file())
        # 换扩展名后旧文件被清理
        attempts.save_attempt('exp', 'lv', 'y', path='a.py', gid='g1')
        self.assertFalse((self.root / 'exp' / 'lv' / 'answer.sql').exists())
        self.assertTrue((self.root / 'exp' / 'lv' / 'answer.py').is_file())

    def test_uml_and_choice_suffix(self):
        attempts.save_attempt('exp', 'uml', '{}', path=None, kind='uml')
        self.assertTrue((self.root / 'exp' / 'uml' / 'answer.mdj').is_file())
        attempts.save_attempt('exp', 'choice', '{"a":1}', path='a.json', kind='choice')
        self.assertTrue((self.root / 'exp' / 'choice' / 'answer.json').is_file())
        # 代码复用不会误读 UML / choice 存档
        self.assertIsNone(attempts.load_attempt('exp', 'uml', attempts.CODE_SUFFIXES))
        self.assertIsNone(attempts.load_attempt('exp', 'choice', attempts.CODE_SUFFIXES))

    def test_mark_passed_and_list(self):
        attempts.save_attempt('exp', 'lv', 'code', path='a.py', gid='g1')
        attempts.mark_passed('exp', 'lv')
        items = attempts.list_attempts()
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]['passed'])
        self.assertEqual(items[0]['file'], 'answer.py')
        self.assertEqual(items[0]['experiment'], 'exp')

    def test_passed_attempt_not_reused_by_default(self):
        path = attempts.save_attempt('exp', 'lv', 'code', path='a.py', gid='g1')
        self.assertIsNotNone(attempts.load_attempt('exp', 'lv'))
        attempts.mark_passed('exp', 'lv')
        self.assertIsNone(attempts.load_attempt('exp', 'lv'))
        loaded = attempts.load_attempt('exp', 'lv', include_passed=True)
        self.assertEqual(loaded, (path, 'code'))

    def test_empty_content_rejected(self):
        with self.assertRaises(ValueError):
            attempts.save_attempt('exp', 'lv', '   ')

    def test_attempt_target(self):
        self.assertEqual(attempts.attempt_target('exp', 'lv'), '')
        attempts.ensure_level('exp', 'lv', path='程序流程图/submit/step_4/step4.mdj')
        self.assertEqual(attempts.attempt_target('exp', 'lv'),
                         '程序流程图/submit/step_4/step4.mdj')
        (self.root / 'exp' / 'lv' / 'target.txt').write_text(
            'submit/step_2/step2.mdj\n', encoding='utf-8')
        self.assertEqual(attempts.attempt_target('exp', 'lv'),
                         'submit/step_2/step2.mdj')

    def test_missing_level_dir(self):
        self.assertIsNone(attempts.attempt_path('none', 'none'))
        self.assertIsNone(attempts.load_attempt('none', 'none'))


if __name__ == '__main__':
    unittest.main()
