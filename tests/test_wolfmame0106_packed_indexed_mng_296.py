"""Stage296: synthetic PNG packed-indexed bytes, not captured game images."""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import wolfmame0106_replay_preflight as png
from tools import wolfmame0106_private_visual_continuity as pixels
from tools import wolfmame0106_private_mng_audit as mng


def chunk(kind, payload=b""):
    return (struct.pack(">I", len(payload)) + kind + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff))


def _packed_row(indices, depth):
    out = bytearray((len(indices) * depth + 7) // 8)
    for i, index in enumerate(indices):
        if not 0 <= index < (1 << depth):
            raise ValueError("invalid index for synthetic palette")
        bit = i * depth
        out[bit // 8] |= index << (8 - depth - bit % 8)
    return bytes(out)


def indexed_png(indices, depth, *, filter_method=0, palette_count=None,
                rows=None, color_type=3):
    w = len(indices)
    row_pixels = [_packed_row(indices, depth)] if rows is None else [
        _packed_row(r, depth) for r in rows]
    h = len(row_pixels)
    if palette_count is None:
        palette_count = 1 << depth
    palette = b"".join(bytes([i, i + 1, i + 2])
                       for i in range(palette_count))
    raw = bytearray()
    prev = bytes(len(row_pixels[0]))
    for row in row_pixels:
        if filter_method == 0:
            encoded = row
        elif filter_method == 1:
            encoded = bytes((row[i] - (row[i-1] if i else 0)) & 255
                            for i in range(len(row)))
        elif filter_method == 2:
            encoded = bytes((row[i] - prev[i]) & 255 for i in range(len(row)))
        else:
            raise ValueError("test supports filters 0/1/2")
        raw.extend(bytes([filter_method]) + encoded)
        prev = row
    return (png.PNG_SIG
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, depth,
                                         color_type, 0, 0, 0))
            + chunk(b"PLTE", palette)
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND"))


def expected_rgba(indices, *, palette_shift=0):
    out = bytearray()
    for index in indices:
        out.extend([index + palette_shift,
                    index + 1 + palette_shift,
                    index + 2 + palette_shift, 255])
    return bytes(out)


class PackedIndexedPNGTests(unittest.TestCase):
    def test_1bit_odd_width_and_msbf_padding(self):
        indices = [1,0,1,0,1,0,1,0,1]
        data = indexed_png(indices, 1)
        detail = png.png_integrity(data)
        self.assertEqual(detail["png_bit_depth"], 1)
        self.assertEqual(detail["idat_decoded_bytes"], 3)
        w,h,rgba = pixels.normalized_rgba(data)
        self.assertEqual((w,h), (9,1))
        self.assertEqual(rgba, expected_rgba(indices))

    def test_2bit_odd_width(self):
        indices = [3,0,1,2,2]
        data = indexed_png(indices, 2)
        self.assertEqual(png.png_integrity(data)["png_bit_depth"], 2)
        self.assertEqual(pixels.normalized_rgba(data)[2], expected_rgba(indices))

    def test_4bit_odd_width(self):
        indices = [15,3,4]
        data = indexed_png(indices, 4)
        self.assertEqual(png.png_integrity(data)["png_bit_depth"], 4)
        self.assertEqual(pixels.normalized_rgba(data)[2], expected_rgba(indices))

    def test_filter_sub_is_applied_to_packed_bytes_before_unpacking(self):
        indices = [1,1,0,0,1,0,0,0,1,0,1,1,0]
        image = indexed_png(indices, 1, filter_method=1)
        self.assertEqual(pixels.normalized_rgba(image)[2], expected_rgba(indices))

    def test_filter_up_uses_prior_packed_row(self):
        first = [1,0,1,0,1,0,1,0,1]
        second = [0,1,0,1,0,1,0,1,0]
        image = indexed_png(first, 1, filter_method=2, rows=[first,second])
        self.assertEqual(pixels.normalized_rgba(image)[2],
                         expected_rgba(first)+expected_rgba(second))

    def test_full_8bit_palette_backward_compatibility(self):
        indices = [8,100,22]
        image = indexed_png(indices, 8, palette_count=128)
        self.assertEqual(png.png_integrity(image)["png_bit_depth"], 8)
        self.assertEqual(pixels.normalized_rgba(image)[2], expected_rgba(indices))

    def test_reject_palette_size_exceeding_bit_capacity(self):
        image = indexed_png([1,0,1], 1, palette_count=3)
        with self.assertRaisesRegex(ValueError, "palette"):
            png.png_integrity(image)

    def test_reject_invalid_low_depth_for_nonindexed_mode(self):
        image = indexed_png([1,0,1], 1, color_type=0)
        with self.assertRaisesRegex(ValueError, "unsupported PNG"):
            png.png_integrity(image)

    def test_private_mng_audit_two_packed_indexed_frames(self):
        with tempfile.TemporaryDirectory(prefix="dino296-packed-mng-") as temp:
            destination = Path(temp)/"synthetic-2frame.mng"
            first = indexed_png([0,1,0,1,0,1,0,1,0], 1)[8:]
            second = indexed_png([1,0,1,0,1,0,1,0,1], 1)[8:]
            mhdr = struct.pack(">7I", 9, 1, 60, 0, 0, 0, 0x41)
            destination.write_bytes(
                mng.MNG_SIGNATURE + chunk(b"MHDR", mhdr)
                + first + second + chunk(b"MEND"))
            report = mng.audit(destination, minimum_frames=2)
            self.assertEqual(report["candidate_frame_count"], 2)
            self.assertEqual(report["changed_candidate_pairs"], 1)
            self.assertFalse(report["original_inp_playback_verified"])


if __name__ == "__main__":
    unittest.main()
