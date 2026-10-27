"""题型判定 + 实验收尾校验。

回归背景（2026-10-25）：软件详细设计-2 / 面向数据流的设计方法-2 的图形题全部
「评测通过」，但实验里的选择题关卡谁都没提交，实验在平台上一直显示未提交，
而整轮运行退出码是 0。下面这些测试锁的就是这几条：
- 带 VNC 环境的选择题必须判成选择题，不能判成图形题；
- 题型判不出来的关卡必须报成 unknown，不许静默跳过；
- 实验跑完的收尾校验要把「未通关」「无人负责」的关卡抓出来并落到报告里。
"""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock

from educoder_reminder import levels, submit, submit_all


def detail(subject='关卡', *, chooses=None, path=None, vnc=False, status=0, score=0):
    data = {
        'challenge': {'subject': subject, 'path': path, 'task_pass': ''},
        'game': {'status': status, 'final_score': score},
        'chooses': chooses or [],
    }
    if vnc:
        data['shixun_environments'] = [{'vnc_url': 'vnc://example'}]
    return data


class ClassifyTests(unittest.TestCase):
    def test_choice_inside_graphic_experiment(self):
        # 图形化实验里的选择题同样挂 VNC 环境，必须优先判成选择题
        self.assertEqual(
            levels.classify_level(detail('McCabe方法', chooses=[{'id': 1}], vnc=True)),
            levels.KIND_CHOICE)

    def test_recorded_kind_wins(self):
        self.assertEqual(levels.classify_level(detail('x'), 'choice'), levels.KIND_CHOICE)
        self.assertEqual(levels.classify_level(detail('x', vnc=True), 'code'), levels.KIND_CODE)

    def test_code_level(self):
        self.assertEqual(levels.classify_level(detail('写代码', path='src/a.py')),
                         levels.KIND_CODE)

    def test_graphic_level(self):
        self.assertEqual(levels.classify_level(detail('画图', vnc=True)),
                         levels.KIND_GRAPHIC)
        self.assertEqual(levels.classify_level(detail('画图', path='a/submit/step1.mdj')),
                         levels.KIND_GRAPHIC)

    def test_unknown_is_explicit(self):
        self.assertEqual(levels.classify_level(detail('???')), levels.KIND_UNKNOWN)
        self.assertEqual(levels.classify_level({}), levels.KIND_UNKNOWN)


class RecordedLevelTests(unittest.TestCase):
    LEVELS = [
        {'title': 'McCabe方法', 'kind': 'choice'},
        {'title': ' 事务型结构图 ', 'kind': 'choice'},
    ]

    def test_exact_and_whitespace(self):
        self.assertEqual(levels.find_recorded_level(self.LEVELS, 'McCabe方法')['kind'], 'choice')
        self.assertEqual(levels.find_recorded_level(self.LEVELS, '事务型结构图')['kind'], 'choice')

    def test_prefix_match(self):
        # 平台标题带章节前缀时也要能匹配到本地答案
        self.assertIsNotNone(
            levels.find_recorded_level(self.LEVELS, '[5、软件设计与结构化设计] McCabe方法'))

    def test_missing(self):
        self.assertIsNone(levels.find_recorded_level(self.LEVELS, '不存在'))
        self.assertIsNone(levels.find_recorded_level(self.LEVELS, ''))


class CoverageTests(unittest.TestCase):
    def test_unowned_only_counts_unpassed(self):
        cov = levels.Coverage()
        cov.note('a', kind=levels.KIND_CHOICE, owner=levels.OWNER_SUBMIT)
        cov.note('b', kind=levels.KIND_GRAPHIC, passed=True)
        cov.note('c', kind=levels.KIND_UNKNOWN, action='unknown')
        self.assertEqual([r['gid'] for r in cov.unowned()], ['c'])

    def test_note_merges(self):
        cov = levels.Coverage()
        cov.note('a', kind=levels.KIND_CHOICE, subject='题目')
        cov.note('a', owner=levels.OWNER_SUBMIT, action='submitted')
        record = cov.get('a')
        self.assertEqual(record['subject'], '题目')
        self.assertEqual(record['owner'], levels.OWNER_SUBMIT)
        self.assertEqual(record['action'], 'submitted')


