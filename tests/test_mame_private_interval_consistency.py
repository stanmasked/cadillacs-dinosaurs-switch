"""ROM-free consistency checks for nominal private MAME capture metadata."""
import copy
import json
import unittest

from test_mame_multistream_interval_evidence import synthetic_metadata
from tools.mame_multistream_interval_evidence import multistream_interval_evidence
from tools.mame_private_interval_consistency import private_nominal_interval_consistency


def fixture():
    frame_report, rgb = synthetic_metadata()
    latch = frame_report['obj_latch_count_evidence']
    latch.update({
        'observed_latch_callback_counts': [10, 11, 11, 13, 14, 14],
        'zero_callback_delta_frames': [904, 910],
        'multiple_callback_delta_frames': [906],
        'obj_changed_without_observed_latch_frames': [910],
        'capture_session_tagged_samples': 6,
        'capture_session_label_consistent': True,
    })
    combined = multistream_interval_evidence(frame_report, rgb, 900, 2, 6)
    return frame_report, combined


class PrivateNominalIntervalConsistencyTests(unittest.TestCase):
    def test_consistent_six_sample_report_never_certifies_vblank(self):
        base, combined = fixture()
        out = private_nominal_interval_consistency(base, combined)
        self.assertEqual(out['status'], 'PRIVATE_NOMINAL_COUNTER_CONSISTENCY_ONLY')
        self.assertEqual(out['nominal_frame_samples_checked'], 6)
        self.assertEqual(out['nominal_intervals_checked'], 5)
        self.assertEqual(out['zero_callback_intervals'], 2)
        self.assertEqual(out['multiple_callback_intervals'], 1)
        self.assertEqual(out['obj_change_without_callback_intervals'], 1)
        self.assertTrue(out['cumulative_latch_deltas_match'])
        self.assertFalse(out['hardware_vblank_observed'])
        self.assertFalse(out['frame_sync_verified'])
        self.assertFalse(out['pixel_parity_eligible'])

    def test_changed_cumulative_count_fails_closed(self):
        base, combined = fixture()
        base['obj_latch_count_evidence']['observed_latch_callback_counts'][2] += 1
        with self.assertRaisesRegex(ValueError, 'cumulative counts'):
            private_nominal_interval_consistency(base, combined)

    def test_counter_overflow_boolean_and_nonmonotone_fail_closed(self):
        for values in ([True, 11, 11, 13, 14, 14],
                       [10, 11, -1, 13, 14, 14],
                       [10, 11, 11, (1 << 64), 14, 14],
                       [10, 11, 9, 13, 14, 14]):
            base, combined = fixture()
            base['obj_latch_count_evidence']['observed_latch_callback_counts'] = values
            with self.subTest(values=values):
                with self.assertRaisesRegex(ValueError, 'numeric series|cumulative'):
                    private_nominal_interval_consistency(base, combined)

    def test_missing_mixed_or_untagged_session_is_rejected(self):
        for field, value in (('sidecar_format_version', 1),
                             ('capture_session_tagged_samples', 5),
                             ('capture_session_label_consistent', False),
                             ('obj_byte_fingerprint_verified_count', True)):
            base, combined = fixture()
            base['obj_latch_count_evidence'][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'V2 session'):
                    private_nominal_interval_consistency(base, combined)

    def test_counter_annotations_must_match_all_intervals(self):
        for field in ('zero_callback_delta_frames',
                      'multiple_callback_delta_frames',
                      'obj_changed_without_observed_latch_frames'):
            base, combined = fixture()
            base['obj_latch_count_evidence'][field] = []
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'annotated'):
                    private_nominal_interval_consistency(base, combined)

    def test_interval_fields_are_checked_individually(self):
        fields = ('from_nominal_frame', 'to_nominal_frame',
                  'changed_obj_slots', 'changed_register_words',
                  'observed_latch_callback_delta', 'rgb_changed',
                  'obj_changed', 'latch_count_increased',
                  'rgb_and_obj_changed',
                  'obj_changed_without_latch_increment',
                  'latch_increment_without_obj_change')
        for field in fields:
            base, combined = fixture()
            original = combined['intervals'][0][field]
            combined['intervals'][0][field] = (not original
                                               if type(original) is bool
                                               else original + 1)
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'observations disagree'):
                    private_nominal_interval_consistency(base, combined)

    def test_source_series_bounds_and_frame_labels_fail_closed(self):
        for source, field, bad in (
            ('obj_buffer_evidence', 'changed_obj_slots_per_interval', [257]*5),
            ('obj_buffer_evidence', 'changed_register_words_per_interval', [True]*5),
            ('obj_latch_count_evidence', 'inter_sample_callback_deltas', [0]*4),
            ('obj_latch_count_evidence', 'nominal_frame_labels', [900, 902, 904, 906, 908, 911]),
        ):
            base, combined = fixture()
            base[source][field] = bad
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    private_nominal_interval_consistency(base, combined)

    def test_totals_and_parity_claims_are_fail_closed(self):
        for field in ('rgb_change_intervals', 'obj_change_intervals',
                      'latch_increment_intervals', 'rgb_obj_cochange_intervals',
                      'rgb_obj_latch_cochange_intervals',
                      'obj_change_without_latch_increment_intervals',
                      'latch_increment_without_obj_change_intervals'):
            base, combined = fixture()
            combined[field] += 1
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'totals'):
                    private_nominal_interval_consistency(base, combined)
        base, combined = fixture()
        combined['frame_sync_verified'] = True
        with self.assertRaisesRegex(ValueError, 'parity claims'):
            private_nominal_interval_consistency(base, combined)

    def test_no_sensitive_values_in_output(self):
        base, combined = fixture()
        base['obj_buffer_evidence']['private_rom_dump'] = 'private ROM BYTES'
        combined['private_capture_session'] = '0' * 32
        result = private_nominal_interval_consistency(base, combined)
        encoded = json.dumps(result)
        self.assertNotIn('private ROM BYTES', encoded)
        self.assertNotIn('0' * 32, encoded)
        self.assertNotIn('file_path', encoded)

    def test_rejects_bad_capture_range_and_incomplete_entries(self):
        for kwargs in ({'first_frame': True}, {'frame_step': 0},
                       {'frame_count': 3}, {'frame_count': 25}):
            base, combined = fixture()
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ValueError, 'bounds'):
                    private_nominal_interval_consistency(base, combined, **kwargs)
        base, combined = fixture()
        combined['intervals'][0] = {}
        with self.assertRaises(ValueError):
            private_nominal_interval_consistency(base, combined)


if __name__ == '__main__':
    unittest.main()
