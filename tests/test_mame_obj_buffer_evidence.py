"""ROM-free buffered CPS-1 OBJ temporal evidence regressions.

Synthetic sidecars only: no MAME binary, commercial sprite data or ROM.
"""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.mame_obj_buffer_evidence import obj_buffer_diagnostic
from tools.mame_obj_sequence_alignment import read_frames
from test_mame_obj_cli_end_to_end import make_capture, invoke, states


def sprite_buffer(slot=None):
    obj = bytearray(2048)
    if slot is not None:
        # 4th big-endian word's high byte is the end marker.
        obj[slot * 8 + 6] = 0xff
    return bytes(obj)


class BufferedObjTemporalEvidenceTests(unittest.TestCase):
    def test_static_empty_obj_reports_missing_markers_not_sprites(self):
        regs = states(6)
        result = obj_buffer_diagnostic(regs, [sprite_buffer()] * 6, 900, 2)
        self.assertEqual(result['distinct_obj_buffer_states'], 1)
        self.assertEqual(result['obj_changed_intervals'], 0)
        self.assertEqual(result['obj_unchanged_intervals'], 5)
        self.assertEqual(result['changed_obj_slots_per_interval'], [0] * 5)
        self.assertEqual(result['first_end_marker_slots'], [None] * 6)
        self.assertEqual(result['nominal_frames_without_end_marker'],
                         [900, 902, 904, 906, 908, 910])
        self.assertEqual(result['obj_static_while_registers_change_intervals'],
                         [902, 904, 906, 908, 910])

    def test_markers_use_fourth_word_high_byte_and_first_slot(self):
        frames = [sprite_buffer(3)] * 6
        result = obj_buffer_diagnostic(states(6), frames, 900, 2)
        self.assertEqual(result['first_end_marker_slots'], [3] * 6)
        self.assertEqual(result['nominal_frames_without_end_marker'], [])

    def test_marker_in_final_256th_slot_is_recognized(self):
        frames = [sprite_buffer(255)] * 4
        report = obj_buffer_diagnostic(states(4), frames, 0, 1)
        self.assertEqual(report['first_end_marker_slots'], [255] * 4)

    def test_obj_change_counts_8_byte_slots_not_changed_bytes(self):
        frames = [sprite_buffer(), sprite_buffer(3), sprite_buffer(3),
                  sprite_buffer(12), sprite_buffer(12), sprite_buffer()]
        result = obj_buffer_diagnostic(states(6), frames, 900, 2)
        self.assertEqual(result['changed_obj_slots_per_interval'],
                         [1, 0, 2, 0, 1])
        self.assertEqual(result['obj_changed_intervals'], 3)
        self.assertEqual(result['obj_unchanged_intervals'], 2)
        self.assertEqual(result['distinct_obj_buffer_states'], 3)

    def test_register_and_obj_change_cooccurrence_is_not_sync_proof(self):
        result = obj_buffer_diagnostic(states(6),
              [sprite_buffer(), sprite_buffer(1), sprite_buffer(1),
               sprite_buffer(2), sprite_buffer(2), sprite_buffer(2)], 900, 2)
        self.assertEqual(result['obj_and_register_change_cooccurrence_intervals'], 2)
        self.assertEqual(result['obj_static_while_registers_change_intervals'],
                         [904, 908, 910])
        self.assertFalse(result['obj_latch_age_verified'])
        self.assertFalse(result['frame_sync_verified'])
        self.assertFalse(result['pixel_parity_eligible'])

    def test_obj_changed_without_register_change_is_separate(self):
        frames = [bytes(128)] * 4
        obs = [sprite_buffer(), sprite_buffer(1), sprite_buffer(2),
               sprite_buffer(3)]
        result = obj_buffer_diagnostic(frames, obs, 900, 2)
        self.assertEqual(result['changed_register_words_per_interval'], [0, 0, 0])
        self.assertEqual(result['obj_changed_intervals'], 3)
        self.assertEqual(result['obj_and_register_change_cooccurrence_intervals'], 0)

    def test_sha256_digests_match_exact_raw_probe_bytes(self):
        obs = [sprite_buffer(None), sprite_buffer(0),
               sprite_buffer(1), sprite_buffer(255)]
        report = obj_buffer_diagnostic(states(4), obs, 900, 2)
        self.assertEqual(report['obj_probe_sha256'],
                         [hashlib.sha256(f).hexdigest() for f in obs])
        self.assertTrue(report['diagnostic_only'])
        self.assertNotIn('buffered_obj_words', report)
        self.assertNotIn('obj_raw', report)

    def test_uses_requested_nominal_frame_step_without_inferred_timing(self):
        result = obj_buffer_diagnostic(states(4),
                                       [sprite_buffer()] * 4, 400, 3)
        self.assertEqual(result['nominal_frame_labels'], [400, 403, 406, 409])

    def test_invalid_frame_series_boundaries_fail(self):
        valid = (states(4), [sprite_buffer()] * 4, 900, 2)
        inputs = [
            (valid[0][:3], valid[1][:3], 900, 2),
            (valid[0], valid[1][:3], 900, 2),
            (valid[0], valid[1], -1, 2),
            (valid[0], valid[1], True, 2),
            (valid[0], valid[1], 900, True),
            (valid[0], valid[1], 900, 0),
            (valid[0], valid[1], 99999999, 2),
        ]
        for candidate in inputs:
            with self.subTest(candidate=(len(candidate[0]), candidate[2],candidate[3])):
                with self.assertRaises(ValueError):
                    obj_buffer_diagnostic(*candidate)

    def test_bad_register_or_obj_payloads_fail_closed(self):
        regs = states(4)
        objs = [sprite_buffer()] * 4
        bad_inputs = [
            (regs[:-1] + [bytes(127)], objs),
            (regs[:-1] + [bytearray(128)], objs),
            (regs, objs[:-1] + [bytes(2047)]),
            (regs, objs[:-1] + [bytearray(2048)]),
        ]
        for a, b in bad_inputs:
            with self.subTest(last_type=type(a[-1]).__name__+type(b[-1]).__name__):
                with self.assertRaises(ValueError):
                    obj_buffer_diagnostic(a, b, 900, 2)

    def test_loader_opt_in_preserves_previous_two_value_interface(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            regs, lua = read_frames(root, 900, 6, 2)
            r, l, obj = read_frames(root, 900, 6, 2, include_obj=True)
            self.assertEqual((r, l), (regs, lua))
            self.assertEqual(len(obj), 6)
            self.assertTrue(all(len(b) == 2048 for b in obj))
            with self.assertRaisesRegex(ValueError, 'include_obj'):
                read_frames(root, 900, 6, 2, include_obj='yes')

    def test_cli_embeds_metadata_for_static_obj_not_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            status, report = invoke(root)
            self.assertEqual(status, 0)
            metadata = report['obj_buffer_evidence']
            self.assertEqual(metadata['distinct_obj_buffer_states'], 1)
            self.assertEqual(metadata['obj_unchanged_intervals'], 5)
            self.assertFalse(metadata['obj_latch_age_verified'])
            self.assertFalse(metadata['pixel_parity_eligible'])
            self.assertNotIn('buffered_obj_words', (root / 'audit.json').read_text())

    def test_cli_detects_one_temporal_obj_marker_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            obj_file = root / 'frame-00000904.buffered-obj-be.bin'
            obj_file.write_bytes(sprite_buffer(3))
            status, report = invoke(root)
            self.assertEqual(status, 0)
            metadata = report['obj_buffer_evidence']
            self.assertEqual(metadata['first_end_marker_slots'],
                             [None, None, 3, None, None, None])
            self.assertEqual(metadata['changed_obj_slots_per_interval'],
                             [0, 1, 1, 0, 0])
            self.assertEqual(metadata['obj_changed_intervals'], 2)
            self.assertEqual(metadata['distinct_obj_buffer_states'], 2)
            self.assertEqual(metadata['obj_probe_sha256'][2],
                             hashlib.sha256(sprite_buffer(3)).hexdigest())
            self.assertFalse(metadata['frame_sync_verified'])
            # Fake OBJ mutations do not upgrade correlated register conclusions.
            self.assertEqual(report['diagnostic_verdict']['status'],
                             'CONSISTENT_BUT_UNVERIFIED')


if __name__ == '__main__':
    unittest.main()