class FakeClient:
    def __init__(self, details):
        self.details = details
        self.calls = []

    async def get(self, path, params, *, strict_status=True):
        gid = path.rsplit('/', 1)[-1].removesuffix('.json')
        self.calls.append(gid)
        return self.details[gid]


HW = {'homework_id': 1, 'shixun_identifier': 's1', 'name': '软件详细设计-2'}


class AuditTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = FakeClient({
            'g1': {**detail('绘制程序流程图', path='p/submit/step1.mdj', status=2),
                   'prev_game': None, 'next_game': 'g2'},
            'g2': {**detail('事务型结构图', chooses=[{'id': 1}], vnc=True),
                   'prev_game': 'g1', 'next_game': None},
        })

    async def test_reports_unpassed_level_even_if_nobody_owns_it(self):
        cov = levels.Coverage()
        with mock.patch.object(submit, 'resolve_entry',
                               new=mock.AsyncMock(return_value='g2')):
            findings = await levels.audit_experiment(self.client, HW, cov)
        self.assertEqual([f['subject'] for f in findings], ['事务型结构图'])
        self.assertIsNone(findings[0]['owner'])          # 无人认领 → 必须被当成漏处理
        self.assertEqual(findings[0]['kind'], levels.KIND_CHOICE)

    async def test_owner_is_reported(self):
        cov = levels.Coverage()
        cov.note('g2', kind=levels.KIND_CHOICE, subject='事务型结构图',
                 owner=levels.OWNER_SUBMIT, action='attempted')
        with mock.patch.object(submit, 'resolve_entry',
                               new=mock.AsyncMock(return_value='g2')):
            findings = await levels.audit_experiment(self.client, HW, cov)
        self.assertEqual(findings[0]['owner'], levels.OWNER_SUBMIT)
        self.assertEqual(findings[0]['action'], 'attempted')

    async def test_clean_experiment(self):
        self.client.details['g2']['game'] = {'status': 2, 'final_score': 100}
        with mock.patch.object(submit, 'resolve_entry',
                               new=mock.AsyncMock(return_value='g2')):
            self.assertEqual(await levels.audit_experiment(self.client, HW), [])

    async def test_no_entry(self):
        with mock.patch.object(submit, 'resolve_entry',
                               new=mock.AsyncMock(return_value=None)):
            self.assertIsNone(await levels.audit_experiment(self.client, HW))

    async def test_unreadable_detail_is_not_reported_as_unpassed(self):
        """读不到详情 ≠ 关卡没过：标 unreadable，让调用方计入 audit_error。"""
        self.client.details['g2'] = {'status': 1, 'message': '忙'}
        with mock.patch.object(submit, 'resolve_entry',
                               new=mock.AsyncMock(return_value='g2')), \
                mock.patch.object(submit, 'DETAIL_RETRY_DELAY', 0):
            findings = await levels.audit_experiment(self.client, HW)
        self.assertEqual([f['gid'] for f in findings], ['g2'])
        self.assertTrue(findings[0]['unreadable'])
        self.assertEqual(findings[0]['kind'], levels.KIND_UNKNOWN)

    async def test_unreadable_level_turns_ok_after_refetch(self):
        fixed = {**detail('事务型结构图', chooses=[{'id': 1}], status=2),
                 'prev_game': 'g1', 'next_game': None}

        class FlakyClient(FakeClient):
            async def get(self, path, params, *, strict_status=True):
                gid = path.rsplit('/', 1)[-1].removesuffix('.json')
                self.calls.append(gid)
                if gid == 'g2':
                    return self.details['g2'] if self.calls.count('g2') <= 2 else fixed
                return self.details[gid]

        client = FlakyClient({
            'g1': {**detail('绘制程序流程图', path='p/submit/step1.mdj', status=2),
                   'prev_game': None, 'next_game': 'g2'},
            'g2': {'status': 1},
        })
        with mock.patch.object(submit, 'resolve_entry',
                               new=mock.AsyncMock(return_value='g2')), \
                mock.patch.object(submit, 'DETAIL_RETRY_DELAY', 0):
            findings = await levels.audit_experiment(client, HW)
        self.assertEqual(findings, [])


