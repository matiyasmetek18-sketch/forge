import unittest

from config import load_port


class ConfigTests(unittest.TestCase):
    def test_present_valid_primary_is_used(self):
        seen = []

        def read(name):
            seen.append(name)
            return {"primary": "8080", "fallback": "9000"}[name]

        self.assertEqual(load_port(read), 8080)
        self.assertEqual(seen, ["primary"])

    def test_missing_primary_uses_fallback(self):
        def read(name):
            if name == "primary":
                raise FileNotFoundError(name)
            return "9000"

        self.assertEqual(load_port(read), 9000)

    def test_malformed_primary_does_not_fall_back(self):
        seen = []

        def read(name):
            seen.append(name)
            return "invalid" if name == "primary" else "9000"

        with self.assertRaises(ValueError):
            load_port(read)
        self.assertEqual(seen, ["primary"])

    def test_out_of_range_primary_does_not_fall_back(self):
        seen = []

        def read(name):
            seen.append(name)
            return "70000" if name == "primary" else "9000"

        with self.assertRaises(ValueError):
            load_port(read)
        self.assertEqual(seen, ["primary"])
