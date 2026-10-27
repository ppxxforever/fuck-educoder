"""已截止/归档实验的跳过判定。"""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from educoder_reminder.submit import homework_deadline, is_homework_closed

BEIJING = ZoneInfo('Asia/Shanghai')


def row(**extra):
    base = {'name': '实验', 'is_archive': False, 'end_time_s': '', 'end_time': ''}
    base.update(extra)
    return base


class ClosedTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 24, 12, 0, tzinfo=BEIJING)

    def iso(self, hours):
        return (self.now + timedelta(hours=hours)).isoformat()

    def test_archived(self):
        self.assertTrue(is_homework_closed(row(is_archive=True), self.now))

    def test_past_deadline(self):
        self.assertTrue(is_homework_closed(row(end_time_s=self.iso(-1)), self.now))

    def test_future_deadline(self):
        self.assertFalse(is_homework_closed(row(end_time_s=self.iso(1)), self.now))

    def test_end_time_fallback(self):
        self.assertTrue(is_homework_closed(row(end_time=self.iso(-2)), self.now))
        self.assertFalse(is_homework_closed(row(end_time=self.iso(2)), self.now))

    def test_prefers_precise_deadline(self):
        item = row(end_time_s=self.iso(-1), end_time=self.iso(24))
        self.assertTrue(is_homework_closed(item, self.now))

    def test_no_deadline_not_closed(self):
        self.assertFalse(is_homework_closed(row(), self.now))
        self.assertIsNone(homework_deadline(row()))

    def test_malformed_deadline_not_closed(self):
        self.assertFalse(is_homework_closed(row(end_time_s='not-a-time'), self.now))


if __name__ == '__main__':
    unittest.main()
