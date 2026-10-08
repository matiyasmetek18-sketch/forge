import unittest

from quota import apportion


class QuotaApportionTests(unittest.TestCase):
    def test_sum_and_largest_remainder(self):
        self.assertEqual(apportion([5, 3, 2], 7), [4, 2, 1])
        self.assertEqual(sum(apportion([2, 7, 11], 13)), 13)

    def test_equal_remainders_use_input_order(self):
        self.assertEqual(apportion([1, 1, 1], 2), [1, 1, 0])

    def test_zero_total_and_invalid_weights(self):
        self.assertEqual(apportion([2, 1], 0), [0, 0])
        for weights in ([], [0, 0], [1, -1]):
            with self.subTest(weights=weights), self.assertRaises(ValueError):
                apportion(weights, 3)


if __name__ == "__main__":
    unittest.main()
