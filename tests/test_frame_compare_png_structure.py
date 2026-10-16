"""ROM-free malformed PNG order tests for CPS-1 frame parity evidence.

Existing filter and pixel metric tests live in test_frame_compare.py.
These fixtures deliberately keep each CRC correct so structure (rather
than accidental corruption) must be detected by the independent reader.
"""
import struct
import unittest
import zlib

from tools.frame_compare import load_rgba_png


SIGNATURE = b'\x89PNG\r\n\x1a\n'
RGBA = bytes((19, 32, 74, 255, 160, 13, 44, 17,
              91, 214, 2, 240, 35, 83, 191, 0))


def chunk(kind, payload=b''):
    return (struct.pack('>I', len(payload)) + kind + payload +
            struct.pack('>I', zlib.crc32(kind + payload) & 0xffffffff))


def parts():
    raw = b'\x00' + RGBA[:8] + b'\x00' + RGBA[8:]
    compressed = zlib.compress(raw)
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', 2, 2, 8, 6, 0, 0, 0))
    return ihdr, compressed, chunk(b'IEND')


def make_png(*png_chunks):
    return SIGNATURE + b''.join(png_chunks)


class PngChunkStructure(unittest.TestCase):
    def test_unmodified_png_and_adjacent_idat_chunks_are_accepted(self):
        ihdr, compressed, iend = parts()
        for png in (
            make_png(ihdr, chunk(b'IDAT', compressed), iend),
            make_png(ihdr, chunk(b'IDAT', compressed[:3]),
                     chunk(b'IDAT', compressed[3:]), iend),
        ):
            with self.subTest(length=len(png)):
                self.assertEqual(load_rgba_png(png), (2, 2, RGBA))

    def test_valid_ancillary_and_optional_plte_preserve_pixels(self):
        ihdr, compressed, iend = parts()
        png = make_png(
            ihdr, chunk(b'PLTE', bytes((1, 2, 3))),
            chunk(b'tEXt', b'purpose\x00synthetic'),
            chunk(b'IDAT', compressed),
            chunk(b'tEXt', b'post\x00image'),
            iend)
        self.assertEqual(load_rgba_png(png), (2, 2, RGBA))

    def test_trailing_bytes_even_one_byte_are_rejected(self):
        ihdr, compressed, iend = parts()
        valid = make_png(ihdr, chunk(b'IDAT', compressed), iend)
        for trailer in (b'x', b'garbage', chunk(b'tEXt', b'extra\x00junk')):
            with self.subTest(trailer=trailer):
                with self.assertRaisesRegex(ValueError, 'Trailing data'):
                    load_rgba_png(valid + trailer)

    def test_ihdr_must_be_first(self):
        ihdr, compressed, iend = parts()
        with self.assertRaisesRegex(ValueError, 'IHDR must be first'):
            load_rgba_png(make_png(chunk(b'tEXt', b'key\x00value'),
                                   ihdr, chunk(b'IDAT', compressed), iend))

    def test_noncontiguous_idat_must_not_be_joined(self):
        ihdr, compressed, iend = parts()
        png = make_png(ihdr, chunk(b'IDAT', compressed[:3]),
                       chunk(b'tEXt', b'gap\x00yes'),
                       chunk(b'IDAT', compressed[3:]), iend)
        with self.assertRaisesRegex(ValueError, 'Noncontiguous PNG IDAT'):
            load_rgba_png(png)

    def test_unknown_critical_chunk_rejected(self):
        ihdr, compressed, iend = parts()
        with self.assertRaisesRegex(ValueError, 'Unsupported critical'):
            load_rgba_png(make_png(ihdr, chunk(b'ABCD', b'opaque'),
                                   chunk(b'IDAT', compressed), iend))

    def test_malformed_chunk_types_rejected_with_valid_crc(self):
        ihdr, compressed, iend = parts()
        for kind in (b'1DAT', b'abct', b'IDaT'):
            with self.subTest(chunk_type=kind):
                with self.assertRaisesRegex(ValueError, 'Invalid PNG chunk type'):
                    load_rgba_png(make_png(ihdr, chunk(kind, b'opaque'),
                                           chunk(b'IDAT', compressed), iend))

    def test_plte_after_idat_or_duplicate_is_rejected(self):
        ihdr, compressed, iend = parts()
        a = chunk(b'PLTE', bytes((1, 2, 3)))
        for bad in (
            make_png(ihdr, chunk(b'IDAT', compressed), a, iend),
            make_png(ihdr, a, a, chunk(b'IDAT', compressed), iend),
            make_png(ihdr, chunk(b'PLTE', bytes((1, 2))), chunk(b'IDAT', compressed), iend),
        ):
            with self.subTest(length=len(bad)):
                with self.assertRaisesRegex(ValueError, 'Invalid or misplaced PLTE'):
                    load_rgba_png(bad)

    def test_iend_must_be_empty_and_complete(self):
        ihdr, compressed, iend = parts()
        with self.assertRaisesRegex(ValueError, 'Nonempty PNG IEND'):
            load_rgba_png(make_png(ihdr, chunk(b'IDAT', compressed),
                                   chunk(b'IEND', b'extra')))
        with self.assertRaisesRegex(ValueError, 'Incomplete PNG'):
            load_rgba_png(make_png(ihdr, chunk(b'IDAT', compressed)))


if __name__ == '__main__':
    unittest.main()
