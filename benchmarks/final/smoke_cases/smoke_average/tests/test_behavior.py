import unittest

from average import mean


class MeanTests(unittest.TestCase):
    def test_fractional_mean(self):
        self.assertEqual(mean([1, 2]), 1.5)

    def test_empty_is_rejected(self):
        with self.assertRaises(ValueError):
            mean([])


if __name__ == "__main__":
    unittest.main()
