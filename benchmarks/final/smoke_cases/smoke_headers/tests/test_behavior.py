import unittest

from headers import get_header


class HeaderTests(unittest.TestCase):
    def test_lookup_is_case_insensitive(self):
        self.assertEqual(get_header({"Content-Type": "text/plain"}, "content-type"), "text/plain")

    def test_missing_header_raises(self):
        with self.assertRaises(KeyError):
            get_header({}, "missing")


if __name__ == "__main__":
    unittest.main()
