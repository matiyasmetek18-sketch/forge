import unittest

from ledger import Ledger


class BatchAtomicityTests(unittest.TestCase):
    def test_successful_batch_commits_all_changes(self):
        ledger = Ledger({"a": 10, "b": 5})
        self.assertEqual(ledger.apply_batch([("a", -3), ("b", 4)]), {"a": 7, "b": 9})

    def test_late_overdraft_rolls_back_earlier_changes(self):
        ledger = Ledger({"a": 10, "b": 5})
        with self.assertRaises(ValueError):
            ledger.apply_batch([("a", 7), ("b", -6)])
        self.assertEqual(ledger.balances, {"a": 10, "b": 5})

    def test_unknown_account_rolls_back(self):
        ledger = Ledger({"a": 10})
        with self.assertRaises(KeyError):
            ledger.apply_batch([("a", -2), ("missing", 1)])
        self.assertEqual(ledger.balances, {"a": 10})


if __name__ == "__main__":
    unittest.main()
