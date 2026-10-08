import unittest

from settings import Settings


class NestedOverrideTests(unittest.TestCase):
    def test_nested_override_restores_each_level(self):
        settings = Settings({"mode": "base"})
        with settings.override("mode", "outer"):
            self.assertEqual(settings.values["mode"], "outer")
            with settings.override("mode", "inner"):
                self.assertEqual(settings.values["mode"], "inner")
            self.assertEqual(settings.values["mode"], "outer")
        self.assertEqual(settings.values["mode"], "base")

    def test_exception_propagates_and_restores(self):
        settings = Settings({"mode": "base"})
        with self.assertRaisesRegex(RuntimeError, "boom"):
            with settings.override("mode", "temporary"):
                raise RuntimeError("boom")
        self.assertEqual(settings.values["mode"], "base")


if __name__ == "__main__":
    unittest.main()
