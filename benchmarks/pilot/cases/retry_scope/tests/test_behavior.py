import unittest

from retries import TransientError, retry_transient


class RetryTests(unittest.TestCase):
    def test_permanent_failure_is_not_retried(self):
        calls = []

        def operation():
            calls.append(1)
            raise ValueError("permanent")

        with self.assertRaisesRegex(ValueError, "permanent"):
            retry_transient(operation)
        self.assertEqual(len(calls), 1)

    def test_transient_failure_can_recover(self):
        calls = []

        def operation():
            calls.append(1)
            if len(calls) < 3:
                raise TransientError("try again")
            return "ok"

        self.assertEqual(retry_transient(operation), "ok")
        self.assertEqual(len(calls), 3)

    def test_exhaustion_preserves_transient_exception(self):
        calls = []

        def operation():
            calls.append(1)
            raise TransientError("still down")

        with self.assertRaisesRegex(TransientError, "still down"):
            retry_transient(operation, attempts=2)
        self.assertEqual(len(calls), 2)

    def test_success_is_not_retried(self):
        self.assertEqual(retry_transient(lambda: 42), 42)
