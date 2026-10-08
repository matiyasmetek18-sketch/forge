import unittest

from jobs import validate_job


class TypedPayloadTests(unittest.TestCase):
    def test_defaults_and_explicit_values(self):
        self.assertEqual(validate_job({"name": "sync"}), {"name": "sync", "retries": 3, "enabled": True})
        self.assertEqual(validate_job({"name": "sync", "retries": 0, "enabled": False}), {"name": "sync", "retries": 0, "enabled": False})

    def test_bool_is_not_an_integer_retry_count(self):
        with self.assertRaises(ValueError):
            validate_job({"name": "sync", "retries": True})

    def test_unknown_and_wrong_typed_fields_are_rejected(self):
        for payload in ({"name": "sync", "extra": 1}, {"name": 9}, {"name": "sync", "enabled": 1}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_job(payload)


if __name__ == "__main__":
    unittest.main()
