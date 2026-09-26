import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from educoder_reminder.courses import Course
from educoder_reminder.errors import CollectionError
from educoder_reminder.homeworks import BEIJING, collect_homeworks, parse_homework
from educoder_reminder.storage import save_snapshot

COURSE = Course(1, '测试课堂', 'joined', 'https://www.educoder.net/classrooms/joined/announcement', True)
NOW = datetime(2026, 9, 24, 12, tzinfo=BEIJING)


def row(i=1, **changes):
    return dict(homework_id=i, name='作业', is_archive=False, status=['提交中'],
                shixun_finished_status=0, un_commit_work=True,
                publish_time='2026-09-01 12:00', end_time='2026-09-25 12:00',
                end_time_s='2026-09-25 12:00:30', **changes)


class FakeClient:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    async def get(self, path, params):
        self.calls.append((path, params))
        return self.pages[params['page'] - 1]


def page(rows, count=2):
    return dict(homework_type=4, is_end=False, query_total_count=count,
                all_count=99, homeworks=rows)


class HomeworkTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clock = patch('educoder_reminder.homeworks.datetime', wraps=datetime)
        mocked = clock.start()
        mocked.now.return_value = NOW
        self.addCleanup(clock.stop)

    async def test_expired_over_five_days_skipped_before_content_parsing(self):
        old = {'homework_id': 1, 'is_archive': False, 'end_time_s': '2026-09-19 11:59:59'}
        client = FakeClient([page([old]), page([row(2)])])
        result = await collect_homeworks(client, COURSE, 4, {'joined'}, now=NOW)
        self.assertEqual([h.id for h in result], [2])
        self.assertEqual(len(client.calls), 2)

    async def test_five_day_boundary_undated_and_postponed_retained(self):
        rows = [row(i) for i in range(1, 5)]
        for item, deadline in zip(rows, ['2026-09-19 12:00:00', '2026-09-20 12:00:00', None, '2026-10-01 12:00:00']):
            item['end_time_s'] = deadline
            item['end_time'] = deadline
        result = await collect_homeworks(FakeClient([page(rows, count=4)]), COURSE, 4, {'joined'}, now=NOW)
        self.assertEqual([h.id for h in result], [1, 2, 3, 4])

    async def test_archived_rows_skipped_before_content_parsing(self):
        archived = {'homework_id': 1, 'is_archive': True}
        client = FakeClient([page([archived]), page([row(2)])])
        result = await collect_homeworks(client, COURSE, 4, {'joined'}, limit=1)
        self.assertEqual([h.id for h in result], [2])
        self.assertEqual(len(client.calls), 2)

    async def test_all_archived_page_returns_no_homeworks(self):
        client = FakeClient([page([{'homework_id': 1, 'is_archive': True}], count=1)])
        self.assertEqual(await collect_homeworks(client, COURSE, 4, {'joined'}), [])

    async def test_pagination_uses_query_total_not_unpublished_count(self):
        client = FakeClient([page([row(1)]), page([row(2)])])
        result = await collect_homeworks(client, COURSE, 4, {'joined'}, limit=1)
        self.assertEqual([h.id for h in result], [1, 2])
        self.assertEqual([p['page'] for _, p in client.calls], [1, 2])
        self.assertTrue(all(p['status'] == 0 and p['id'] == 'joined' for _, p in client.calls))

    async def test_scope_enforced_before_request(self):
        client = FakeClient([])
        with self.assertRaises(CollectionError):
            await collect_homeworks(client, COURSE, 4, {'different'})
        self.assertEqual(client.calls, [])

    async def test_partial_and_repeated_pages_rejected(self):
        for second in [[], [row(1)]]:
            with self.subTest(second=second):
                with self.assertRaises(CollectionError):
                    await collect_homeworks(FakeClient([page([row(1)]), page(second)]), COURSE, 4, {'joined'})

    async def test_ended_course_rejected(self):
        data = page([])
        data['is_end'] = True
        with self.assertRaises(CollectionError):
            await collect_homeworks(FakeClient([data]), COURSE, 4, {'joined'})

    def test_precise_personal_deadline_and_timezone(self):
        item = parse_homework(row(), COURSE, 4)
        self.assertEqual(item.deadline, '2026-09-25T12:00:30+08:00')
        self.assertEqual(item.reminder_state(NOW), 'pending')

    def test_both_completion_fields(self):
        for kind, field, value in [(4, 'shixun_finished_status', 1), (1, 'un_commit_work', False)]:
            data = row()
            data[field] = value
            self.assertEqual(parse_homework(data, COURSE, kind).reminder_state(NOW), 'completed')

    def test_unknown_completion_not_assumed_unfinished(self):
        data = row()
        data['shixun_finished_status'] = 99
        self.assertEqual(parse_homework(data, COURSE, 4).reminder_state(NOW), 'unknown_completion')

    def test_archive_expired_and_undated(self):
        item = parse_homework(row(), COURSE, 4)
        self.assertEqual(replace(item, archived=True).reminder_state(NOW), 'archived')
        self.assertEqual(replace(item, deadline=NOW.isoformat()).reminder_state(NOW), 'overdue')
        self.assertEqual(replace(item, deadline=None).reminder_state(NOW), 'no_deadline')
        self.assertEqual(replace(item, publish_at='2026-10-01T00:00:00+08:00').reminder_state(NOW), 'unpublished')

    def test_invalid_date_rejected(self):
        data = row()
        data['end_time_s'] = '第一组明天，第二组后天'
        with self.assertRaises(CollectionError):
            parse_homework(data, COURSE, 4)

    def test_postponement_preserves_history_and_reactivates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.sqlite3'
            expired = replace(parse_homework(row(), COURSE, 4), deadline='2026-09-23T12:00:00+08:00')
            save_snapshot(path, 'me', [expired], NOW)
            future = replace(expired, deadline='2026-09-30T12:00:00+08:00')
            save_snapshot(path, 'me', [future], NOW)
            save_snapshot(path, 'me', [future], NOW)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT old_deadline,new_deadline FROM deadline_changes').fetchall(),
                                 [(expired.deadline, future.deadline)])
                self.assertEqual(db.execute('SELECT count(*) FROM homeworks').fetchone()[0], 1)
            self.assertEqual(future.reminder_state(NOW), 'pending')

    def test_disappeared_rows_inactive_other_accounts_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.sqlite3'
            item = parse_homework(row(), COURSE, 4)
            save_snapshot(path, 'me', [item], NOW)
            save_snapshot(path, 'other', [item], NOW)
            save_snapshot(path, 'me', [], NOW)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT username,present FROM homeworks ORDER BY username').fetchall(),
                                 [('me', 0), ('other', 1)])

    def test_failed_write_rolls_back_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.sqlite3'
            item = parse_homework(row(), COURSE, 4)
            save_snapshot(path, 'me', [item], NOW)
            with self.assertRaises(sqlite3.IntegrityError):
                save_snapshot(path, 'me', [replace(item, course_id=None)], NOW)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute('SELECT present FROM homeworks').fetchall(), [(1,)])
