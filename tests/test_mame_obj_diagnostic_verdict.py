"""Synthetic, ROM-free and fail-closed MAME diagnostic verdict regressions."""
import unittest

from tools.mame_obj_diagnostic_verdict import diagnostic_verdict


def reports(exact_offset=1, transition_offset=1, stable=True):
    exact = {
        'offset_hypothesis_informative': exact_offset is not None,
        'best_offset_steps': exact_offset,
        'word_distance_diagnostic_only': True,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
    transition = {
        'transition_hypothesis_informative': transition_offset is not None,
        'transition_best_offset_steps': transition_offset,
        'transition_diagnostic_only': True,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
    stability = {
        'leave_one_out_applicable': transition_offset is not None,
        'leave_one_out_stable': bool(stable and transition_offset is not None),
        'leave_one_out_trial_count': 5 if transition_offset is not None else 0,
        'leave_one_out_consistent_trials': (
            5 if stable and transition_offset is not None else
            3 if transition_offset is not None else 0),
        'leave_one_out_unstable_indices': (
            [] if stable and transition_offset is not None else
            [0, 2] if transition_offset is not None else []),
        'leave_one_out_diagnostic_only': True,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
    return exact, transition, stability


class DiagnosticVerdictTests(unittest.TestCase):
    def test_consistent_stable_offset_never_grants_pixel_parity(self):
        result = diagnostic_verdict(*reports())
        self.assertEqual(result['status'], 'CONSISTENT_BUT_UNVERIFIED')
        self.assertEqual(result['diagnostic_candidate_offset_steps'], 1)
        self.assertTrue(result['exact_transition_offsets_agree'])
        self.assertTrue(result['leave_one_out_stable'])
        self.assertEqual(result['independent_physical_measurement_count'], 0)
        self.assertFalse(result['frame_sync_verified'])
        self.assertFalse(result['pixel_parity_eligible'])

    def test_disagreement_is_not_presented_as_valid_offset(self):
        result = diagnostic_verdict(*reports(0, 1, True))
        self.assertEqual(result['status'], 'CONFLICTING_REGISTER_DIAGNOSTICS')
        self.assertIsNone(result['diagnostic_candidate_offset_steps'])
        self.assertFalse(result['exact_transition_offsets_agree'])
        self.assertFalse(result['frame_sync_verified'])

    def test_agreement_without_leave_one_out_stability_is_fragile(self):
        result = diagnostic_verdict(*reports(1, 1, False))
        self.assertEqual(result['status'], 'FRAGILE_REGISTER_DIAGNOSTIC')
        self.assertIsNone(result['diagnostic_candidate_offset_steps'])
        self.assertTrue(result['exact_transition_offsets_agree'])
        self.assertFalse(result['leave_one_out_stable'])

    def test_exact_registers_only_remain_uncorroborated(self):
        result = diagnostic_verdict(*reports(0, None, False))
        self.assertEqual(result['status'], 'EXACT_ONLY_UNCORROBORATED')
        self.assertIsNone(result['diagnostic_candidate_offset_steps'])
        self.assertIsNone(result['exact_transition_offsets_agree'])

    def test_transition_only_is_not_treated_as_exact_frame(self):
        result = diagnostic_verdict(*reports(None, 1, True))
        self.assertEqual(result['status'], 'TRANSITION_ONLY_UNCORROBORATED')
        self.assertIsNone(result['diagnostic_candidate_offset_steps'])
        self.assertTrue(result['leave_one_out_stable'])

    def test_no_evidence_is_inconclusive(self):
        result = diagnostic_verdict(*reports(None, None, False))
        self.assertEqual(result['status'], 'INSUFFICIENT_REGISTER_EVIDENCE')
        self.assertIsNone(result['diagnostic_candidate_offset_steps'])
        self.assertIsNone(result['exact_transition_offsets_agree'])

    def test_no_tentative_offset_upgrade_when_exact_is_noninformative(self):
        a, b, c = reports(None, None, False)
        a['best_offset_steps'] = 0
        result = diagnostic_verdict(a, b, c)
        self.assertEqual(result['status'], 'INSUFFICIENT_REGISTER_EVIDENCE')
        self.assertIsNone(result['diagnostic_candidate_offset_steps'])

    def test_reject_claims_of_synchronized_pixels_or_frames(self):
        for index, field, value in (
            (0, 'frame_sync_verified', True),
            (1, 'pixel_parity_eligible', True),
            (2, 'frame_sync_verified', None),
            (0, 'pixel_parity_eligible', 0)):
            parts = list(reports())
            parts[index][field] = value
            with self.subTest(index=index, field=field):
                with self.assertRaisesRegex(ValueError, 'claims'):
                    diagnostic_verdict(*parts)

    def test_reject_missing_or_nonboolean_required_flags(self):
        for index, key, value in (
            (0, 'offset_hypothesis_informative', 1),
            (1, 'transition_hypothesis_informative', 'yes'),
            (2, 'leave_one_out_stable', None),
            (0, 'word_distance_diagnostic_only', False),
            (1, 'transition_diagnostic_only', None),
            (2, 'leave_one_out_diagnostic_only', 1)):
            parts = list(reports())
            parts[index][key] = value
            with self.subTest(index=index, key=key):
                with self.assertRaises(ValueError):
                    diagnostic_verdict(*parts)

    def test_reject_inconsistent_transition_and_stability_metadata(self):
        a, b, c = reports()
        c['leave_one_out_applicable'] = False
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            diagnostic_verdict(a, b, c)
        a, b, c = reports(None, None, False)
        c['leave_one_out_stable'] = True
        with self.assertRaisesRegex(ValueError, 'conflicts'):
            diagnostic_verdict(a, b, c)

    def test_reject_spoofed_stable_trials(self):
        for key, value in (
            ('leave_one_out_trial_count', 0),
            ('leave_one_out_consistent_trials', 4),
            ('leave_one_out_unstable_indices', [2]),
            ('leave_one_out_trial_count', True),
            ('leave_one_out_trial_count', 24)):
            parts = list(reports())
            parts[2][key] = value
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'Stable label|Inconsistent'):
                    diagnostic_verdict(*parts)

    def test_reject_unstable_trial_accounting_without_promotion(self):
        for changed in (
            {'leave_one_out_trial_count': 2},
            {'leave_one_out_consistent_trials': 6},
            {'leave_one_out_unstable_indices': [0, 0]},
            {'leave_one_out_unstable_indices': [5, 6]},
            {'leave_one_out_unstable_indices': 'none'},
        ):
            parts = list(reports(1, 1, False))
            parts[2].update(changed)
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    diagnostic_verdict(*parts)

    def test_reject_bogus_offsets_and_non_objects(self):
        for index, field, value in (
            (0, 'best_offset_steps', True),
            (1, 'transition_best_offset_steps', '1'),
            (0, 'best_offset_steps', 5),
            (1, 'transition_best_offset_steps', -5)):
            parts = list(reports())
            parts[index][field] = value
            with self.subTest(index=index):
                with self.assertRaisesRegex(ValueError, 'Informative'):
                    diagnostic_verdict(*parts)
        with self.assertRaises(ValueError):
            diagnostic_verdict([], *reports()[1:])


if __name__ == '__main__':
    unittest.main()
