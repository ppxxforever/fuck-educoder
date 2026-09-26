import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from educoder_reminder import remind
from educoder_reminder.errors import CollectionError
from educoder_reminder.homeworks import BEIJING
from educoder_reminder.storage import save_snapshot
from scripts.service import render

NOW = datetime(2026, 9, 24, 12, tzinfo=BEIJING)
CONFIG = ('me', 'sctp123tFakeKey', 'once', 'defer', 5, 6, 60)


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_check_validates_without_tick_or_send(self):
        with patch.object(remind, 'options', return_value=CONFIG), patch.object(remind, 'tick', new_callable=AsyncMock) as tick:
            await remind.execute('check')
            tick.assert_not_awaited()

    async def test_loop_continues_after_collection_error(self):
        with patch.object(remind, 'options', return_value=CONFIG), \
                patch.object(remind, 'tick', side_effect=[CollectionError('模拟网络故障'), 'nothing_due']) as tick, \
                patch.object(remind.asyncio, 'sleep', side_effect=[None, asyncio.CancelledError]) as sleep:
            with self.assertRaises(asyncio.CancelledError):
                await remind.execute('run')
            self.assertEqual(tick.await_count, 2)
            self.assertTrue(all(1 <= call.args[0] <= 60 for call in sleep.call_args_list))

    async def test_restart_respects_persisted_sync_time_and_six_hour_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reminder.sqlite3'
            for age, expected in [(timedelta(hours=5, minutes=59), 0), (timedelta(hours=6), 1)]:
                with self.subTest(age=age):
                    save_snapshot(path, 'me', [], NOW - age)
                    with patch.object(remind, 'DATABASE', path), patch.object(remind, 'datetime', wraps=datetime) as clock, \
                            patch.object(remind, 'crawl_homeworks', return_value=('me', [], [])) as crawl:
                        clock.now.return_value = NOW
                        self.assertEqual(await remind.tick(CONFIG), 'nothing_due')
                        self.assertEqual(crawl.await_count, expected)

    def test_second_process_lock_rejected(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(remind, 'ROOT', Path(directory)):
            with remind.process_lock():
                with self.assertRaises(CollectionError):
                    with remind.process_lock():
                        pass
            with remind.process_lock():
                pass

    def test_service_paths_escaped_no_secrets(self):
        with patch('scripts.service.pwd.getpwnam', return_value=SimpleNamespace(pw_uid=1000)):
            unit = render(Path('/srv/course work%$'), 'student')
        self.assertIn('WorkingDirectory=/srv/course work%%$', unit)
        self.assertIn('ExecStart="/srv/course work%%$$/.venv/bin/python"', unit)
        self.assertIn('User=student', unit)
        self.assertIn('KillSignal=SIGINT', unit)
        self.assertNotIn('SENDKEY', unit)

    def test_root_service_rejected(self):
        with patch('scripts.service.pwd.getpwnam', return_value=SimpleNamespace(pw_uid=0)):
            with self.assertRaises(ValueError):
                render(Path('/srv/project'), 'root')
