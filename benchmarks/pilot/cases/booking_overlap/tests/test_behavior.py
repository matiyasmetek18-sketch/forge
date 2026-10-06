import unittest

from bookings import Calendar


class BookingTests(unittest.TestCase):
    def test_enclosing_interval_conflicts(self):
        calendar = Calendar()
        self.assertTrue(calendar.book(10, 20))
        self.assertFalse(calendar.book(5, 25))
        self.assertEqual(calendar.bookings, [(10, 20)])

    def test_contained_and_partial_overlap_conflict(self):
        calendar = Calendar()
        calendar.book(10, 20)
        for interval in ((12, 18), (5, 12), (18, 25)):
            with self.subTest(interval=interval):
                self.assertFalse(calendar.book(*interval))

    def test_touching_boundaries_and_separate_intervals_work(self):
        calendar = Calendar()
        self.assertTrue(calendar.book(10, 20))
        self.assertTrue(calendar.book(20, 30))
        self.assertTrue(calendar.book(0, 10))

    def test_empty_interval_rejected(self):
        with self.assertRaises(ValueError):
            Calendar().book(4, 4)
