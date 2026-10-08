import unittest

from streams import write_all


class PartialWriter:
    def __init__(self, limit):
        self.limit = limit
        self.data = bytearray()

    def write(self, data):
        count = min(self.limit, len(data))
        self.data.extend(data[:count])
        return count


class PartialWriterTests(unittest.TestCase):
    def test_all_bytes_are_written_in_order(self):
        writer = PartialWriter(3)
        self.assertEqual(write_all(writer, b"abcdefgh"), 8)
        self.assertEqual(bytes(writer.data), b"abcdefgh")

    def test_empty_input_needs_no_write(self):
        writer = PartialWriter(0)
        self.assertEqual(write_all(writer, b""), 0)

    def test_zero_progress_raises(self):
        with self.assertRaises(RuntimeError):
            write_all(PartialWriter(0), b"x")


if __name__ == "__main__":
    unittest.main()
