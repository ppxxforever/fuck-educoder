"""本地答案来源选择测试（选择题优先于图形题等）。"""
import json
import unittest

from educoder_reminder import answer_sources


ANSWERS = {
    'classrooms': [{
        'code': 'c1', 'name': '课堂',
        'experiments': [{
            'name': '[7] 单元测试',
            'levels': [
                {'title': '使用Junit进行单元测试', 'kind': 'code',
                 'answer': {'language': '', 'code': 'class T {}'}},
                {'title': '事务型结构图', 'kind': 'choice',
                 'answer': [{'number': 1, 'selected': ['A']}]},
            ],
        }],
    }],
}


def detail(subject, *, chooses=None, path=None, vnc=False):
    return {
        'challenge': {'subject': subject, 'path': path, 'task_pass': ''},
        'chooses': chooses or [],
        'shixun_environments': [{'vnc_url': 'x'}] if vnc else [],
    }


class AnswerSourceTests(unittest.TestCase):
    def test_find_answer_level(self):
        exp = ANSWERS['classrooms'][0]['experiments'][0]
        self.assertEqual(answer_sources.find_answer_level(exp, '使用Junit进行单元测试')['kind'],
                         'code')
        # 包含匹配（平台标题可能带前缀）
        self.assertIsNotNone(answer_sources.find_answer_level(exp, 'Junit进行单元测试'))
        self.assertIsNone(answer_sources.find_answer_level(exp, '不存在'))

    def test_local_code_and_choice(self):
        self.assertEqual(
            answer_sources.local_code(ANSWERS, 'c1', '课堂', '单元测试',
                                      '使用Junit进行单元测试'),
            'class T {}')
        choice = answer_sources.local_choice(ANSWERS, 'c1', '课堂', '单元测试',
                                             '事务型结构图')
        self.assertEqual(json.loads(choice)['answer'][0]['selected'], ['A'])

    def test_choice_wins_over_graphic(self):
        # 事务型结构图带 chooses，同时也可能带 VNC 环境；必须按选择题处理
        d = detail('事务型结构图', chooses=[{'id': 1}], vnc=True)
        content, kind, path, source = answer_sources.answer_for_level(
            d, ANSWERS, 'c1', '课堂', '单元测试')
        self.assertEqual(kind, 'choice')
        self.assertEqual(path, 'answer.json')
        self.assertEqual(source, 'answers.json')
        self.assertEqual(json.loads(content)['answer'][0]['selected'], ['A'])

    def test_code_level(self):
        d = detail('使用Junit进行单元测试', path='src/step1/CalculatorTest.java')
        content, kind, path, _ = answer_sources.answer_for_level(
            d, ANSWERS, 'c1', '课堂', '单元测试')
        self.assertEqual(kind, 'code')
        self.assertEqual(path, 'src/step1/CalculatorTest.java')
        self.assertEqual(content, 'class T {}')


if __name__ == '__main__':
    unittest.main()
