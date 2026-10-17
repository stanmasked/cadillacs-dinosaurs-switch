"""ROM-free regression checks of leave-one-transition-out offset stability."""
import unittest

from tools.mame_obj_transition_stability import transition_leave_one_out
from test_mame_obj_transition_evidence import frames_from_masks, distinct_frames


class TransitionStabilityTests(unittest.TestCase):
    def test_identical_varying_sequence_remains_stable(self):
        data = distinct_frames()
        report = transition_leave_one_out(data, data, 2, 2)
        self.assertTrue(report['leave_one_out_applicable'])
        self.assertTrue(report['leave_one_out_stable'])
        self.assertEqual(report['leave_one_out_trial_count'], 5)
        self.assertEqual(report['leave_one_out_consistent_trials'], 5)
        self.assertEqual(report['leave_one_out_unstable_indices'], [])
        self.assertFalse(report['frame_sync_verified'])
        self.assertFalse(report['pixel_parity_eligible'])

    def test_one_sample_offset_four_matches_stable(self):
        data = distinct_frames()
        lua = [bytes([0x9b])*128] + data[:-1]
        report = transition_leave_one_out(data, lua, 2, 2)
        self.assertTrue(report['leave_one_out_stable'])
        self.assertEqual(report['leave_one_out_consistent_trials'], 5)

    def test_three_matches_one_bad_transition_is_fragile(self):
        src = frames_from_masks([1, 2, 4, 8, 16])
        dst = frames_from_masks([1 << 25, 1, 2, 4, 1 << 26])
        report = transition_leave_one_out(src, dst, 2, 2)
        self.assertTrue(report['leave_one_out_applicable'])
        self.assertFalse(report['leave_one_out_stable'])
        self.assertGreater(len(report['leave_one_out_unstable_indices']), 0)
        self.assertLess(report['leave_one_out_consistent_trials'], 5)
        self.assertEqual(report['leave_one_out_reason'],
                         'SENSITIVE_TO_OMITTED_TRANSITIONS')

    def test_all_static_frames_do_not_launch_jackknife_trials(self):
        frames = [bytes(128)] * 6
        report = transition_leave_one_out(frames, frames, 2, 2)
        self.assertFalse(report['leave_one_out_applicable'])
        self.assertEqual(report['leave_one_out_trial_count'], 0)
        self.assertEqual(report['leave_one_out_reason'], 'BASE_HYPOTHESIS_INCONCLUSIVE')

    def test_periodic_changes_do_not_launch_jackknife_trials(self):
        frames = frames_from_masks([1, 2, 1, 2, 1])
        report = transition_leave_one_out(frames, frames, 2, 2)
        self.assertFalse(report['leave_one_out_applicable'])
        self.assertFalse(report['leave_one_out_stable'])

    def test_short_edge_overlap_remains_rejected(self):
        frames = distinct_frames()
        lua = [bytes([100])*128, bytes([101])*128] + frames[:4]
        report = transition_leave_one_out(frames, lua, 2, 2)
        self.assertFalse(report['leave_one_out_applicable'])
        self.assertEqual(report['leave_one_out_trial_count'], 0)

    def test_ten_frame_two_step_offset_robust(self):
        src = frames_from_masks([1 << i for i in range(9)])
        lua = [bytes([101])*128, bytes([102])*128] + src[:-2]
        report = transition_leave_one_out(src, lua, 2, 2)
        self.assertTrue(report['leave_one_out_applicable'])
        self.assertTrue(report['leave_one_out_stable'])
        self.assertEqual(report['leave_one_out_trial_count'], 9)
        self.assertEqual(report['leave_one_out_consistent_trials'], 9)

    def test_input_rejection_inherited_from_primary(self):
        src = distinct_frames()
        with self.assertRaises(ValueError):
            transition_leave_one_out(src, [bytes(127)]*6, 2, 2)
        with self.assertRaises(ValueError):
            transition_leave_one_out(src, src, True, 2)
        with self.assertRaises(ValueError):
            transition_leave_one_out(src, src, 2, 4)


if __name__ == '__main__':
    unittest.main()
