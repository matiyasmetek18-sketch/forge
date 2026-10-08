import unittest

from counter import Counter


class CounterTests(unittest.TestCase):
    def test_reset_returns_prior_value(self):
        counter = Counter()
        counter.increment()
        counter.increment()
        self.assertEqual(counter.reset(), 2)
        self.assertEqual(counter.value, 0)


if __name__ == "__main__":
    unittest.main()