class ProcessExperimentWiringTests(unittest.IsolatedAsyncioTestCase):
    """submit.py 里的静默分支已经被拿掉：判不出题型必须计数 + 留痕。"""

    HW = {'homework_id': 1, 'shixun_identifier': 's1', 'name': '实验'}

    def _stats(self):
        return {'submitted': 0, 'would_submit': 0, 'skipped_passed': 0,
                'skipped_no_answer': 0, 'skipped_error': 0, 'failed': 0,
                'processed': 0, 'unowned': 0}

    async def test_unknown_level_is_counted_as_unowned(self):
        client = FakeClient({
            'g1': {'challenge': {'subject': '神秘关卡'}, 'game': {'status': 0},
                   'prev_game': None, 'next_game': None},
        })
        stats = self._stats()
        coverage = levels.Coverage()
        with mock.patch.object(submit, 'resolve_entry',
                               new=mock.AsyncMock(return_value='g1')):
            await submit.process_experiment(
                client, self.HW, {'name': '实验', 'levels': []}, False, stats, 5,
                answers={'classrooms': []}, classroom_code='c1',
                use_ai=False, delay=0, coverage=coverage)
        self.assertEqual(stats['unowned'], 1)
        self.assertEqual([r['gid'] for r in coverage.unowned()], ['g1'])

    async def test_graphic_level_does_not_cut_the_chain(self):
        # 图形关卡不能截断关卡链，后面的关卡仍然要看得到（不然又漏一关）
        client = FakeClient({
            'g1': {'challenge': {'subject': '画图', 'path': 'a/submit/step1.mdj'},
                   'game': {'status': 0}, 'prev_game': None, 'next_game': 'g2'},
            'g2': {'challenge': {'subject': '选择题', 'path': None},
                   'chooses': [{'id': 1}], 'game': {'status': 0},
                   'prev_game': 'g1', 'next_game': None},
        })
        stats = self._stats()
        coverage = levels.Coverage()
        with mock.patch.object(submit, 'resolve_entry',
                               new=mock.AsyncMock(return_value='g1')):
            await submit.process_experiment(
                client, self.HW, {'name': '实验', 'levels': []}, False, stats, 5,
                answers={'classrooms': []}, classroom_code='c1',
                use_ai=False, delay=0, coverage=coverage)
        self.assertEqual(coverage.get('g1')['owner'], levels.OWNER_UML)
        self.assertEqual(coverage.get('g2')['owner'], levels.OWNER_SUBMIT)
        self.assertEqual(stats['unowned'], 0)


class FakeClientContext:
    async def __aenter__(self):
        return FakeClient({})

    async def __aexit__(self, *exc_info):
        return False


