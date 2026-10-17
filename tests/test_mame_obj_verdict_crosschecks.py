"""ROM-free cross-report tamper checks for full CPS-1 frame diagnostics."""
import copy
import unittest

from tools.mame_obj_diagnostic_verdict import diagnostic_verdict
from tools.mame_obj_transition_evidence import transition_diagnostic
from tools.mame_obj_transition_stability import transition_leave_one_out
from test_mame_obj_transition_evidence import distinct_frames


def full_reports():
    frames = distinct_frames()
    exact = {
        'sample_count': len(frames), 'frame_step': 2,
        'frame_sync_verified': False, 'pixel_parity_eligible': False,
        'word_distance_diagnostic_only': True,
        'offset_hypothesis_informative': True, 'best_offset_steps': 0,
        'best_offset_nominal_frames': 0,
        'candidates': [
            {'offset_steps': 0, 'exact_equal_pairs': len(frames),
             'distinct_equal_register_states': len(frames)}],
    }
    return (exact, transition_diagnostic(frames, frames, 2, 2),
            transition_leave_one_out(frames, frames, 2, 2))


class VerdictCrossReportTests(unittest.TestCase):
    def test_full_real_transition_and_loo_objects_are_compatible(self):
        result = diagnostic_verdict(*full_reports())
        self.assertEqual(result['status'], 'CONSISTENT_BUT_UNVERIFIED')
        self.assertEqual(result['diagnostic_candidate_offset_steps'], 0)
        self.assertFalse(result['frame_sync_verified'])
        self.assertFalse(result['pixel_parity_eligible'])

    def test_mismatched_loo_count_for_same_series_rejected(self):
        parts = list(full_reports())
        parts[0]['sample_count'] = 8
        with self.assertRaisesRegex(ValueError, 'LOO trial count'):
            diagnostic_verdict(*parts)

    def test_exact_offset_nominal_clock_mismatch_rejected(self):
        parts = list(full_reports())
        parts[0]['best_offset_nominal_frames'] = 2
        with self.assertRaisesRegex(ValueError, 'Exact offset'):
            diagnostic_verdict(*parts)

    def test_transition_offset_nominal_clock_mismatch_rejected(self):
        parts = list(full_reports())
        parts[1]['transition_best_offset_nominal_frames'] = 2
        with self.assertRaisesRegex(ValueError, 'Transition offset'):
            diagnostic_verdict(*parts)

    def test_incomplete_series_metadata_rejected(self):
        for field, value in (('sample_count', True), ('sample_count', 25),
                             ('frame_step', 0), ('frame_step', 121)):
            parts = list(full_reports())
            parts[0][field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(ValueError, 'frame-series'):
                    diagnostic_verdict(*parts)
        parts = list(full_reports())
        del parts[0]['frame_step']
        with self.assertRaisesRegex(ValueError, 'frame-series'):
            diagnostic_verdict(*parts)

    def test_exact_candidate_cannot_claim_unsupported_diversity(self):
        parts = list(full_reports())
        parts[0]['candidates'][0]['distinct_equal_register_states'] = 1
        with self.assertRaisesRegex(ValueError, 'Exact candidate lacks'):
            diagnostic_verdict(*parts)

    def test_transition_candidate_cannot_ignore_insufficient_overlap(self):
        parts = list(full_reports())
        zero = next(r for r in parts[1]['transition_candidates']
                    if r['offset_steps'] == 0)
        zero['overlap_sufficient'] = False
        with self.assertRaisesRegex(ValueError, 'Transition candidate lacks'):
            diagnostic_verdict(*parts)

    def test_spoofed_loo_reason_rejected(self):
        parts = list(full_reports())
        parts[2]['leave_one_out_reason'] = 'SENSITIVE_TO_OMITTED_TRANSITIONS'
        with self.assertRaisesRegex(ValueError, 'LOO reason'):
            diagnostic_verdict(*parts)

    def test_missing_candidate_row_and_malformed_rows_rejected(self):
        parts = list(full_reports())
        parts[1]['transition_candidates'] = []
        with self.assertRaisesRegex(ValueError, 'candidate offset absent'):
            diagnostic_verdict(*parts)
        parts = list(full_reports())
        parts[0]['candidates'] = 'corrupt'
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            diagnostic_verdict(*parts)


if __name__ == '__main__':
    unittest.main()
