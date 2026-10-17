"""ROM-free, metadata-only cross-stream interval diagnosis and honesty tests."""
import copy
import json
import unittest

from tools.mame_multistream_interval_evidence import multistream_interval_evidence


def synthetic_metadata():
    labels = [900, 902, 904, 906, 908, 910]
    base = {
        'first_frame': 900,
        'sample_count': 6,
        'frame_step': 2,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
        'obj_buffer_evidence': {
            'diagnostic_only': True,
            'nominal_frame_labels': labels,
            'changed_obj_slots_per_interval': [1, 0, 2, 0, 4],
            'changed_register_words_per_interval': [2, 2, 0, 1, 1],
            'obj_changed_intervals': 3,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        },
        'obj_latch_count_evidence': {
            'diagnostic_only': True,
            'sidecar_format_version': 2,
            'obj_byte_fingerprint_binding': 'FNV1A64_ALL_SAMPLES_MATCHED',
            'obj_byte_fingerprint_verified_count': 6,
            'nominal_frame_labels': labels,
            'inter_sample_callback_deltas': [1, 0, 2, 1, 0],
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        },
    }
    rgb = {
        'diagnostic_only': True,
        'nominal_frame_labels': labels,
        'reference_width': 384,
        'reference_height': 224,
        'changed_pixel_counts_per_interval': [10, 0, 15, 3, 0],
        'changed_reference_intervals': 3,
        'exact_unique_rgb_colors_per_frame': [4, 4, 6, 6, 7, 7],
        'nonblack_pixel_counts_per_frame': [250] * 6,
        'all_black_reference_sequence': False,
        'static_reference_sequence': False,
        'all_frames_single_color': False,
        'active_gameplay_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
    return base, rgb


class MultistreamIntervalEvidenceTests(unittest.TestCase):
    def test_nominal_multistream_cochanges_never_prove_synchronization(self):
        base, rgb = synthetic_metadata()
        out = multistream_interval_evidence(base, rgb, 900, 2, 6)
        self.assertEqual(out['status'], 'MULTISTREAM_VARIATION_OBSERVED_UNVERIFIED')
        self.assertEqual(out['nominal_frame_labels'], rgb['nominal_frame_labels'])
        self.assertEqual(out['rgb_change_intervals'], 3)
        self.assertEqual(out['obj_change_intervals'], 3)
        self.assertEqual(out['latch_increment_intervals'], 3)
        self.assertEqual(out['rgb_obj_cochange_intervals'], 2)
        self.assertEqual(out['rgb_obj_latch_cochange_intervals'], 2)
        self.assertEqual(out['obj_change_without_latch_increment_intervals'], 1)
        self.assertEqual(out['latch_increment_without_obj_change_intervals'], 1)
        self.assertEqual(out['intervals'][0]['to_nominal_frame'], 902)
        self.assertEqual(out['intervals'][4]['to_nominal_frame'], 910)
        self.assertFalse(out['hardware_vblank_observed'])
        self.assertFalse(out['active_gameplay_verified'])
        self.assertFalse(out['obj_latch_age_verified'])
        self.assertFalse(out['pixel_parity_eligible'])

    def test_obj_change_without_callback_increase_is_annotated_not_rejected(self):
        base, rgb = synthetic_metadata()
        out = multistream_interval_evidence(base, rgb, 900, 2, 6)
        self.assertEqual(out['intervals'][4]['observed_latch_callback_delta'], 0)
        self.assertTrue(out['intervals'][4]['obj_changed_without_latch_increment'])
        self.assertIn('OBJ_CHANGED_WITHOUT_COUNT_INCREMENT', out['observational_cautions'])

    def test_latch_increase_without_obj_change_is_separate(self):
        base, rgb = synthetic_metadata()
        out = multistream_interval_evidence(base, rgb, 900, 2, 6)
        self.assertEqual(out['intervals'][3]['changed_obj_slots'], 0)
        self.assertTrue(out['intervals'][3]['latch_increment_without_obj_change'])
        self.assertFalse(out['intervals'][3]['rgb_and_obj_changed'])

    def test_black_static_sequence_remains_low_information(self):
        base, rgb = synthetic_metadata()
        base['obj_buffer_evidence']['changed_obj_slots_per_interval'] = [0] * 5
        base['obj_buffer_evidence']['obj_changed_intervals'] = 0
        rgb['changed_pixel_counts_per_interval'] = [0] * 5
        rgb['changed_reference_intervals'] = 0
        rgb['all_black_reference_sequence'] = True
        rgb['static_reference_sequence'] = True
        rgb['all_frames_single_color'] = True
        rgb['exact_unique_rgb_colors_per_frame'] = [1] * 6
        rgb['nonblack_pixel_counts_per_frame'] = [0] * 6
        out = multistream_interval_evidence(base, rgb, 900, 2, 6)
        self.assertEqual(out['status'], 'LOW_INFORMATION_FOR_MULTISTREAM_STUDY')
        self.assertIn('ALL_BLACK_REFERENCE', out['observational_cautions'])
        self.assertIn('NO_OBJ_CHANGES_OBSERVED', out['observational_cautions'])
        self.assertIn('SINGLE_COLOR_FRAMES', out['observational_cautions'])
        self.assertFalse(out['frame_sync_verified'])

    def test_all_callback_deltas_zero_cannot_claim_vblank(self):
        base, rgb = synthetic_metadata()
        base['obj_latch_count_evidence']['inter_sample_callback_deltas'] = [0] * 5
        out = multistream_interval_evidence(base, rgb, 900, 2, 6)
        self.assertEqual(out['status'], 'LOW_INFORMATION_FOR_MULTISTREAM_STUDY')
        self.assertIn('NO_LATCH_COUNT_INCREMENTS', out['observational_cautions'])
        self.assertEqual(out['latch_increment_intervals'], 0)

    def test_single_color_changing_rgb_is_not_gameplay(self):
        base, rgb = synthetic_metadata()
        rgb['all_frames_single_color'] = True
        rgb['exact_unique_rgb_colors_per_frame'] = [1] * 6
        out = multistream_interval_evidence(base, rgb, 900, 2, 6)
        self.assertIn('SINGLE_COLOR_FRAMES', out['observational_cautions'])
        self.assertFalse(out['active_gameplay_verified'])

    def test_rejects_nonmatching_labels_in_each_independent_stream(self):
        for key in ('obj_buffer_evidence', 'obj_latch_count_evidence', None):
            base, rgb = synthetic_metadata()
            other = rgb if key is None else base[key]
            other['nominal_frame_labels'] = [900, 902, 904, 907, 908, 910]
            with self.subTest(stream=key):
                with self.assertRaisesRegex(ValueError, 'frame labels'):
                    multistream_interval_evidence(base, rgb, 900, 2, 6)

    def test_rejects_nonfalse_parity_or_nondiagnostic_claims(self):
        for key in ('obj_buffer_evidence', 'obj_latch_count_evidence', None):
            base, rgb = synthetic_metadata()
            stream = rgb if key is None else base[key]
            stream['frame_sync_verified'] = True
            with self.subTest(stream=key):
                with self.assertRaisesRegex(ValueError, 'flags'):
                    multistream_interval_evidence(base, rgb, 900, 2, 6)
        base, rgb = synthetic_metadata()
        base['obj_buffer_evidence']['diagnostic_only'] = False
        with self.assertRaisesRegex(ValueError, 'diagnostic-only'):
            multistream_interval_evidence(base, rgb, 900, 2, 6)

    def test_rejects_v1_or_incomplete_fingerprint_binding(self):
        for field, bad in (
            ('sidecar_format_version', 1),
            ('obj_byte_fingerprint_verified_count', 5),
            ('obj_byte_fingerprint_binding', 'LEGACY_V1_NOT_BOUND'),
        ):
            base, rgb = synthetic_metadata()
            base['obj_latch_count_evidence'][field] = bad
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'V2'):
                    multistream_interval_evidence(base, rgb, 900, 2, 6)

    def test_rejects_bad_numeric_series_and_bool_integers(self):
        sources = [
            ('changed_pixel_counts_per_interval', None, [True] * 5),
            ('changed_pixel_counts_per_interval', None, [999999] * 5),
            ('changed_obj_slots_per_interval', 'obj_buffer_evidence', [-1] * 5),
            ('changed_obj_slots_per_interval', 'obj_buffer_evidence', [257] * 5),
            ('changed_register_words_per_interval', 'obj_buffer_evidence', [65] * 5),
            ('inter_sample_callback_deltas', 'obj_latch_count_evidence', [-1] * 5),
            ('exact_unique_rgb_colors_per_frame', None, [0] * 6),
        ]
        for field, stream, invalid in sources:
            base, rgb = synthetic_metadata()
            target = rgb if stream is None else base[stream]
            target[field] = invalid
            with self.subTest(field=field, stream=stream):
                with self.assertRaisesRegex(ValueError, 'Invalid'):
                    multistream_interval_evidence(base, rgb, 900, 2, 6)

    def test_rejects_forged_transition_totals(self):
        for key, field in ((None, 'changed_reference_intervals'),
                           ('obj_buffer_evidence', 'obj_changed_intervals')):
            base, rgb = synthetic_metadata()
            target = rgb if key is None else base[key]
            target[field] = 5
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'totals'):
                    multistream_interval_evidence(base, rgb, 900, 2, 6)

    def test_rejects_invalid_base_frame_bounds_and_dimensions(self):
        for field, value in (('first_frame', 901), ('sample_count', 5),
                             ('frame_step', True)):
            base, rgb = synthetic_metadata()
            base[field] = value
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    multistream_interval_evidence(base, rgb, 900, 2, 6)
        base, rgb = synthetic_metadata()
        rgb['reference_height'] = 225
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            multistream_interval_evidence(base, rgb, 900, 2, 6)
        for count in (True, 3, 25):
            base, rgb = synthetic_metadata()
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, 'frame selection'):
                    multistream_interval_evidence(base, rgb, 900, 2, count)

    def test_no_sensitive_source_data_or_hashes_returned(self):
        base, rgb = synthetic_metadata()
        base['obj_buffer_evidence']['obj_probe_sha256'] = ['deadbeef' * 8] * 6
        out = multistream_interval_evidence(base, rgb, 900, 2, 6)
        serialized = json.dumps(out)
        self.assertNotIn('deadbeef', serialized)
        self.assertNotIn('rompath', serialized)
        self.assertNotIn('reference_rgb24_bytes', serialized)
        self.assertTrue(out['diagnostic_only'])


if __name__ == '__main__':
    unittest.main()
