import unittest

from resources import run_with_resource


class Resource:
    def __init__(self, close_error=None):
        self.closed = False
        self.close_error = close_error

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error


class CleanupPrecedenceTests(unittest.TestCase):
    def test_action_error_wins_over_close_error(self):
        resource = Resource(RuntimeError("close"))

        def fail(_resource):
            raise ValueError("action")

        with self.assertRaisesRegex(ValueError, "action"):
            run_with_resource(resource, fail)
        self.assertTrue(resource.closed)

    def test_close_error_is_reported_after_success(self):
        with self.assertRaisesRegex(RuntimeError, "close"):
            run_with_resource(Resource(RuntimeError("close")), lambda resource: 7)

    def test_successful_result_and_close(self):
        resource = Resource()
        self.assertEqual(run_with_resource(resource, lambda item: 7), 7)
        self.assertTrue(resource.closed)


if __name__ == "__main__":
    unittest.main()
