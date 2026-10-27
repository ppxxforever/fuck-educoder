"""「AI 刷通 → 落库 → 下次复用」闭环测试。

覆盖三处以前断掉的环节：
1. answers.json 里没有的新课堂，做完的答案必须能落进去（否则 AI 白干）；
2. solutions/ 只写不读 → 现在要能被当作答案来源复用；
3. 复用回来后要回填 answers.json，之后不再依赖 solutions/。
"""
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from educoder_reminder import answer_sources, solutions, submit


EMPTY_ANSWERS = {'kind': 'class-answers', 'classrooms': []}


class EnsureClassroomTests(unittest.TestCase):
    def test_new_classroom_is_created(self):
        data = json.loads(json.dumps(EMPTY_ANSWERS))
        classroom = submit.ensure_classroom(data, 'NEWCODE', '数据结构')
        self.assertEqual(classroom['code'], 'NEWCODE')
        self.assertEqual(classroom['name'], '数据结构')
        self.assertEqual(classroom['experiments'], [])
        self.assertEqual(len(data['classrooms']), 1)

    def test_existing_classroom_reused_and_name_backfilled(self):
        data = {'classrooms': [{'code': 'C1', 'name': '', 'experiments': [
            {'name': '实验', 'levels': []}]}]}
        classroom = submit.ensure_classroom(data, 'C1', '软件工程')
        self.assertEqual(len(data['classrooms']), 1)
        self.assertEqual(classroom['name'], '软件工程')
        self.assertEqual(len(classroom['experiments']), 1)

    def test_missing_code_returns_none(self):
        self.assertIsNone(submit.ensure_classroom(EMPTY_ANSWERS, ''))

    def test_same_course_name_with_new_code_reuses_entry(self):
        # 换班/换学期后 code 变了、课名相同：沿用旧条目并更新 code，不新增重复课堂
        data = {'classrooms': [{'code': 'OLD', 'name': '数据结构', 'experiments': [
            {'name': '实验一', 'levels': []}]}]}
        classroom = submit.ensure_classroom(data, 'NEW', '数据结构')
        self.assertEqual(len(data['classrooms']), 1)
        self.assertEqual(classroom['code'], 'NEW')
        self.assertEqual(len(classroom['experiments']), 1)


class SaveLevelAnswerTests(unittest.TestCase):
    """新课堂上做出来的答案必须写进 answers.json（以前会静默丢弃）。"""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'answers.json'
        self.data = json.loads(json.dumps(EMPTY_ANSWERS))

    def test_code_answer_on_brand_new_classroom_is_persisted(self):
        submit.save_level_answer(
            self.data, 'NEWCODE', '实验一', '第一关', 'code',
            {'language': '', 'code': 'print(1)'}, self.path, classroom_name='数据结构')
        on_disk = json.loads(self.path.read_text(encoding='utf-8'))
        classroom = on_disk['classrooms'][0]
        self.assertEqual(classroom['name'], '数据结构')
        level = classroom['experiments'][0]['levels'][0]
        self.assertEqual(level['title'], '第一关')
        self.assertEqual(level['answer']['code'], 'print(1)')
        self.assertTrue(level['answered'])

    def test_second_answer_appends_to_same_experiment(self):
        submit.save_level_answer(self.data, 'C1', '实验一', '第一关', 'code',
                                 {'language': '', 'code': 'a'}, self.path)
        submit.save_level_answer(self.data, 'C1', '实验一', '第二关', 'code',
                                 {'language': '', 'code': 'b'}, self.path)
        self.assertEqual(len(self.data['classrooms']), 1)
        levels = self.data['classrooms'][0]['experiments'][0]['levels']
        self.assertEqual([lv['title'] for lv in levels], ['第一关', '第二关'])

    def test_sql_artifacts_stripped(self):
        submit.save_level_answer(
            self.data, 'C1', '实验', 'SQL关', 'code',
            {'language': '', 'code': 'CREATE DATABASE IF NOT EXISTS x;\nuse x;\nSELECT 1;'},
            self.path)
        code = self.data['classrooms'][0]['experiments'][0]['levels'][0]['answer']['code']
        self.assertNotIn('CREATE DATABASE', code)
        self.assertIn('use x;', code)


class LoadArchivedSolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(solutions, 'SOLUTIONS_DIR', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_code_solution_becomes_level(self):
        solutions.save_solution('实验', '第一关', 'print(42)\n', path='src/step1/main.py',
                                kind='code')
        level = submit.load_archived_solution('实验', '第一关', 'code')
        self.assertIsNotNone(level)
        self.assertEqual(level['kind'], 'code')
        self.assertEqual(level['answer']['code'], 'print(42)\n')
        self.assertTrue(level['answered'])

    def test_choice_solution_becomes_level(self):
        payload = json.dumps({'title': '选择题', 'kind': 'choice',
                              'answer': [{'number': 1, 'selected': ['A']}]},
                             ensure_ascii=False)
        solutions.save_solution('实验', '选择题', payload, path='answer.json',
                                kind='choice')
        level = submit.load_archived_solution('实验', '选择题', 'choice')
        self.assertEqual(level['answer'], [{'number': 1, 'selected': ['A']}])

    def test_broken_choice_json_returns_none(self):
        solutions.save_solution('实验', '坏答案', 'not json', path='answer.json',
                                kind='choice')
        self.assertIsNone(submit.load_archived_solution('实验', '坏答案', 'choice'))

    def test_missing_returns_none(self):
        self.assertIsNone(submit.load_archived_solution('实验', '不存在', 'code'))
        self.assertIsNone(submit.load_archived_solution('', '关卡', 'code'))

    def test_uml_not_loaded_here(self):
        solutions.save_solution('实验', '图形', '{}', kind='uml')
        self.assertIsNone(submit.load_archived_solution('实验', '图形', 'graphic'))


class AnswerSourcesSolutionFallbackTests(unittest.TestCase):
    """answer_sources 的优先级：answers.json → answer/ → solutions/ → attempts/。"""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(solutions, 'SOLUTIONS_DIR', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def detail(self, subject, path='src/step1/main.py'):
        return {'challenge': {'subject': subject, 'path': path, 'task_pass': ''},
                'chooses': []}

    def test_solution_used_when_answers_json_has_nothing(self):
        solutions.save_solution('实验', '第一关', 'print(7)\n', path='src/step1/main.py',
                                kind='code')
        content, kind, path, source = answer_sources.answer_for_level(
            self.detail('第一关'), {'classrooms': []}, 'C1', '课堂', '实验')
        self.assertEqual(content, 'print(7)\n')
        self.assertEqual(kind, 'code')
        self.assertTrue(source.endswith('answer.py'))

    def test_answers_json_wins_over_solution(self):
        solutions.save_solution('实验', '第一关', 'from-solution\n',
                                path='src/step1/main.py', kind='code')
        answers = {'classrooms': [{'code': 'C1', 'name': '课堂', 'experiments': [
            {'name': '实验', 'levels': [
                {'title': '第一关', 'kind': 'code',
                 'answer': {'language': '', 'code': 'from-answers-json'}}]}]}]}
        content, _kind, _path, source = answer_sources.answer_for_level(
            self.detail('第一关'), answers, 'C1', '课堂', '实验')
        self.assertEqual(content, 'from-answers-json')
        self.assertEqual(source, 'answers.json')


if __name__ == '__main__':
    unittest.main()
