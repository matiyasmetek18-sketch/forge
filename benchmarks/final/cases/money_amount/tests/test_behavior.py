import unittest

from money import parse_amount


class MoneyAmountTests(unittest.TestCase):
    def test_valid_amounts_are_exact_cents(self):
        self.assertEqual(parse_amount("0.01"), 1)
        self.assertEqual(parse_amount("12.3"), 1230)
        self.assertEqual(parse_amount("10000.00"), 1_000_000)

    def test_noncanonical_syntax_is_rejected(self):
        for value in ("01.00", "+1", "1e2", "1.005", "1.", ".5", "NaN", " 1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_amount(value)

    def test_range_and_type_are_checked(self):
        for value in ("0", "0.00", "10000.01", 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_amount(value)


if __name__ == "__main__":
    unittest.main()