class ThinDetailTests(unittest.IsolatedAsyncioTestCase):
    """回归：平台换新一轮尝试后，头几次详情是残缺的（2026-10-26 紧耦合&高内聚）。

    那一轮的关卡 gid 从 fjavozk5ml7t 变成 l9i3eofnfmpc，第一次 GET 只回
    `game` + 没有 subject/chooses 的 challenge，于是本地明明存着答案，却被判成
    「题型无法判定」的无主关卡，实验收尾校验报 1 关未完成。
    """

    HW = {'homework_id': 4000330, 'shixun_identifier': 's1', 'name': '紧耦合&高内聚'}
    THIN = {'challenge': {'id': 9}, 'game': {'status': 0},
            'prev_game': None, 'next_game': None}
    FULL = {'challenge': {'id': 9, 'subject': '内聚和耦合'}, 'chooses': [{'id': 1}],
            'game': {'status': 0}, 'prev_game': None, 'next_game': None}
    EXPERIMENT = {'name': '紧耦合&高内聚', 'levels': [
        {'title': '内聚和耦合', 'kind': 'choice', 'answered': True,
         'identifiers': ['fub3xapz74hw'],
         'answer': [{'number': 1, 'selected': ['A']}]},
    ]}

    def _stats(self):
        return {'submitted': 0, 'would_submit': 0, 'skipped_passed': 0,
                'skipped_no_answer': 0, 'skipped_error': 0, 'failed': 0,
                'processed': 0, 'unowned': 0}

    async def _process(self, payloads):
        client = SequencedClient({'g1': payloads})
        stats = self._stats()
        coverage = levels.Coverage()
        with mock.patch.object(submit, 'DETAIL_RETRY_DELAY', 0), \
                mock.patch.object(submit, 'resolve_entry',
                                  new=mock.AsyncMock(return_value='g1')):
            await submit.process_experiment(
                client, self.HW, self.EXPERIMENT, False, stats, 5,
                answers={'classrooms': []}, classroom_code='c1',
                use_ai=False, delay=0, coverage=coverage)
        return stats, coverage

    async def test_thin_detail_is_refetched(self):
        stats, coverage = await self._process([self.THIN, self.FULL])
        self.assertEqual(coverage.get('g1')['kind'], levels.KIND_CHOICE)
        self.assertEqual(stats['would_submit'], 1)      # 拿本地答案走到 dry-run 提交
        self.assertEqual(stats['unowned'], 0)

    async def test_permanently_thin_detail_falls_back_to_chain_order(self):
        # 怎么重读都拿不到标题时，按关卡顺序对本地答案，不能丢成无主关卡
        stats, coverage = await self._process([self.THIN])
        self.assertEqual(coverage.get('g1')['kind'], levels.KIND_CHOICE)
        self.assertEqual(stats['unowned'], 0)
        self.assertEqual(coverage.get('g1')['owner'], levels.OWNER_SUBMIT)
        # 但题目本身缺了：绝不拿空答案去提交，宁可报错等下一轮
        self.assertEqual(stats['skipped_error'], 1)

    def test_recorded_kind_never_guessed_from_thin_detail(self):
        self.assertEqual(levels.classify_level(self.THIN, 'choice'), levels.KIND_CHOICE)
        self.assertEqual(levels.classify_level(self.THIN, 'code'), levels.KIND_CODE)
        self.assertEqual(levels.classify_level(self.THIN, 'uml'), levels.KIND_GRAPHIC)
        self.assertEqual(levels.classify_level(self.THIN), levels.KIND_UNKNOWN)

    def test_detail_has_clues(self):
        self.assertFalse(levels.detail_has_clues(self.THIN))
        self.assertFalse(levels.detail_has_clues({}))
        self.assertTrue(levels.detail_has_clues(self.FULL))
        self.assertTrue(levels.detail_has_clues(
            {'challenge': {'path': 'submit/a.py'}, 'game': {'status': 0}}))
        self.assertTrue(levels.detail_has_clues({'game': {'status': 2}}))


class SequencedClient:
    """同一个 gid 按顺序返回不同详情，最后一次重复。"""

    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    async def get(self, path, params, *, strict_status=True):
        gid = path.rsplit('/', 1)[-1].removesuffix('.json')
        self.calls.append(gid)
        seq = self.payloads[gid]
        return seq.pop(0) if len(seq) > 1 else seq[0]


