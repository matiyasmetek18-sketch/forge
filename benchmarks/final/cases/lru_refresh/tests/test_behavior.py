import unittest

from cache import LRUCache


class LRURefreshTests(unittest.TestCase):
    def test_get_refreshes_recency(self):
        cache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        self.assertEqual(cache.get("a"), 1)
        cache.put("c", 3)
        self.assertNotIn("b", cache.data)
        self.assertIn("a", cache.data)

    def test_update_refreshes_without_evicting(self):
        cache = LRUCache(2)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("a", 9)
        cache.put("c", 3)
        self.assertEqual(dict(cache.data), {"a": 9, "c": 3})

    def test_missing_key_still_raises(self):
        with self.assertRaises(KeyError):
            LRUCache(1).get("missing")


if __name__ == "__main__":
    unittest.main()
