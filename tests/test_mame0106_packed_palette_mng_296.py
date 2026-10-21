"""Stage296 ROM-free MAME 0.106 packed-index PNG/MNG regression fixtures.

The 2006 MAME PNG writer chooses bit depth 1 for a two-color machine.
These tests use ONLY invented pixels, palettes and artificial PNG data.
"""
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import wolfmame0106_replay_preflight as png
from tools import wolfmame0106_private_visual_continuity as visual
from tools import wolfmame0106_private_mng_audit as mng


def chunk(name, data=b""):
    return (struct.pack(">I", len(data)) + name + data +
            struct.pack(">I", zlib.crc32(name + data) & 0xffffffff))


def packed_png(rows, depth=1, palette=None, filters=None, padding_bit=0):
    """Create valid indexed PNG scanlines with selectable row filters."""
    if palette is None:
        palette = [(0, 0, 0), (255, 255, 255)]
    if filters is None:
        filters = [0] * len(rows)
    h, w = len(rows), len(rows[0])
    assert all(len(row) == w for row in rows)
    assert depth in (1, 2, 4, 8)
    stride = (w * depth + 7) // 8
    previous = bytes(stride)
    raw = bytearray()
    for values, mode in zip(rows, filters):
        unpacked = bytearray([0] * stride)
        for x, index in enumerate(values):
            assert index < (1 << depth)
            bit = x * depth
            unpacked[bit // 8] |= index << (8 - depth - (bit % 8))
        if padding_bit:
            spare_bits = stride * 8 - w * depth
            if spare_bits:
                unpacked[-1] |= padding_bit & ((1 << spare_bits) - 1)
        encoded = bytearray(unpacked)
        for x in range(stride):
            left = unpacked[x - 1] if x else 0
            above = previous[x]
            upper_left = previous[x - 1] if x else 0
            paeth = visual._paeth(left, above, upper_left)
            predict = [0, left, above, (left + above) // 2, paeth][mode]
            encoded[x] = (unpacked[x] - predict) & 255
        raw.extend(bytes((mode,)) + encoded)
        previous = bytes(unpacked)
    ihdr = struct.pack(">IIBBBBB", w, h, depth, 3, 0, 0, 0)
    colors = bytes(v for color in palette for v in color)
    return (png.PNG_SIG + chunk(b"IHDR", ihdr) + chunk(b"PLTE", colors) +
            chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND"))


def mng_from_frames(frames, width, height):
    mhdr = struct.pack(">7I", width, height, 60, 0, 0, 0, 0x41)
    return (mng.MNG_SIGNATURE + chunk(b"MHDR", mhdr) +
            b"".join(frame[len(png.PNG_SIG):] for frame in frames) +
            chunk(b"MEND"))


class PackedPaletteMameMNGTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="dino296-indexed-only-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_depth1_mame_like_two_colour_png_to_rgba(self):
        rgb = [(0, 3, 6), (12, 24, 36)]
        pixels = [[0, 1, 0, 1, 1, 0, 1, 0], [1, 1, 0, 0, 0, 1, 1, 1]]
        raw = packed_png(pixels, 1, rgb)
        meta = png.png_integrity(raw)
        self.assertEqual(meta["png_color_type"], 3)
        self.assertEqual(meta["png_bit_depth"], 1)
        self.assertEqual(meta["idat_decoded_bytes"], 4)
        w, h, rgba = visual.normalized_rgba(raw)
        self.assertEqual((w, h), (8, 2))
        expected = bytes(t for row in pixels for i in row
                         for t in (*rgb[i], 255))
        self.assertEqual(rgba, expected)

    def test_depth1_png_padding_bits_do_not_become_pixels(self):
        pixels = [[1, 0, 1, 1, 0], [0, 1, 0, 1, 1]]
        ordinary = packed_png(pixels, 1, padding_bit=0)
        dirty_pad = packed_png(pixels, 1, padding_bit=7)
        self.assertEqual(visual.normalized_rgba(ordinary),
                         visual.normalized_rgba(dirty_pad))
        self.assertEqual(png.png_integrity(dirty_pad)["idat_decoded_bytes"], 4)

    def test_depth2_with_all_five_png_filter_modes(self):
        colors = [(x * 30, x * 33, x * 37) for x in range(4)]
        pixels = [
            [0, 1, 2, 3, 3, 2, 1, 0, 3],
            [1, 2, 3, 0, 2, 1, 0, 3, 1],
            [3, 2, 1, 0, 0, 1, 2, 3, 2],
            [0, 0, 3, 3, 2, 2, 1, 1, 1],
            [2, 3, 1, 0, 3, 0, 1, 2, 0],
        ]
        raw = packed_png(pixels, 2, colors, filters=[0, 1, 2, 3, 4])
        meta = png.png_integrity(raw)
        self.assertEqual(meta["png_bit_depth"], 2)
        w, h, rgba = visual.normalized_rgba(raw)
        self.assertEqual((w, h, len(rgba)), (9, 5, 9 * 5 * 4))
        expected = bytes(t for row in pixels for i in row
                         for t in (*colors[i], 255))
        self.assertEqual(rgba, expected)

    def test_depth4_indexed_filters_and_non_byte_multiple_width(self):
        colors = [(i * 10, i * 10, i * 11) for i in range(16)]
        pixels = [[0, 1, 7, 15, 9], [5, 4, 3, 2, 1]]
        raw = packed_png(pixels, 4, colors, filters=[1, 4])
        self.assertEqual(png.png_integrity(raw)["png_bit_depth"], 4)
        self.assertEqual(
            visual.normalized_rgba(raw)[2],
            bytes(v for row in pixels for index in row
                  for v in (*colors[index], 255)))

    def test_depth8_indexed_behavior_remains_compatible(self):
        pixels = [[0, 1, 2], [2, 1, 0]]
        colors = [(5, 6, 7), (20, 21, 22), (80, 90, 100)]
        raw = packed_png(pixels, 8, colors, filters=[0, 1])
        self.assertEqual(png.png_integrity(raw)["png_bit_depth"], 8)
        self.assertEqual(
            visual.normalized_rgba(raw)[2],
            bytes(x for row in pixels for i in row for x in (*colors[i], 255)))

    def test_mng_two_colour_frames_audited_and_change_detected(self):
        palette = [(20, 40, 60), (200, 210, 220)]
        frames = [
            packed_png([[0, 0, 0, 0], [0, 0, 0, 0]], 1, palette),
            packed_png([[0, 1, 0, 1], [1, 0, 1, 0]], 1, palette),
            packed_png([[0, 1, 0, 1], [1, 0, 1, 0]], 1, palette),
        ]
        dest = self.root / "candidate.mng"
        dest.write_bytes(mng_from_frames(frames, 4, 2))
        report = mng.audit(dest, minimum_frames=3)
        self.assertEqual(report["candidate_frame_count"], 3)
        self.assertEqual(report["changed_candidate_pairs"], 1)
        self.assertEqual(report["identical_candidate_pairs"], 1)
        self.assertFalse(report["original_inp_playback_verified"])

    def test_mng_24_packed_frames_matches_stage295_requested_count(self):
        frames = []
        for i in range(24):
            row = [((x + i) % 2) for x in range(16)]
            frames.append(packed_png([row] * 8, 1))
        dest = self.root / "stage295.mng"
        dest.write_bytes(mng_from_frames(frames, 16, 8))
        report = mng.audit(dest, minimum_frames=24)
        self.assertEqual(report["candidate_frame_count"], 24)
        self.assertEqual(report["changed_candidate_pairs"], 23)

    def test_indexed_palette_must_fit_depth(self):
        raw = packed_png([[0, 1]], 1, palette=[(0, 0, 0),
                                                  (1, 1, 1), (2, 2, 2)])
        with self.assertRaisesRegex(ValueError, "palette exceeds"):
            png.png_integrity(raw)

    def test_unmapped_palette_index_rejected_during_pixel_decode(self):
        raw = packed_png([[0, 3]], 2, palette=[(0, 0, 0),
                                                  (20, 20, 20)])
        self.assertEqual(png.png_integrity(raw)["png_bit_depth"], 2)
        with self.assertRaisesRegex(ValueError, "palette entry out of range"):
            visual.normalized_rgba(raw)

    def test_nonindexed_low_bit_depth_still_refused(self):
        raw = packed_png([[0, 1]], 1)
        # Change color type from indexed to RGB and update IHDR CRC,
        # leaving bit depth 1, which is unsupported for RGB.
        pos = len(png.PNG_SIG)
        length = struct.unpack(">I", raw[pos:pos + 4])[0]
        header = bytearray(raw[pos + 8:pos + 8 + length])
        header[9] = 2
        edited = (raw[:pos] + chunk(b"IHDR", bytes(header)) +
                  raw[pos + 12 + length:])
        with self.assertRaisesRegex(ValueError, "unsupported PNG dimensions/mode"):
            png.png_integrity(edited)

    def test_corrupt_packed_scanline_length_rejected(self):
        raw = packed_png([[0, 1, 0, 1]], 1)
        raw = raw.replace(zlib.compress(b"\x00" + b"\x50"),
                          zlib.compress(b"\x00" + b"\x50\x00"))
        # If compression bytes accidentally do not match, fall back to
        # rewriting IDAT with a one-byte-too-long payload.
        if raw == packed_png([[0, 1, 0, 1]], 1):
            base = packed_png([[0, 1, 0, 1]], 1)
            offset = base.index(b"IDAT") - 4
            head = base[:offset]
            tail = base[base.index(b"IEND") - 4:]
            raw = head + chunk(b"IDAT", zlib.compress(b"\x00\x50\x00")) + tail
        with self.assertRaises(ValueError):
            png.png_integrity(raw)


if __name__ == "__main__":
    unittest.main()
