import unittest
from educoder_reminder.courses import CollectionError, collect, parse_page


def row(i, ended=False):
    return dict(id=i, name=f'Course {i}', is_end=ended,
                first_category_url=f'/classrooms/code{i}/announcement', can_visited=True)


class CoursesTests(unittest.IsolatedAsyncioTestCase):
    async def test_pages_and_ended_filter(self):
        calls = []
        async def fetch(page, size):
            calls.append(page)
            return {'count': 3, 'courses': [row(1), row(2, True)] if page == 1 else [row(3)]}
        result = await collect(fetch, 2)
        self.assertEqual([c.id for c in result], [1, 3])
        self.assertEqual(calls, [1, 2])

    async def test_repeated_page_rejected(self):
        async def fetch(page, size):
            return {'count': 2, 'courses': [row(1)]}
        with self.assertRaises(CollectionError):
            await collect(fetch, 1)

    async def test_empty_account(self):
        async def fetch(page, size):
            return {'count': 0, 'courses': []}
        self.assertEqual(await collect(fetch), [])

    async def test_partial_result_rejected(self):
        async def fetch(page, size):
            return {'count': 2, 'courses': [row(1)] if page == 1 else []}
        with self.assertRaises(CollectionError):
            await collect(fetch, 1)

    def test_auth_error_not_empty(self):
        with self.assertRaises(CollectionError):
            parse_page({'status': -102})

    def test_missing_end_state_rejected(self):
        item = row(1)
        del item['is_end']
        with self.assertRaises(CollectionError):
            parse_page({'count': 1, 'courses': [item]})

    def test_external_link_rejected(self):
        item = row(1)
        item['first_category_url'] = 'https://example.com/classrooms/other'
        with self.assertRaises(CollectionError):
            parse_page({'count': 1, 'courses': [item]})
