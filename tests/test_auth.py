import unittest
from unittest.mock import patch
from educoder_reminder.auth import signing_headers


class AuthTests(unittest.TestCase):
    def test_matches_captured_browser_request(self):
        headers = signing_headers(timestamp=1790256850591)
        self.assertEqual(headers['X-EDU-Signature'], 'b2fbfaca950022123f688176c0013049')

    def test_timestamp_refreshed_per_request(self):
        with patch('educoder_reminder.auth.time.time_ns', side_effect=[1000000, 2000000]):
            first, second = signing_headers(), signing_headers()
        self.assertEqual(first['X-EDU-Timestamp'], '1')
        self.assertEqual(second['X-EDU-Timestamp'], '2')
        self.assertNotEqual(first['X-EDU-Signature'], second['X-EDU-Signature'])
