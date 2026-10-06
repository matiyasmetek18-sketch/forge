import unittest
from datetime import datetime, timezone

from timestamps import normalize_timestamp


class TimestampTests(unittest.TestCase):
    def test_positive_offset(self):
        self.assertEqual(normalize_timestamp("2025-03-01T12:30:00+05:30"), datetime(2025, 3, 1, 7, tzinfo=timezone.utc))

    def test_negative_offset_crosses_day(self):
        self.assertEqual(normalize_timestamp("2025-03-01T23:30:00-02:00"), datetime(2025, 3, 2, 1, 30, tzinfo=timezone.utc))

    def test_naive_and_utc_values(self):
        expected = datetime(2025, 3, 1, 12, 30, tzinfo=timezone.utc)
        self.assertEqual(normalize_timestamp("2025-03-01T12:30:00"), expected)
        self.assertEqual(normalize_timestamp("2025-03-01T12:30:00+00:00"), expected)
