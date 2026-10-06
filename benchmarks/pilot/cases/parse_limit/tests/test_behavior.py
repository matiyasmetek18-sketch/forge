import unittest

from settings import parse_limit


class LimitTests(unittest.TestCase):
    def test_valid_values_and_default(self):
        self.assertEqual(parse_limit(None), 20)
        self.assertEqual(parse_limit(None, default=7), 7)
        self.assertEqual(parse_limit("001"), 1)
        self.assertEqual(parse_limit("100"), 100)

    def test_reject_malformed_values(self):
        for raw in (" 5", "+5", "5 ", "5.0", "\u0665", 5, True):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_limit(raw)

    def test_reject_out_of_range(self):
        for raw in ("0", "101"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_limit(raw)
