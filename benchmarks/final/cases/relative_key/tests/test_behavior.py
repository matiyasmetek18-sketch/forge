import unittest

from keys import normalize_key


class RelativeKeyTests(unittest.TestCase):
    def test_valid_nested_key_is_preserved(self):
        self.assertEqual(normalize_key("team/A-1/report.json"), "team/A-1/report.json")

    def test_navigation_and_empty_segments_are_rejected(self):
        for value in ("a/../secret", "a/./b", "a//b", "../x", "/root", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_key(value)

    def test_backslashes_are_not_path_separators(self):
        with self.assertRaises(ValueError):
            normalize_key("team\\secret")


if __name__ == "__main__":
    unittest.main()