class RunAllCoverageTests(unittest.IsolatedAsyncioTestCase):
    """run_all 必须把收尾校验的结论计入 stats 并落盘报告。"""

    def _answers(self, tmp):
        path = Path(tmp) / 'answers.json'
        path.write_text(json.dumps({'kind': 'class-answers', 'classrooms': []}),
                        encoding='utf-8')
        return path

    async def _run(self, findings, apply=True):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        report_path = Path(tmp.name) / 'unfinished.json'
        os.environ['EDUCODER_UNFINISHED_REPORT'] = str(report_path)
        self.addCleanup(os.environ.pop, 'EDUCODER_UNFINISHED_REPORT', None)

        course = SimpleNamespace(identifier='c1', name='软件工程', created_at='2026-09-01')

        async def fake_courses(client):
            return [course]

        async def fake_rows(client, code):
            return [{'name': '软件详细设计-2', 'homework_id': 4102633,
                     'shixun_finished_status': 0}]

        async def fake_choice(client, hw, experiment, apply, stats, poll, **kwargs):
            stats['submitted'] += 1
            stats['processed'] += 1

        async def fake_uml(client, hw, apply, stats, poll, **kwargs):
            stats['processed'] += 1

        async def fake_audit(client, hw, coverage=None, limit=200, entry=None):
            return findings

        with mock.patch.multiple(
                submit_all,
                open_client=FakeClientContext,
                fetch_courses=fake_courses,
                fetch_homework_rows=fake_rows,
                process_choice_code=fake_choice,
                process_uml=fake_uml), \
                mock.patch.object(levels, 'audit_experiment', fake_audit):
            stats = await submit_all.run_all(
                apply, None, None, 10, None, False, False, False,
                self._answers(tmp.name), delay=0)
        return stats, report_path

    async def test_unfinished_levels_are_counted_and_reported(self):
        findings = [{'gid': 'g2', 'subject': '事务型结构图',
                     'kind': levels.KIND_CHOICE, 'owner': None, 'action': 'unknown'}]
        stats, report_path = await self._run(findings)
        self.assertEqual(stats['unfinished'], 1)
        self.assertEqual(stats['unowned'], 1)
        payload = json.loads(report_path.read_text(encoding='utf-8'))
        self.assertEqual(payload['experiments'][0]['homework'], '软件详细设计-2')
        self.assertEqual(payload['experiments'][0]['levels'][0]['subject'], '事务型结构图')
        self.assertEqual(payload['unowned_levels'], 1)

    async def test_clean_run_writes_no_report(self):
        stats, report_path = await self._run([])
        self.assertEqual(stats['unfinished'], 0)
        self.assertFalse(report_path.exists())


