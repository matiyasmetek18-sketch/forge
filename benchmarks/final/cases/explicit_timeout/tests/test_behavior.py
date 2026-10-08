import unittest

from timeouts import resolve_timeout


class ExplicitTimeoutTests(unittest.TestCase):
    def test_none_uses_default_but_zero_is_preserved(self):
        self.assertEqual(resolve_timeout(None, 12), 12)
        self.assertEqual(resolve_timeout(0, 12), 0)

    def test_positive_values_are_preserved(self):
        self.assertEqual(resolve_timeout(2.5), 2.5)

    def test_invalid_values_are_rejected(self):
        for value in (-1, True, "5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_timeout(value)


if __name__ == "__main__":
    unittest.main()
