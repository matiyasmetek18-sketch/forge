import unittest

from tags import parse_tags


class TagTests(unittest.TestCase):
    def test_normalizes_valid_input(self):
        self.assertEqual(parse_tags(" Red, BLUE ,green"), ("red", "blue", "green"))

    def test_rejects_empty_fields(self):
        for raw in ("", "red,", ",red", "red,,blue", "  "):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_tags(raw)

    def test_rejects_duplicate_after_normalization(self):
        with self.assertRaises(ValueError):
            parse_tags("Red, blue, red")

    def test_rejects_non_text(self):
        with self.assertRaises(ValueError):
            parse_tags(["red"])
