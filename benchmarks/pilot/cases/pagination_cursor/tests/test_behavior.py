import unittest

from client import fetch_all


class PaginationTests(unittest.TestCase):
    def test_empty_intermediate_page_does_not_end_iteration(self):
        pages = {
            None: {"items": [1], "next_cursor": "a"},
            "a": {"items": [], "next_cursor": "b"},
            "b": {"items": [2], "next_cursor": None},
        }
        seen = []

        def fetch(cursor):
            seen.append(cursor)
            return pages[cursor]

        self.assertEqual(fetch_all(fetch), [1, 2])
        self.assertEqual(seen, [None, "a", "b"])

    def test_empty_terminal_page(self):
        self.assertEqual(fetch_all(lambda _cursor: {"items": [], "next_cursor": None}), [])

    def test_single_page(self):
        self.assertEqual(fetch_all(lambda _cursor: {"items": [3, 4], "next_cursor": None}), [3, 4])
