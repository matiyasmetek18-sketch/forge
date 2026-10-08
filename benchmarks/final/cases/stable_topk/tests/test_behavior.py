import unittest

from ranking import top_k


class StableTopKTests(unittest.TestCase):
    def test_ties_preserve_input_order(self):
        records = [
            {"name": "alpha", "score": 9},
            {"name": "beta", "score": 10},
            {"name": "zulu", "score": 10},
            {"name": "gamma", "score": 8},
        ]
        self.assertEqual([item["name"] for item in top_k(records, 3)], ["beta", "zulu", "alpha"])

    def test_input_is_not_mutated(self):
        records = [{"name": "b", "score": 1}, {"name": "a", "score": 2}]
        before = [dict(item) for item in records]
        top_k(records, 1)
        self.assertEqual(records, before)

    def test_invalid_k_is_rejected(self):
        for k in (-1, 2):
            with self.subTest(k=k), self.assertRaises(ValueError):
                top_k([{"name": "a", "score": 1}], k)


if __name__ == "__main__":
    unittest.main()
