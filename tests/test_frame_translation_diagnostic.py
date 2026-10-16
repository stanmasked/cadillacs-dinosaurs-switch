"""ROM-free XY registration diagnostics; never substitute for full-frame parity."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.cps1_tiles import _png_rgba
from tools.frame_compare import diagnose_translation, main


def pattern(width, height):
    return bytes(channel for y in range(height) for x in range(width)
                 for channel in ((31*x+13*y) % 256, (7*x+17*y) % 256,
                                 (11*x+23*y) % 256, 255))


def move(frame, width, height, dx, dy):
    result = bytearray(width * height * 4)
    for y in range(height):
        for x in range(width):
            xx, yy = x + dx, y + dy
            if 0 <= xx < width and 0 <= yy < height:
                out = (yy * width + xx) * 4
                src = (y * width + x) * 4
                result[out:out+4] = frame[src:src+4]
    return bytes(result)


class FrameTranslationDiagnostics(unittest.TestCase):
    def test_detect_known_signed_xy_shift_without_wraparound(self):
        width, height = 11, 9
        reference = pattern(width, height)
        candidate = move(reference, width, height, 2, -1)
        report = diagnose_translation(reference, candidate, width, height, 3)
        match = report['best_translation']
        self.assertEqual((match['dx'], match['dy']), (2, -1))
        self.assertEqual(match['different_pixels'], 0)
        self.assertEqual(match['overlap_pixels'], (width-2)*(height-1))
        self.assertLess(match['overlap_fraction'], 1)
        self.assertTrue(report['diagnostic_only'])

    def test_identical_frames_prefer_zero_offset_and_full_coverage(self):
        width, height = 13, 9
        reference = pattern(width, height)
        match = diagnose_translation(reference, reference, width, height)['best_translation']
        self.assertEqual((match['dx'], match['dy']), (0, 0))
        self.assertEqual(match['overlap_fraction'], 1)
        self.assertEqual(match['different_pixels'], 0)

    def test_flat_image_ties_choose_zero_shift(self):
        width, height = 8, 5
        flat = bytes((7, 8, 9, 255)) * (width * height)
        match = diagnose_translation(flat, flat, width, height, 3)['best_translation']
        self.assertEqual((match['dx'], match['dy']), (0, 0))

    def test_optional_alpha_exclusion_respected(self):
        width, height = 10, 7
        reference = pattern(width, height)
        candidate = bytearray(reference)
        for i in range(3, len(candidate), 4):
            candidate[i] = 3
        rgb = diagnose_translation(reference, candidate, width, height,
                                   ignore_alpha=True)
        rgba = diagnose_translation(reference, candidate, width, height)
        self.assertEqual(rgb['compared_channels'], 'RGB')
        self.assertEqual(rgb['best_translation']['different_pixels'], 0)
        self.assertEqual(rgba['best_translation']['different_pixels'], width*height)

    def test_single_pixel_frame_has_only_zero_translation(self):
        frame = bytes((1, 2, 3, 4))
        match = diagnose_translation(frame, frame, 1, 1)['best_translation']
        self.assertEqual((match['dx'], match['dy']), (0, 0))

    def test_invalid_dimensions_limits_and_lengths_are_rejected(self):
        for width, height, shift, data in (
                (0, 1, 1, b''), (1, -1, 1, b''),
                (1, 1, 0, b'1234'), (1, 1, 5, b'1234'),
                (True, 1, 1, b'1234'), (1, 1, True, b'1234'),
                (1, 1, 1, b'123')):
            with self.subTest(width=width, height=height, shift=shift):
                with self.assertRaises(ValueError):
                    diagnose_translation(data, data, width, height, shift)
        with self.assertRaisesRegex(ValueError, '512x256'):
            diagnose_translation(b'', b'', 513, 256)

    def test_cli_remains_strict_even_when_diagnostic_finds_exact_overlap(self):
        width, height = 11, 9
        reference = pattern(width, height)
        shifted = move(reference, width, height, 2, -1)
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory)/'ref.png', Path(directory)/'test.png'
            a.write_bytes(_png_rgba(width, height, reference, 'synthetic'))
            b.write_bytes(_png_rgba(width, height, shifted, 'synthetic'))
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = main([str(a), str(b), '--diagnose-shift', '3'])
            report = json.loads(stdout.getvalue())
            self.assertEqual(status, 1)
            self.assertGreater(report['different_pixels'], 0)
            self.assertFalse(report['identical'])
            best = report['translation_diagnostic']['best_translation']
            self.assertEqual((best['dx'], best['dy']), (2, -1))
            self.assertEqual(best['different_pixels'], 0)
            self.assertLess(best['overlap_fraction'], 1)


if __name__ == '__main__':
    unittest.main()
