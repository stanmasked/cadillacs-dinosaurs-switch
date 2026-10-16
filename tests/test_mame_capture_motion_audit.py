"""ROM-free CPS-1 same-render-callback motion diagnostic tests."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.mame_capture_motion_audit import (
    STREAMS, RGB_LENGTH, _rgb_difference, audit_sequence, main,
)


def fixture(root, frame, *, pixel=0, obj=0, palette=0):
    stem = f'frame-{frame:08d}'
    meta = {'game': 'dino', 'frame': frame,
            'capture_hook': 'screen_update_cps1_complete',
            'full_cliprect': True, 'buffered_obj_same_render_pass': True,
            'reference_pixel_encoding': 'rgb24_palette_resolved',
            'raw_word_endianness': 'big',
            'palette_source': 'MAME_effective_pen_color',
            'reference_rgb_bytes': 258048, 'buffered_obj_bytes': 2048,
            'gfxram_bytes': 196608, 'palette_bytes': 9216,
            'cps_a_bytes': 64, 'cps_b_bytes': 64,
            'reference_width': 384, 'reference_height': 224,
            'pixel_parity_verified': False}
    (root / (stem + '.manifest.json')).write_text(json.dumps(meta))
    for suffix, length in STREAMS.items():
        buf = bytearray(length)
        if suffix == 'reference-rgb24.bin':
            buf[:3] = bytes((pixel, 2, 3))
        if suffix == 'buffered-obj-be.bin':
            buf[0] = obj
        if suffix == 'palette-rgb24.bin':
            buf[0] = palette
        (root / (stem + '.' + suffix)).write_bytes(buf)


class CaptureMotionAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        fixture(self.root, 900, pixel=0, obj=0, palette=0)
        fixture(self.root, 901, pixel=0, obj=1, palette=0)
        fixture(self.root, 902, pixel=17, obj=1, palette=2)
        fixture(self.root, 904, pixel=30, obj=2, palette=3)

    def test_all_streams_identical_rgb_but_obj_changes(self):
        audit = audit_sequence(self.root, 900, 2)
        self.assertEqual(audit['unique_stream_hash_counts']['reference-rgb24.bin'], 1)
        self.assertEqual(audit['unique_stream_hash_counts']['buffered-obj-be.bin'], 2)
        self.assertEqual(audit['unchanged_reference_transitions'], 1)
        self.assertTrue(audit['reference_all_frames_identical'])
        self.assertIn('buffered-obj-be.bin',
                      audit['frames'][1]['streams_changed_since_previous'])
        self.assertNotIn('reference-rgb24.bin',
                         audit['frames'][1]['streams_changed_since_previous'])
        self.assertEqual(audit['longest_unchanged_reference_transition_run'], 1)

    def test_one_pixel_color_error_location(self):
        audit = audit_sequence(self.root, 900, 3)
        self.assertEqual(audit['unchanged_reference_transitions'], 1)
        difference = audit['frames'][2]['rgb_since_previous']
        self.assertEqual(difference['different_pixels'], 1)
        self.assertEqual(difference['first_changed_pixel_xy'], [0, 0])
        self.assertEqual(difference['changed_bbox_xyxy_inclusive'], [0, 0, 0, 0])
        self.assertEqual(difference['changed_channel_counts_rgb'], [1, 0, 0])
        self.assertEqual(difference['total_absolute_channel_error_rgb'], [17, 0, 0])
        self.assertFalse(audit['first_level_verified'])
        self.assertFalse(audit['mame_pixel_parity_verified'])
        self.assertFalse(audit['input_replay_synchronized'])

    def test_single_frame_is_not_falsely_warned_frozen(self):
        audit = audit_sequence(self.root, 900, 1)
        self.assertEqual(audit['frames'][0]['mame_frame'], 900)
        self.assertNotIn('rgb_since_previous', audit['frames'][0])
        self.assertEqual(audit['warnings'], [])

    def test_stride_selects_actual_numbers_without_interpolation(self):
        audit = audit_sequence(self.root, 900, 3, stride=2)
        self.assertEqual([p['mame_frame'] for p in audit['frames']], [900, 902, 904])
        self.assertEqual(audit['stride'], 2)
        self.assertEqual(audit['unique_stream_hash_counts']['reference-rgb24.bin'], 3)

    def test_missing_frame_is_refused(self):
        with self.assertRaises(FileNotFoundError):
            audit_sequence(self.root, 901, 3)

    def test_truncated_rgb_or_obj_is_refused(self):
        p = self.root / 'frame-00000901.reference-rgb24.bin'
        p.write_bytes(bytes(RGB_LENGTH - 1))
        with self.assertRaisesRegex(ValueError, 'reference-rgb24.bin'):
            audit_sequence(self.root, 900, 2)
        fixture(self.root, 901)
        p = self.root / 'frame-00000901.buffered-obj-be.bin'
        p.write_bytes(bytes(2047))
        with self.assertRaisesRegex(ValueError, 'buffered-obj-be.bin'):
            audit_sequence(self.root, 900, 2)

    def test_bad_manifest_rejected(self):
        p = self.root / 'frame-00000900.manifest.json'
        j = json.loads(p.read_text())
        j['buffered_obj_same_render_pass'] = False
        p.write_text(json.dumps(j))
        with self.assertRaisesRegex(ValueError, 'buffered_obj_same_render_pass'):
            audit_sequence(self.root, 900, 1)

    def test_range_validation_rejects_booleans_and_overflow(self):
        for args in ((True,1,1),(-1,1,1),(900,0,1),
                     (900,121,1),(900,1,0),(99999999,2,2),
                     (900,1,True)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                audit_sequence(self.root,*args)

    def test_error_rectangle_across_screen(self):
        a = bytearray(RGB_LENGTH)
        b = bytearray(a)
        for x, y, channel, val in ((2, 7, 1, 19),(380, 220, 2, 88)):
            b[3*(y*384+x)+channel] = val
        measured = _rgb_difference(a,b)
        self.assertEqual(measured['different_pixels'],2)
        self.assertEqual(measured['changed_bbox_xyxy_inclusive'],[2,7,380,220])
        self.assertEqual(measured['first_changed_pixel_xy'],[2,7])
        self.assertEqual(measured['changed_channel_counts_rgb'],[0,1,1])
        self.assertEqual(measured['total_absolute_channel_error_rgb'],[0,19,88])

    def test_cli_persists_hashes_and_refuses_to_overwrite(self):
        dest = self.root/'private-report.json'
        args = [str(self.root),'--first','900','--count','3','--report',str(dest)]
        self.assertEqual(main(args),0)
        content = dest.read_text()
        self.assertEqual(json.loads(content)['frame_count'],3)
        self.assertNotIn('palette_rgb',content)
        self.assertEqual(main(args),2)
        self.assertEqual(dest.read_text(),content)


if __name__ == '__main__':
    unittest.main()
