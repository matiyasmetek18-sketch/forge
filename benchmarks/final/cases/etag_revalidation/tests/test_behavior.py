import unittest

from client import load_json


class EtagRevalidationTests(unittest.TestCase):
    def test_304_reuses_cache_and_sends_etag(self):
        seen = []

        def fetch(etag):
            seen.append(etag)
            return {"status": 304, "body": b""}

        cached = ({"value": 4}, "tag-1")
        self.assertEqual(load_json(fetch, cached), cached)
        self.assertEqual(seen, ["tag-1"])

    def test_200_refreshes_data_and_etag(self):
        result = load_json(lambda etag: {"status": 200, "body": '{"value": 5}', "etag": "tag-2"}, ({"value": 4}, "tag-1"))
        self.assertEqual(result, ({"value": 5}, "tag-2"))

    def test_invalid_status_and_cacheless_304_fail(self):
        with self.assertRaises(RuntimeError):
            load_json(lambda etag: {"status": 304, "body": b""})
        with self.assertRaises(RuntimeError):
            load_json(lambda etag: {"status": 503, "body": b"down"})


if __name__ == "__main__":
    unittest.main()