class SubmitAllWiringTests(unittest.IsolatedAsyncioTestCase):
    """submit_all：入口只解析一次；平台进度对账。"""

    def _answers(self, tmp):
        path = Path(tmp) / 'answers.json'
        path.write_text(json.dumps({'kind': 'class-answers', 'classrooms': []}),
                        encoding='utf-8')
        return path

    def _course(self):
        return SimpleNamespace(identifier='c1', name='软件工程', created_at='2026-09-01')

    def _row(self, finished=0):
        return {'name': '紧耦合&高内聚', 'homework_id': 4000330,
                'shixun_identifier': 's1', 'shixun_finished_status': finished}

    async def _run(self, *, rows_sequence, seen):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.environ['EDUCODER_UNFINISHED_REPORT'] = str(Path(tmp.name) / 'u.json')
        self.addCleanup(os.environ.pop, 'EDUCODER_UNFINISHED_REPORT', None)
        rows = list(rows_sequence)

        async def fake_courses(client):
            return [self._course()]

        async def fake_rows(client, code):
            return rows.pop(0) if len(rows) > 1 else rows[0]

        async def fake_choice(client, hw, experiment, apply, stats, poll, **kwargs):
            seen.setdefault('choice', []).append(kwargs.get('entry'))
            stats['submitted'] += 1
            stats['processed'] += 1

        async def fake_uml(client, hw, apply, stats, poll, **kwargs):
            seen.setdefault('uml', []).append(kwargs.get('entry'))

        async def fake_audit(client, apply, stats, coverage, course, hw, report,
                             entry=None):
            seen['audit'] = entry

        resolve = mock.AsyncMock(return_value='ENTRY')
        seen['resolve'] = resolve
        with mock.patch.multiple(
                submit_all,
                open_client=FakeClientContext,
                fetch_courses=fake_courses,
                fetch_homework_rows=fake_rows,
                process_choice_code=fake_choice,
                process_uml=fake_uml,
                resolve_entry=resolve), \
                mock.patch.object(submit_all, 'audit_experiment', fake_audit):
            stats = await submit_all.run_all(
                True, None, None, 10, None, False, False, False,
                self._answers(tmp.name), delay=0)
        return stats

    async def test_entry_is_shared_by_three_chains(self):
        seen = {}
        stats = await self._run(rows_sequence=[[self._row()]], seen=seen)
        self.assertEqual(seen['choice'], ['ENTRY'])
        self.assertEqual(seen['uml'], ['ENTRY'])
        self.assertEqual(seen['audit'], 'ENTRY')
        self.assertEqual(seen['resolve'].await_count, 1)
        self.assertEqual(stats['unowned'], 0)

    async def test_platform_still_unfinished_is_reported(self):
        # 对账时平台还是「未完成」→ 单独计数，不与评测通过的结果混在一起
        seen = {}
        stats = await self._run(rows_sequence=[[self._row(0)], [self._row(0)]], seen=seen)
        self.assertEqual(stats['stale_homework'], 1)

    async def test_platform_finished_after_round_is_clean(self):
        seen = {}
        stats = await self._run(rows_sequence=[[self._row(0)], [self._row(1)]], seen=seen)
        self.assertEqual(stats['stale_homework'], 0)


class AuditUnreadableTests(unittest.IsolatedAsyncioTestCase):
    """详情读不全不能报成「未通关」：计入 audit_error。"""

    async def test_unreadable_counts_as_audit_error(self):
        findings = [{'gid': 'g9', 'subject': '(未命名关卡)',
                     'kind': levels.KIND_UNKNOWN, 'owner': None,
                     'action': None, 'unreadable': True}]
        stats = {'audit_error': 0, 'unfinished': 0, 'unowned': 0}
        report: list[dict] = []
        course = SimpleNamespace(identifier='c1', name='软件工程')
        with mock.patch.object(submit_all.levelmod, 'audit_experiment',
                               new=mock.AsyncMock(return_value=findings)):
            await submit_all.audit_experiment(
                FakeClient({}), True, stats, levels.Coverage(), course,
                {'name': '实验', 'homework_id': 1}, report)
        self.assertEqual(stats['audit_error'], 1)
        self.assertEqual(stats['unfinished'], 0)
        self.assertEqual(stats['unowned'], 0)      # 不能误导成「无人负责」
        self.assertEqual(report, [])

    async def test_mixed_findings(self):
        findings = [
            {'gid': 'g1', 'subject': 'A', 'kind': 'choice', 'owner': 'submit',
             'action': 'attempted'},
            {'gid': 'g2', 'subject': 'B', 'kind': 'choice', 'owner': 'submit',
             'action': 'attempted', 'unreadable': True},
        ]
        stats = {'audit_error': 0, 'unfinished': 0, 'unowned': 0}
        report: list[dict] = []
        course = SimpleNamespace(identifier='c1', name='软件工程')
        with mock.patch.object(submit_all.levelmod, 'audit_experiment',
                               new=mock.AsyncMock(return_value=findings)):
            await submit_all.audit_experiment(
                FakeClient({}), True, stats, levels.Coverage(), course,
                {'name': '实验', 'homework_id': 1}, report)
        self.assertEqual(stats['audit_error'], 1)
        self.assertEqual(stats['unfinished'], 1)
        self.assertEqual([lv['gid'] for lv in report[0]['levels']], ['g1'])


if __name__ == '__main__':
    unittest.main()
