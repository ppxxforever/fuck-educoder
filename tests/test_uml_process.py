"""submit_uml.process_experiment 的回归测试。

背景（2026-10-26）：面向对象分析之顺序图/活动图/类图/用例图 这些「选择题 + 图形题」
混合实验，入口关卡是选择题，process_uml 却只看入口就整条链跳过，导致后面的图形题
全部「未处理」，账号 17836905335 一轮下来 29 关图形题没提交、6 个实验平台仍显示未完成。
"""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from educoder_reminder import levels, submit_uml


def _stats():
    return {'submitted': 0, 'would_submit': 0, 'skipped_passed': 0,
            'skipped_no_answer': 0, 'skipped_error': 0, 'skipped_closed': 0,
            'failed': 0, 'processed': 0}


class MixedExperimentTests(unittest.IsolatedAsyncioTestCase):
    """入口是选择题、后面跟图形题的混合实验，图形题不能被跳过。"""

    HW = {'homework_id': 1, 'shixun_identifier': 's1', 'name': '混合实验'}

    CHOICE = {'challenge': {'subject': '选择题', 'task_pass': ''},
              'chooses': [{'id': 1}], 'game': {'status': 0},
              'prev_game': None, 'next_game': 'g2'}
    GRAPHIC = {'challenge': {'subject': '画图', 'path': 'a/submit/step1.mdj',
                             'task_pass': '保存到 a/submit/step1.mdj'},
               'game': {'status': 0},
               'shixun_environments': [{'vnc_url': 'vnc://example'}],
               'prev_game': 'g1', 'next_game': None}

    async def _run(self, *, apply=False):
        cache = {'g1': self.CHOICE, 'g2': self.GRAPHIC}
        stats = _stats()
        coverage = levels.Coverage()
        submit_mock = mock.AsyncMock(return_value=True)
        with TemporaryDirectory() as d:
            mdj = Path(d) / 'step1.mdj'
            mdj.write_text('{"_type":"Project"}', encoding='utf-8')
            with mock.patch.object(submit_uml, 'is_homework_closed',
                                   return_value=False), \
                 mock.patch.object(submit_uml, 'resolve_entry',
                                   new=mock.AsyncMock(return_value='g1')), \
                 mock.patch.object(submit_uml, 'walk_prev_to_head',
                                   new=mock.AsyncMock(return_value=(['g1', 'g2'], cache))), \
                 mock.patch.object(submit_uml, 'detail_of',
                                   new=mock.AsyncMock(
                                       side_effect=lambda c, cache, gid: cache[gid])), \
                 mock.patch.object(submit_uml, 'resolve_answer_base',
                                   return_value=Path(d)), \
                 mock.patch.object(submit_uml, 'collect_mdj',
                                   return_value={'画图': str(mdj)}), \
                 mock.patch.object(submit_uml, 'extract_target',
                                   return_value=('a/submit/step1.mdj', 1)), \
                 mock.patch.object(submit_uml, 'submit_graphic_game',
                                   new=submit_mock), \
                 mock.patch.object(submit_uml, 'passed_on_platform',
                                   new=mock.AsyncMock(return_value=False)), \
                 mock.patch.object(submit_uml, 'release_myshixun_pod',
                                   new=mock.AsyncMock(return_value=False)):
                await submit_uml.process_experiment(
                    mock.Mock(), self.HW, apply, stats, 5,
                    use_ai=False, delay=0, coverage=coverage)
        return stats, coverage, submit_mock

    async def test_graphic_level_is_submitted_after_choice_entry(self):
        stats, coverage, submit_mock = await self._run(apply=True)
        # 图形题必须被归到 UML 链，并且真的提交了（不再是 action=None 的「未处理」）
        self.assertEqual(coverage.get('g2')['owner'], levels.OWNER_UML)
        # 关键回归：入口是选择题时，后面的图形题仍要被 submit_graphic_game 提交
        submit_mock.assert_awaited_once()

    async def test_pure_choice_experiment_still_skipped(self):
        # 纯选择题实验（没有任何图形题）仍然应该直接交给 submit.py，不能多打印/多走
        cache = {'g1': self.CHOICE}
        submit_mock = mock.AsyncMock()
        with mock.patch.object(submit_uml, 'is_homework_closed', return_value=False), \
             mock.patch.object(submit_uml, 'resolve_entry',
                               new=mock.AsyncMock(return_value='g1')), \
             mock.patch.object(submit_uml, 'walk_prev_to_head',
                               new=mock.AsyncMock(return_value=(['g1'], cache))), \
             mock.patch.object(submit_uml, 'detail_of',
                               new=mock.AsyncMock(
                                   side_effect=lambda c, cache, gid: cache[gid])), \
             mock.patch.object(submit_uml, 'submit_graphic_game',
                               new=submit_mock), \
             mock.patch.object(submit_uml, 'passed_on_platform',
                               new=mock.AsyncMock(return_value=False)):
            await submit_uml.process_experiment(
                mock.Mock(), self.HW, False, _stats(), 5,
                use_ai=False, delay=0, coverage=levels.Coverage())
        submit_mock.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
