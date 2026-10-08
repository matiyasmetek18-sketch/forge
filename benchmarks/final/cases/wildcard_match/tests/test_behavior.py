import unittest

from wildcard import matches


class WildcardMatchTests(unittest.TestCase):
    def test_multiple_stars_and_backtracking(self):
        self.assertTrue(matches("abefcdgiescdfimde", "ab*cd?i*de"))
        self.assertTrue(matches("mississippi", "m*iss*?pi"))

    def test_stars_may_match_empty(self):
        self.assertTrue(matches("abc", "a**bc"))
        self.assertTrue(matches("", "***"))

    def test_full_string_mismatch(self):
        self.assertFalse(matches("abc", "a*d"))
        self.assertFalse(matches("ab", "?*?*?"))


if __name__ == "__main__":
    unittest.main()
