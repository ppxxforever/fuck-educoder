"""solutions/ 已完成答案库的读写测试。"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from educoder_reminder import solutions


class SolutionsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(solutions, 'SOLUTIONS_DIR', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_save_and_load_code(self):
        target = solutions.save_solution(
            '实验', '关卡', 'print(1)\n', path='src/step1/main.py', gid='g1',
            kind='code', classroom='c1', source='submit')
        self.assertEqual(target.name, 'answer.py')
        self.assertEqual(solutions.load_solution('实验', '关卡'), (target, 'print(1)\n'))
        meta = json.loads((self.root / '实验' / '关卡' / 'meta.json')
                          .read_text(encoding='utf-8'))
        self.assertEqual(meta['gid'], 'g1')
        self.assertEqual(meta['classroom'], 'c1')
        self.assertEqual(meta['source'], 'submit')

    def test_choice_and_uml_suffix(self):
        solutions.save_solution('e', 'choice', '{"a": 1}', path='answer.json',
                                kind='choice')
        solutions.save_solution('e', 'uml', '{}', kind='uml')
        self.assertTrue((self.root / 'e' / 'choice' / 'answer.json').is_file())
        self.assertTrue((self.root / 'e' / 'uml' / 'answer.mdj').is_file())

    def test_overwrite_and_list(self):
        solutions.save_solution('e', 'lv', 'old', path='a.sql')
        new = solutions.save_solution('e', 'lv', 'new', path='a.py')
        self.assertFalse((self.root / 'e' / 'lv' / 'answer.sql').exists())
        items = solutions.list_solutions()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['file'], 'answer.py')
        self.assertEqual(solutions.load_solution('e', 'lv'), (new, 'new'))

    def test_empty_rejected(self):
        self.assertIsNone(solutions.save_solution('e', 'lv', '   ', path='a.py'))
        self.assertIsNone(solutions.save_solution('', 'lv', 'x', path='a.py'))

    def test_missing(self):
        self.assertIsNone(solutions.solution_path('no', 'no'))
        self.assertIsNone(solutions.load_solution('no', 'no'))


if __name__ == '__main__':
    unittest.main()
