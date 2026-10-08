import unittest

from decoder import decode_chunks


class StreamDecodeTests(unittest.TestCase):
    def test_multibyte_characters_may_cross_chunks(self):
        data = "A€🙂Z".encode("utf-8")
        chunks = [data[:2], data[2:4], data[4:6], data[6:]]
        self.assertEqual(decode_chunks(chunks), "A€🙂Z")

    def test_ascii_and_empty_chunks_are_preserved(self):
        self.assertEqual(decode_chunks([b"ab", b"", b"cd"]), "abcd")

    def test_malformed_and_incomplete_sequences_raise(self):
        for chunks in ([b"\xff"], [b"\xe2", b"\x82"]):
            with self.subTest(chunks=chunks), self.assertRaises(UnicodeDecodeError):
                decode_chunks(chunks)


if __name__ == "__main__":
    unittest.main()
