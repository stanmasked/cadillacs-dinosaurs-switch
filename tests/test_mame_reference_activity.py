"""ROM-free tests of bounded, local-only CPS-1 RGB activity metadata."""
from pathlib import Path
import json
import tempfile
import unittest

from tools.mame_reference_activity import (
    PIXELS, REFERENCE_BYTES, reference_activity_diagnostic,
)


class PrivateReferenceActivityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def make_frames(self, blobs):
        for i, data in enumerate(blobs):
            (self.root /
             f'frame-{900 + i * 2:08d}.reference-rgb24.bin').write_bytes(data)

    def inspect(self, count=6):
        return reference_activity_diagnostic(self.root, 900, count, 2)

    def test_six_all_black_frames_are_not_mistaken_for_gameplay(self):
        self.make_frames([bytes(REFERENCE_BYTES)] * 6)
        data = self.inspect()
        self.assertEqual(data['status'], 'ALL_BLACK_REFERENCE_SEQUENCE')
        self.assertEqual(data['changed_reference_intervals'], 0)
        self.assertEqual(data['changed_pixel_counts_per_interval'], [0] * 5)
        self.assertEqual(data['nonblack_pixel_counts_per_frame'], [0] * 6)
        self.assertEqual(data['exact_unique_rgb_colors_per_frame'], [1] * 6)
        self.assertTrue(data['all_black_reference_sequence'])
        self.assertTrue(data['static_reference_sequence'])
        self.assertFalse(data['active_gameplay_verified'])
        self.assertFalse(data['frame_sync_verified'])
        self.assertFalse(data['pixel_parity_eligible'])

    def test_identical_white_frames_are_static_not_black(self):
        white = bytes([255]) * REFERENCE_BYTES
        self.make_frames([white] * 6)
        data = self.inspect()
        self.assertEqual(data['status'], 'STATIC_REFERENCE_SEQUENCE')
        self.assertFalse(data['all_black_reference_sequence'])
        self.assertTrue(data['static_reference_sequence'])
        self.assertEqual(data['nonblack_pixel_counts_per_frame'], [PIXELS] * 6)
        self.assertTrue(data['all_frames_single_color'])

    def test_uniform_color_changes_do_not_imply_active_gameplay(self):
        self.make_frames([bytes([i + 1]) * REFERENCE_BYTES for i in range(6)])
        data = self.inspect()
        self.assertEqual(data['status'], 'REFERENCE_BYTES_CHANGED_UNVERIFIED')
        self.assertEqual(data['changed_pixel_counts_per_interval'], [PIXELS] * 5)
        self.assertEqual(data['changed_reference_intervals'], 5)
        self.assertTrue(data['all_frames_single_color'])
        self.assertFalse(data['active_gameplay_verified'])
        self.assertFalse(data['reference_capture_provenance_verified'])

    def test_one_pixel_change_is_counted_exactly_once(self):
        base = bytearray(REFERENCE_BYTES)
        altered = bytearray(base)
        altered[100 * 3:100 * 3 + 3] = b'\x01\x02\x03'
        self.make_frames([bytes(base), bytes(altered), bytes(altered),
                          bytes(base)])
        data = self.inspect(count=4)
        self.assertEqual(data['changed_pixel_counts_per_interval'], [1, 0, 1])
        self.assertEqual(data['changed_reference_intervals'], 2)
        self.assertEqual(data['exact_unique_rgb_colors_per_frame'], [1, 2, 2, 1])
        self.assertEqual(data['nonblack_pixel_counts_per_frame'], [0, 1, 1, 0])
        self.assertEqual(data['nominal_frame_labels'], [900, 902, 904, 906])

    def test_two_color_frame_is_not_labeled_single_color(self):
        blob = b'\x00\x00\x00' * (PIXELS // 2) + \
               b'\xff\xff\x00' * (PIXELS // 2)
        self.make_frames([blob] * 4)
        report = self.inspect(count=4)
        self.assertEqual(report['exact_unique_rgb_colors_per_frame'], [2] * 4)
        self.assertFalse(report['all_frames_single_color'])
        self.assertEqual(report['nonblack_pixel_counts_per_frame'],
                         [PIXELS // 2] * 4)

    def test_invalid_rgb_size_is_rejected_without_padding_or_truncation(self):
        for size in (0, 3, REFERENCE_BYTES - 1, REFERENCE_BYTES + 1):
            with self.subTest(size=size):
                self.make_frames([bytes(REFERENCE_BYTES)] * 6)
                (self.root / 'frame-00000902.reference-rgb24.bin').write_bytes(
                    bytes(size))
                with self.assertRaisesRegex(ValueError, 'incomplete or oversized'):
                    self.inspect()

    def test_missing_private_reference_fails_closed(self):
        self.make_frames([bytes(REFERENCE_BYTES)] * 6)
        (self.root / 'frame-00000906.reference-rgb24.bin').unlink()
        with self.assertRaises(OSError):
            self.inspect()

    def test_strict_nominal_frame_bounds_reject_bool_and_overflow(self):
        for a, b, c in (
            (True, 6, 2), (-1, 6, 2), (900, True, 2),
            (900, 3, 2), (900, 25, 2), (900, 6, True),
            (900, 6, 121), (99999999, 6, 2),
        ):
            with self.subTest(args=(a, b, c)):
                with self.assertRaisesRegex(ValueError, 'Invalid bounded'):
                    reference_activity_diagnostic(self.root, a, b, c)

    def test_private_rgb_bytes_never_appear_in_returned_metadata(self):
        marker = b'\x47\x19\xb3'
        self.make_frames([marker * PIXELS] * 6)
        result = self.inspect()
        output = json.dumps(result)
        self.assertNotIn(marker.hex(), output)
        self.assertNotIn('reference_rgb24_bytes', result)
        self.assertTrue(result['diagnostic_only'])
        self.assertFalse(result['pixel_parity_eligible'])


if __name__ == '__main__':
    unittest.main()
