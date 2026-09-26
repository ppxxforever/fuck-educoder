import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

from educoder_reminder.homeworks import BEIJING, Homework
from educoder_reminder.notifications import connect, deliver, quota_remaining, receiver_id, select_notices
from educoder_reminder.serverchan import PushError, endpoint, validate_response
from educoder_reminder.storage import save_snapshot
from educoder_reminder import remind

NOW = datetime(2026, 9, 24, 12, tzinfo=BEIJING)
KEY = 'sctp123tFakeTestKey'


def homework(i=1, hours=12):
    return Homework('joined', '课堂', i, 4, '实验', (NOW + timedelta(hours=hours)).isoformat(),
                    (NOW - timedelta(days=1)).isoformat(), False, False, ['提交中'],
                    'https://www.educoder.net/classrooms/joined/shixun_homework')


class NotificationsTests(unittest.IsolatedAsyncioTestCase):
    def test_upcoming_five_day_boundary_and_exclusions(self):
        items = [homework(1, 120), homework(2, 120.01), homework(3, 0),
                 replace(homework(4), completed=True), replace(homework(5), archived=True),
                 replace(homework(6), deadline=None), homework(7, 1)]
        title, body = remind.upcoming_message(items, NOW)
        self.assertIn('2 项', title)
        self.assertEqual(body.count('打开课堂作业列表'), 2)

    async def test_custom_summary_keeps_formal_events_unsent(self):
        self.save([homework()])
        transport = AsyncMock()
        await deliver(self.db, KEY, [], NOW, 5, transport=transport, test=True,
                      test_message=('测试汇总', '模拟作业清单'))
        transport.assert_awaited_once_with(KEY, '测试汇总', '模拟作业清单')
        self.assertEqual(self.db.execute('SELECT count(*) FROM push_events').fetchone()[0], 0)
        self.assertEqual(len(self.select()), 1)
        self.assertEqual(quota_remaining(self.db, self.receiver, NOW, 5), 4)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.db = connect(self.path)
        self.addCleanup(self.db.close)
        self.receiver = receiver_id(KEY)

    def save(self, items):
        save_snapshot(self.path, 'me', items, NOW)

    def select(self, now=NOW, mode='once'):
        return select_notices(self.db, 'me', self.receiver, now, mode)

    async def test_windows_merge_dedup_and_one_hour_catchup(self):
        self.save([homework(1, 25), homework(2, 24), homework(3, 1), homework(4, .5), homework(5, 0)])
        notices = self.select()
        self.assertEqual([(n.homework.id, n.stage) for n in notices], [(4, '1h'), (3, '1h'), (2, '24h')])
        transport = AsyncMock()
        await deliver(self.db, KEY, notices, NOW, 5, transport=transport)
        transport.assert_awaited_once()
        self.assertEqual(self.select(), [])
        self.assertEqual([(n.homework.id,n.stage) for n in self.select(NOW + timedelta(hours=23))], [(2,'1h'),(1,'24h')])

    async def test_postponement_and_return_to_old_deadline_rearm(self):
        item = homework()
        self.save([item])
        await deliver(self.db, KEY, self.select(), NOW, 5, transport=AsyncMock())
        self.save([replace(item, deadline=(NOW + timedelta(hours=48)).isoformat())])
        self.assertEqual(self.select(), [])
        self.save([item])
        self.assertEqual(len(self.select()), 1)

    async def test_undated_once_or_daily(self):
        self.save([replace(homework(), deadline=None)])
        await deliver(self.db, KEY, self.select(), NOW, 5, transport=AsyncMock())
        self.assertEqual(self.select(NOW + timedelta(days=1)), [])
        await deliver(self.db, KEY, self.select(mode='daily'), NOW, 5, transport=AsyncMock())
        self.assertEqual(self.select(mode='daily'), [])
        self.assertEqual(len(self.select(NOW + timedelta(days=1), 'daily')), 1)

    async def test_bounded_retry_backoff_and_quota(self):
        self.save([homework()])
        failing = AsyncMock(side_effect=PushError('模拟服务拒绝'))
        for minutes in [0, 5, 35]:
            at = NOW + timedelta(minutes=minutes)
            with self.assertRaises(PushError):
                await deliver(self.db, KEY, self.select(at), at, 5, transport=failing)
            self.assertEqual(self.select(at + timedelta(seconds=1)), [])
        self.assertEqual(self.select(NOW + timedelta(hours=1)), [])
        self.assertEqual(quota_remaining(self.db, self.receiver, NOW, 5), 2)

    async def test_quota_keeps_events_pending_until_next_day(self):
        self.save([replace(homework(), deadline=None)])
        transport = AsyncMock()
        await deliver(self.db, KEY, [], NOW, 1, transport=transport, test=True)
        self.assertEqual(await deliver(self.db, KEY, self.select(), NOW, 1, transport=transport), 'quota_exhausted')
        self.assertEqual(len(self.select(NOW + timedelta(days=1))), 1)
        self.assertEqual(quota_remaining(self.db, self.receiver, NOW + timedelta(days=1), 1), 1)
        transport.assert_awaited_once()

    def test_completed_archived_and_inactive_not_selected(self):
        self.save([replace(homework(1), completed=True), replace(homework(2), archived=True), homework(3)])
        self.save([])
        self.assertEqual(self.select(), [])

    def test_scoped_update_does_not_deactivate_other_classroom(self):
        first, second = homework(1), replace(homework(2), course_id='other')
        self.save([first, second])
        save_snapshot(self.path, 'me', [], NOW, scopes={('joined', 4)})
        self.assertEqual([n.homework.id for n in self.select()], [2])

    async def test_tick_rechecks_completed_homework_before_sending(self):
        item = homework()
        self.save([item])
        async def recheck(username, notices):
            self.save([replace(item, completed=True)])
            return {('joined', 4)}
        with patch.object(remind, 'DATABASE', self.path), patch.object(remind, 'datetime', wraps=datetime) as clock, \
                patch.object(remind, 'recheck', side_effect=recheck) as verify, \
                patch.object(remind, 'deliver', new_callable=AsyncMock) as deliver_mock:
            clock.now.return_value = NOW
            await remind.tick(('me', KEY, 'once', 'defer', 5, 6, 60))
            verify.assert_awaited_once()
            self.assertEqual(deliver_mock.call_args.args[2], [])

    async def test_recheck_failure_never_sends(self):
        self.save([homework()])
        with patch.object(remind, 'DATABASE', self.path), patch.object(remind, 'datetime', wraps=datetime) as clock, \
                patch.object(remind, 'recheck', side_effect=PushError('模拟复核失败')), \
                patch.object(remind, 'deliver', new_callable=AsyncMock) as deliver_mock:
            clock.now.return_value = NOW
            with self.assertRaises(PushError):
                await remind.tick(('me', KEY, 'once', 'defer', 5, 6, 60))
            deliver_mock.assert_not_awaited()

    def test_provider_and_response_validation(self):
        self.assertEqual(endpoint(KEY)[0], 'SC3')
        self.assertEqual(endpoint('SCTfake')[0], 'Turbo')
        for key in ['sctp123tbad/key', 'unknown', 'SCTkey?redirect=1']:
            with self.assertRaises(PushError):
                endpoint(key)
        validate_response(200, {'code': 0})
        for status, body in [(429, {'code': 0}), (200, {'code': 1}), (200, {}), (200, {'code': False})]:
            with self.assertRaises(PushError):
                validate_response(status, body)
