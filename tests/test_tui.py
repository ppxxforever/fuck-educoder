"""TUI 数据层与界面的冒烟测试（不联网、不提交）。"""
import asyncio
import hashlib
import json
import os
import sqlite3
import sys
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from zoneinfo import ZoneInfo

from educoder_reminder.tui import data
from educoder_reminder.tui.runner import Options, build_command

BEIJING = ZoneInfo('Asia/Shanghai')


def homework_record(course_id, course_name, hw_id, kind, name, deadline, publish,
                    archived=False, completed=False, status=None):
    return {
        'course_id': course_id, 'course_name': course_name, 'id': hw_id,
        'kind': kind, 'name': name, 'deadline': deadline, 'publish_at': publish,
        'archived': archived, 'completed': completed, 'status': status or [],
        'url': f'https://www.educoder.net/classrooms/{course_id}/shixun_homework',
    }


class Fixture:
    """在临时目录里造一份最小可用的本地状态。"""

    def __init__(self, root: Path):
        self.root = root
        self.db = root / 'reminder.sqlite3'
        self.homeworks_json = root / 'homeworks.json'
        self.accounts = root / 'accounts.json'
        self.queue_state = root / 'queue_state.json'
        self.courses = root / 'courses.json'
        self.auth = root / 'auth.sqlite3'
        self.env = root / '.env'
        self.queue_log = root / 'queue.log'
        self.tui_log = root / 'tui.log'
        self.username = 'demo_login'

    def write(self, now: datetime) -> None:
        def iso(hours: float) -> str:
            return (now + timedelta(hours=hours)).isoformat()

        records = [
            homework_record('c1', '软件工程导论', 1, 4, '实验三 顺序图', iso(0.5), iso(-10)),
            homework_record('c1', '软件工程导论', 2, 4, '实验四 用例图', iso(6), iso(-10)),
            homework_record('c2', '数据库原理', 3, 1, '第 4 章 图文作业', iso(30), iso(-10)),
            homework_record('c2', '数据库原理', 4, 4, '实验二 实体联系图', iso(-5), iso(-20)),
            homework_record('c3', '面向对象分析', 5, 4, '无截止时间的实验', None, iso(-10)),
            homework_record('c3', '面向对象分析', 6, 4, '已完成的实验', iso(48), iso(-10),
                            completed=True),
            homework_record('c3', '面向对象分析', 7, 4, '未发布的实验', iso(48), iso(48)),
            homework_record('c3', '面向对象分析', 8, 1, '归档作业', iso(-400), iso(-500),
                            archived=True),
        ]
        connection = sqlite3.connect(self.db)
        connection.executescript('''
            CREATE TABLE homeworks (
                username TEXT, course_id TEXT, kind INTEGER, homework_id INTEGER,
                deadline TEXT, completed INTEGER, archived INTEGER, present INTEGER,
                payload TEXT, synced_at TEXT);
            CREATE TABLE sync_state (username TEXT, synced_at TEXT);
        ''')
        for record in records:
            connection.execute(
                'INSERT INTO homeworks VALUES (?,?,?,?,?,?,?,1,?,?)',
                (self.username, record['course_id'], record['kind'], record['id'],
                 record['deadline'], record['completed'], record['archived'],
                 json.dumps(record, ensure_ascii=False), now.isoformat()))
        connection.execute('INSERT INTO sync_state VALUES (?,?)', (self.username, now.isoformat()))
        connection.commit()
        connection.close()

        self.accounts.write_text(json.dumps([
            {'account': '13800000000', 'password': 'Secret123', 'note': '本人'},
            {'account': '13900000000', 'password': 'enc:not-decryptable', 'note': '同学'},
        ], ensure_ascii=False), encoding='utf-8')
        self.queue_state.write_text(json.dumps({
            '13800000000': {'status': 'done', 'submitted': 3, 'failed': 0,
                            'skipped_passed': 10, 'finished_at': '2026-10-24 10:00:00'},
        }, ensure_ascii=False), encoding='utf-8')
        self.courses.write_text(json.dumps([
            {'id': 1, 'name': '软件工程导论', 'identifier': 'c1'},
        ], ensure_ascii=False), encoding='utf-8')
        self.env.write_text(
            "EDUCODER_LOGIN_ACCOUNT='13800000000'\n"
            "EDUCODER_LOGIN_PASSWORD='Secret123'\n"
            "EDUCODER_TOKEN='token'\nEDUCODER_COOKIE='cookie'\n"
            "AI_API_KEY='sk-test'\nAI_MODEL='deepseek-chat'\n"
            "SYNC_INTERVAL_HOURS='6'\n", encoding='utf-8')
        auth = sqlite3.connect(self.auth)
        auth.executescript('CREATE TABLE login_attempts (username TEXT, attempted_at REAL);')
        auth.execute('INSERT INTO login_attempts VALUES (?,?)',
                     (hashlib.sha256(b'13800000000').hexdigest(), time.time() - 1200))
        auth.commit()
        auth.close()
        self.queue_log.write_text('队列日志一行\n', encoding='utf-8')

    def patches(self):
        return mock.patch.multiple(
            data,
            REMINDER_DB=self.db,
            HOMEWORKS_JSON=self.homeworks_json,
            ACCOUNTS=self.accounts,
            QUEUE_STATE=self.queue_state,
            COURSES_CACHE=self.courses,
            AUTH_DB=self.auth,
            ENV_PATH=self.env,
            QUEUE_LOG=self.queue_log,
            TUI_LOG=self.tui_log,
            DATA_DIR=self.root,
        )


class TuiDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = datetime(2026, 10, 24, 12, 0, tzinfo=BEIJING)
        self.fixture = Fixture(self.root)
        self.fixture.write(self.now)
        self.patch = self.fixture.patches()
        self.patch.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.patch.stop)
        self.addCleanup(lambda: [
            os.environ.pop(key, None)
            for key in ('EDUCODER_LOGIN_ACCOUNT', 'EDUCODER_LOGIN_PASSWORD',
                        *data.SESSION_KEYS)
        ])

    def test_session_and_cooldown(self):
        session = data.session()
        self.assertEqual(session['account'], '13800000000')
        self.assertTrue(session['session_ready'])
        self.assertTrue(session['ai_configured'])
        self.assertEqual(session['sync_hours'], '6')
        self.assertGreater(session['cooldown'], 0)
        self.assertLessEqual(session['cooldown'], 1800)

    def test_homework_rows_and_states(self):
        rows = data.homework_rows(self.now)
        by_name = {row['name']: row['state'] for row in rows}
        self.assertEqual(by_name['实验三 顺序图'], 'pending')
        self.assertEqual(by_name['实验二 实体联系图'], 'overdue')
        self.assertEqual(by_name['无截止时间的实验'], 'no_deadline')
        self.assertEqual(by_name['已完成的实验'], 'completed')
        self.assertEqual(by_name['未发布的实验'], 'unpublished')
        self.assertEqual(by_name['归档作业'], 'archived')
        # 待完成排最前，按截止时间升序
        self.assertEqual([r['name'] for r in rows[:3]],
                         ['实验三 顺序图', '实验四 用例图', '第 4 章 图文作业'])

    def test_summary_counts(self):
        summary = data.summary(data.homework_rows(self.now), self.now)
        self.assertEqual(summary['total'], 8)
        self.assertEqual(summary['urgent_1h'], 1)
        self.assertEqual(summary['urgent_24h'], 2)
        self.assertEqual(summary['counts']['pending'], 3)
        self.assertEqual(summary['counts']['overdue'], 1)

    def test_queue_rows_and_passwords(self):
        rows = data.queue_rows()
        self.assertEqual(len(rows), 2)
        done = [r for r in rows if r['status'] == 'done'][0]
        self.assertEqual(done['submitted'], 3)
        self.assertEqual(data.password_display({'password': 'Secret123'}), 'Sec***')
        self.assertEqual(
            data.password_display({'password': 'Secret123'}, reveal=True), 'Secret123')
        self.assertEqual(data.password_display({'password': 'enc:broken'}), '已加密')
        self.assertEqual(data.password_display({'password': ''}), '缺失')

    def test_add_and_remove_account(self):
        data.add_account('13700000000', 'NewPass1', '测试')
        self.assertIn('13700000000', data.account_names())
        self.assertTrue(data.remove_account('13700000000'))
        self.assertNotIn('13700000000', data.account_names())
        with self.assertRaises(ValueError):
            data.add_account('', 'x')

    def test_per_account_classrooms(self):
        data.add_account('13700000000', 'NewPass1', '测试', ['c1', '数据库，c1'])
        self.assertEqual(data.account_classrooms('13700000000'), ['c1', '数据库'])
        rows = {r['account']: r for r in data.queue_rows()}
        self.assertEqual(rows['13700000000']['classrooms'], ['c1', '数据库'])
        self.assertEqual(rows['13800000000']['classrooms'], [])
        data.set_account_classrooms('13700000000', ['c2'])
        self.assertEqual(data.account_classrooms('13700000000'), ['c2'])
        data.set_account_classrooms('13700000000', [])
        self.assertEqual(data.account_classrooms('13700000000'), [])
        # 更新账号时 classrooms 省略则保留原设置，显式传 [] 才清空
        data.set_account_classrooms('13700000000', ['c3'])
        data.add_account('13700000000', 'NewPass2')
        self.assertEqual(data.account_classrooms('13700000000'), ['c3'])
        data.add_account('13700000000', 'NewPass3', classrooms=[])
        self.assertEqual(data.account_classrooms('13700000000'), [])
        with self.assertRaises(ValueError):
            data.set_account_classrooms('not-exist', ['c1'])

    def test_set_queue_status(self):
        data.set_queue_status('13800000000', 'done')
        row = next(r for r in data.queue_rows() if r['account'] == '13800000000')
        self.assertEqual(row['status'], 'done')
        self.assertTrue(row['manual'])
        self.assertEqual(row['submitted'], 3)      # 保留历史计数
        data.set_queue_status('13800000000', 'pending', reset_progress=True)
        row = next(r for r in data.queue_rows() if r['account'] == '13800000000')
        self.assertEqual(row['status'], 'pending')
        self.assertEqual(row['submitted'], 0)
        data.set_queue_status('13800000000', 'failed')
        row = next(r for r in data.queue_rows() if r['account'] == '13800000000')
        self.assertEqual(row['status'], 'failed')
        self.assertEqual(row['error'], '手动标记失败')
        with self.assertRaises(ValueError):
            data.set_queue_status('not-exist', 'done')

    def test_update_account(self):
        data.update_account('13800000000', '13800000001', 'NewPass1', '新备注', ['c1'])
        self.assertIn('13800000001', data.account_names())
        self.assertNotIn('13800000000', data.account_names())
        self.assertEqual(data.account_classrooms('13800000001'), ['c1'])
        rows = {r['account']: r for r in data.queue_rows()}
        self.assertEqual(rows['13800000001']['note'], '新备注')
        self.assertEqual(rows['13800000001']['status'], 'done')   # 队列状态跟着改
        # 密码留空表示保留原密码
        data.update_account('13800000001', password=None, note='再改')
        item = next(a for a in data.accounts() if a['account'] == '13800000001')
        self.assertEqual(item['password'], 'NewPass1')
        with self.assertRaises(ValueError):
            data.update_account('13800000001', '13900000000')

    def test_activate_account_clears_session(self):
        data.activate_account('13900000000', 'Other123', clear_limit=True)
        env = data.read_env()
        self.assertEqual(env['EDUCODER_LOGIN_ACCOUNT'], '13900000000')
        self.assertEqual(env['EDUCODER_LOGIN_PASSWORD'], 'Other123')
        self.assertEqual(env['EDUCODER_TOKEN'], '')
        self.assertEqual(env['EDUCODER_COOKIE'], '')
        self.assertEqual(data.cooldown_seconds('13900000000'), 0)

    def test_display_helpers(self):
        self.assertEqual(data.human_age((self.now - timedelta(minutes=5)).isoformat(), self.now),
                         '5 分钟前')
        self.assertEqual(data.human_age('', self.now), '-')
        self.assertEqual(data.display_path(data.ROOT / 'data' / 'x.log'), 'data/x.log')
        self.assertEqual(data.format_remaining((self.now + timedelta(hours=2)).isoformat(),
                                               self.now), '剩 2小时0分')
        self.assertEqual(data.format_remaining((self.now - timedelta(days=1)).isoformat(),
                                               self.now), '逾期 1天0小时')


