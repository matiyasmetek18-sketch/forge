import unittest

from memo import get_or_compute


class MemoizedFailureTests(unittest.TestCase):
    def test_failure_does_not_poison_cache(self):
        cache = {}
        calls = []

        def compute():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("temporary")
            return 9

        with self.assertRaises(RuntimeError):
            get_or_compute(cache, "key", compute)
        self.assertNotIn("key", cache)
        self.assertEqual(get_or_compute(cache, "key", compute), 9)
        self.assertEqual(len(calls), 2)

    def test_none_is_a_cacheable_success(self):
        cache = {}
        calls = []
        self.assertIsNone(get_or_compute(cache, "key", lambda: calls.append(1)))
        self.assertIsNone(get_or_compute(cache, "key", lambda: calls.append(2)))
        self.assertEqual(calls, [1])


if __name__ == "__main__":
    unittest.main()