class TuiRunnerTests(unittest.TestCase):
    def test_build_command_adds_interpreter(self):
        argv = build_command('remind_preview', Options())
        self.assertEqual(argv[1:4], ['-u', '-m', 'educoder_reminder.remind'])
        self.assertEqual(argv[4], 'preview')

    def test_build_command_all_apply_options(self):
        argv = build_command('all_apply', Options(
            classroom='c1，数据库', limit='3', timeout='90', no_ai=True, release=True))
        self.assertEqual(argv[3], 'educoder_reminder.submit_all')
        self.assertEqual(argv[4], '--apply')
        self.assertIn('--classroom', argv)
        self.assertEqual(argv.count('--classroom'), 2)  # 中文逗号也会拆分
        self.assertIn('数据库', argv)
        self.assertIn('--limit', argv)
        self.assertIn('--poll-timeout', argv)
        self.assertIn('--no-ai', argv)
        self.assertIn('--release-envs', argv)

    def test_build_command_queue_apply(self):
        argv = build_command('queue_apply', Options(classroom='c1', gap='600'))
        self.assertTrue(argv[2].endswith('run_queue.py'))
        self.assertIn('--apply', argv)
        self.assertEqual(argv[argv.index('--gap') + 1], '600')

    def test_build_command_prepare_tasks(self):
        argv = build_command('prepare_preview', Options(
            classroom='c1，数据库', limit='3', experiment='视图', no_ai=True))
        self.assertEqual(argv[3], 'educoder_reminder.prepare')
        self.assertEqual(argv.count('--classroom'), 2)
        self.assertEqual(argv[argv.index('--limit') + 1], '3')
        self.assertEqual(argv[argv.index('--experiment') + 1], '视图')
        self.assertIn('--no-ai', argv)
        self.assertIn('--dry-run', argv)
        self.assertNotIn('--poll-timeout', argv)

        argv = build_command('prepare_apply', Options(classroom='c1'))
        self.assertNotIn('--dry-run', argv)

    def test_unknown_options_not_forwarded(self):
        argv = build_command('remind_preview', Options(classroom='c1', limit='5', no_ai=True))
        for flag in ('--classroom', '--limit', '--no-ai'):
            self.assertNotIn(flag, argv)


class TuiAppTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = datetime.now(BEIJING)
        self.fixture = Fixture(self.root)
        self.fixture.write(self.now)
        self.patch = self.fixture.patches()
        self.patch.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.patch.stop)

    async def test_mount_tabs_and_filters(self):
        from textual.widgets import Input, Select, TabbedContent

        from educoder_reminder.tui.app import EducoderTUI

        app = EducoderTUI()
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            tabs = app.query_one(TabbedContent)
            self.assertEqual(tabs.active, 'tab-overview')
            self.assertEqual(len(app.todo_rows), 4)  # pending + overdue

            await pilot.press('2')
            await pilot.pause()
            self.assertEqual(tabs.active, 'tab-homework')
            self.assertEqual(len(app.hw_visible), 8)

            app.query_one('#hw-search', Input).value = '用例'
            await pilot.pause()
            self.assertEqual(len(app.hw_visible), 1)

            app.query_one('#hw-state', Select).value = 'pending'
            await pilot.pause()
            self.assertEqual(len(app.hw_visible), 1)

            app.query_one('#hw-state', Select).value = 'completed'
            await pilot.pause()
            self.assertEqual(app.hw_visible, [])

            await pilot.press('3')
            await pilot.pause()
            self.assertEqual(app.selected_account, '13800000000')
            self.assertEqual(len(app.queue_rows), 2)

            await pilot.press('5')
            await pilot.pause()
            self.assertEqual(tabs.active, 'tab-log')

    async def test_edit_account_and_save(self):
        from textual.widgets import Input, TabbedContent

        from educoder_reminder.tui.app import EducoderTUI

        app = EducoderTUI()
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            app.query_one(TabbedContent).active = 'tab-queue'
            await pilot.pause()
            app.selected_account = '13800000000'
            app.action_edit_account()
            await pilot.pause()
            self.assertEqual(app.editing_account, '13800000000')
            self.assertEqual(app.query_one('#q-account', Input).value, '13800000000')
            self.assertEqual(app.query_one('#q-password', Input).value, 'Secret123')
            self.assertIn('修改账号', str(
                app.query_one('#queue-form-title').render()))

            app.query_one('#q-note', Input).value = '改过的备注'
            app.action_save_account()
            await pilot.pause()
            self.assertEqual(app.editing_account, '')
            accounts = json.loads(Path(self.fixture.accounts).read_text(encoding='utf-8'))
            item = next(a for a in accounts if a['account'] == '13800000000')
            self.assertEqual(item['note'], '改过的备注')
            self.assertEqual(item['password'], 'Secret123')   # 未改密码

    async def test_manual_status_modal(self):
        from textual.widgets import TabbedContent

        from educoder_reminder.tui.app import EducoderTUI, StatusScreen

        app = EducoderTUI()
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            app.query_one(TabbedContent).active = 'tab-queue'
            await pilot.pause()
            app.selected_account = '13800000000'
            app.action_set_status()
            await pilot.pause()
            self.assertIsInstance(app.screen, StatusScreen)
            await pilot.press('d')      # 标记完成
            await pilot.pause()
            rows = {r['account']: r for r in app.queue_rows}
            self.assertEqual(rows['13800000000']['status'], 'done')
            self.assertTrue(rows['13800000000']['manual'])

            app.selected_account = '13800000000'
            app.action_set_status()
            await pilot.pause()
            await pilot.press('z')      # 清空进度并待处理
            await pilot.pause()
            rows = {r['account']: r for r in app.queue_rows}
            self.assertEqual(rows['13800000000']['status'], 'pending')
            self.assertEqual(rows['13800000000']['submitted'], 0)

    async def test_course_picker_saves_per_account(self):
        from textual.widgets import TabbedContent

        from educoder_reminder.tui.app import CoursePickerScreen, EducoderTUI

        app = EducoderTUI()
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            app.query_one(TabbedContent).active = 'tab-queue'
            await pilot.pause()
            app.selected_account = '13800000000'
            app.action_pick_courses()
            await pilot.pause()
            self.assertIsInstance(app.screen, CoursePickerScreen)
            await pilot.press('a')   # 全选
            await pilot.pause()
            await pilot.press('s')   # 保存
            await pilot.pause()
            self.assertEqual(data.account_classrooms('13800000000'), ['c1'])
            rows = {r['account']: r for r in app.queue_rows}
            self.assertEqual(rows['13800000000']['classrooms'], ['c1'])

            # 再次打开并清空，表示恢复全部课堂
            app.selected_account = '13800000000'
            app.action_pick_courses()
            await pilot.pause()
            await pilot.press('n')
            await pilot.pause()
            await pilot.press('s')
            await pilot.pause()
            self.assertEqual(data.account_classrooms('13800000000'), [])

    async def test_single_account_argv_ignores_global_classroom(self):
        from textual.widgets import Input, TabbedContent

        from educoder_reminder.tui.app import EducoderTUI

        app = EducoderTUI()
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            app.query_one(TabbedContent).active = 'tab-tasks'
            await pilot.pause()
            app.query_one('#task-classroom', Input).value = '全局课程'
            await pilot.pause()
            # 该账号没配课程：不带 --classroom，也不受任务页全局筛选影响
            argv = app._account_argv('13800000000')
            self.assertNotIn('--classroom', argv)
            self.assertIn('--only', argv)
            self.assertIn('13800000000', argv)
            self.assertIn('--force', argv)
            self.assertNotIn('全局课程', argv)

            # 配了课程：命令里显式带 --classroom，便于核对
            data.set_account_classrooms('13800000000', ['c1', '数据库'])
            argv = app._account_argv('13800000000')
            self.assertEqual(argv.count('--classroom'), 2)
            self.assertIn('c1', argv)
            self.assertIn('数据库', argv)
            self.assertNotIn('全局课程', argv)

    async def test_prepare_shortcuts_select_task(self):
        from textual.widgets import Select, TabbedContent

        from educoder_reminder.tui.app import EducoderTUI

        app = EducoderTUI()
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            started = []
            # 只验证「按钮」把任务切对并触发运行，不真的联网/AI
            app._start_task = lambda key, *a, **kw: started.append(key)

            await pilot.press('P')
            await pilot.pause()
            self.assertEqual(app.query_one(TabbedContent).active, 'tab-tasks')
            self.assertEqual(app.query_one('#task-kind', Select).value,
                             'prepare_preview')
            self.assertEqual(started, ['prepare_preview'])

            await pilot.press('G')
            await pilot.pause()
            self.assertEqual(app.query_one('#task-kind', Select).value,
                             'prepare_apply')
            self.assertEqual(started, ['prepare_preview', 'prepare_apply'])

    async def test_dangerous_task_requires_confirmation(self):
        from textual.widgets import RichLog, Select, TabbedContent

        from educoder_reminder.tui.app import ConfirmScreen, EducoderTUI

        app = EducoderTUI()
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            app.query_one(TabbedContent).active = 'tab-tasks'
            app.query_one('#task-kind', Select).value = 'all_apply'
            await pilot.pause()
            app.action_run_task()
            await pilot.pause()
            self.assertIsInstance(app.screen, ConfirmScreen)
            await pilot.press('escape')
            await pilot.pause()
            self.assertEqual(app.running_task, '')

            # 确认后才真正执行（用无害命令代替真实提交）
            app._start_task('verify_all', argv=[
                sys.executable, '-c', 'print("confirmed-run")'])
            await pilot.pause()
            self.assertIsInstance(app.screen, ConfirmScreen)
            await pilot.press('y')
            for _ in range(300):
                await pilot.pause()
                if not app.running_task:
                    break
                await asyncio.sleep(0.05)
            self.assertEqual(app.running_task, '')
            log = app.query_one('#task-log', RichLog)
            self.assertIn('confirmed-run', '\n'.join(line.text for line in log.lines))

    async def test_harmless_task_runs_subprocess(self):
        from textual.widgets import RichLog, Select, TabbedContent

        from educoder_reminder.tui.app import EducoderTUI

        app = EducoderTUI()
        async with app.run_test(size=(150, 45)) as pilot:
            await pilot.pause()
            app.query_one(TabbedContent).active = 'tab-tasks'
            # 只打印帮助/参数错误，不联网、不提交
            # 用自定义 argv 跑一条纯本地命令，验证子进程输出能实时进日志
            app._launch('queue_preview', [
                sys.executable, '-c',
                'print("tui-test-line"); print("tui-test-done")'])
            for _ in range(300):
                await pilot.pause()
                if not app.running_task:
                    break
                await asyncio.sleep(0.05)
            self.assertEqual(app.running_task, '')
            log = app.query_one('#task-log', RichLog)
            text = '\n'.join(line.text for line in log.lines)
            self.assertIn('tui-test-line', text)
            self.assertIn('退出码 0', text)


if __name__ == '__main__':
    unittest.main()
