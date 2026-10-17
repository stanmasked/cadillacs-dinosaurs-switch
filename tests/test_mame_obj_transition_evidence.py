"""ROM-free tests for CPS-1 video register transition masks.

Changing-register masks are clues only; all results stay parity-ineligible.
"""
import struct
import unittest

from tools.mame_obj_transition_evidence import transition_diagnostic


def frames_from_masks(masks):
    words = [0] * 64
    frames = [struct.pack('>64H', *words)]
    for mask in masks:
        for word in range(64):
            if mask & (1 << word):
                words[word] += 1
        frames.append(struct.pack('>64H', *words))
    return frames


def distinct_frames():
    return frames_from_masks([1 << x for x in (0, 3, 7, 11, 17)])


class TransitionEvidenceTests(unittest.TestCase):
    def test_unique_one_step_register_change_shift_is_diagnostic(self):
        render = distinct_frames()
        lua = [bytes([0x9b])*128] + render[:-1]
        report = transition_diagnostic(render, lua, 2, 2)
        self.assertEqual(report['transition_best_offset_steps'], 1)
        self.assertEqual(report['transition_best_offset_nominal_frames'], 2)
        self.assertTrue(report['transition_hypothesis_informative'])
        self.assertEqual(report['transition_candidates'][3]['matching_active_transitions'], 4)
        self.assertFalse(report['frame_sync_verified'])
        self.assertFalse(report['pixel_parity_eligible'])

    def test_identical_variable_frame_streams_select_zero(self):
        frames = distinct_frames()
        report = transition_diagnostic(frames, frames, 2, 2)
        self.assertEqual(report['transition_best_offset_steps'], 0)
        self.assertEqual(report['transition_candidates'][2]['matching_active_transitions'], 5)
        self.assertEqual(report['transition_candidates'][2]['distinct_matching_change_masks'], 5)
        self.assertTrue(report['transition_diagnostic_only'])

    def test_static_sequence_is_ambiguous_no_supporting_transitions(self):
        frames = [bytes(128)] * 6
        result = transition_diagnostic(frames, frames, 2, 2)
        self.assertIsNone(result['transition_best_offset_steps'])
        self.assertFalse(result['transition_hypothesis_informative'])
        self.assertEqual(result['render_active_transitions'], 0)
        self.assertEqual(result['transition_ambiguous_best_offsets'], [-2,-1,0,1,2])
        self.assertEqual(result['transition_candidates'][2]
                         ['matching_inactive_transitions_non_evidence'], 5)

    def test_periodic_change_masks_report_ambiguous_offsets(self):
        frames = frames_from_masks([1, 2, 1, 2, 1])
        result = transition_diagnostic(frames, frames, 1, 2)
        self.assertIsNone(result['transition_best_offset_steps'])
        self.assertEqual(result['transition_ambiguous_best_offsets'], [-2, 0, 2])
        self.assertFalse(result['transition_hypothesis_informative'])

    def test_repeated_one_word_change_is_not_informative(self):
        frames = frames_from_masks([1, 1, 1, 1, 1])
        result = transition_diagnostic(frames, frames, 2, 2)
        self.assertIsNone(result['transition_best_offset_steps'])
        self.assertFalse(result['transition_hypothesis_informative'])

    def test_only_two_matching_active_patterns_insufficient(self):
        frames = frames_from_masks([0, 0, 1, 0, 2])
        result = transition_diagnostic(frames, frames, 2, 0)
        self.assertFalse(result['transition_hypothesis_informative'])
        self.assertIsNone(result['transition_best_offset_steps'])
        self.assertEqual(result['transition_candidates'][0]
                         ['matching_active_transitions'], 2)

    def test_different_word_values_with_identical_change_masks_are_weak_hints(self):
        render = distinct_frames()
        lua = [bytes([0x7f])*128] + render[:-1]
        # Alter the same register in every Lua sample: the change masks
        # remain the same even though the full register sets never agree.
        changed = []
        for frame in lua:
            buf = bytearray(frame)
            buf[126] ^= 0x40
            changed.append(bytes(buf))
        result = transition_diagnostic(render, changed, 2, 2)
        self.assertEqual(result['transition_best_offset_steps'], 1)
        self.assertTrue(result['transition_hypothesis_informative'])
        self.assertFalse(result['frame_sync_verified'])
        self.assertFalse(result['pixel_parity_eligible'])

    def test_unrelated_changes_do_not_select_offset(self):
        render = distinct_frames()
        lua = frames_from_masks([1 << i for i in (40, 41, 42, 43, 44)])
        report = transition_diagnostic(render, lua, 2, 2)
        self.assertIsNone(report['transition_best_offset_steps'])
        self.assertEqual(max(c['matching_active_transitions']
                             for c in report['transition_candidates']), 0)
        self.assertFalse(report['transition_hypothesis_informative'])

    def test_overlap_is_not_padded_or_wrapped(self):
        render = distinct_frames()
        lua = [bytes([100])*128, bytes([101])*128] + render[:4]
        report = transition_diagnostic(render, lua, 2, 2)
        # Three perfect boundary matches cover only 3 of 5 transitions.
        # Still worth investigating, but not an informative offset.
        self.assertIsNone(report['transition_best_offset_steps'])
        self.assertEqual(report['transition_top_scoring_offset_steps'], 2)
        self.assertEqual(report['transition_assessment'], 'INSUFFICIENT_OVERLAP')
        self.assertEqual(report['transition_candidates'][-1]['overlapping_transitions'], 3)
        self.assertEqual(report['transition_candidates'][-1]['matching_active_transitions'], 3)
        self.assertFalse(report['transition_candidates'][-1]['overlap_sufficient'])
        self.assertAlmostEqual(report['transition_candidates'][-1]['overlap_fraction'], 3/5)

    def test_four_of_five_transition_coverage_remains_informative(self):
        render = distinct_frames()
        lua = [bytes([0x9b])*128] + render[:-1]
        result = transition_diagnostic(render, lua, 2, 2)
        winning = result['transition_candidates'][3]
        self.assertEqual(winning['overlapping_transitions'], 4)
        self.assertAlmostEqual(winning['overlap_fraction'], 4/5)
        self.assertTrue(winning['overlap_sufficient'])
        self.assertTrue(result['transition_hypothesis_informative'])
        self.assertEqual(result['transition_assessment'],
                         'DIAGNOSTIC_HYPOTHESIS_ONLY')

    def test_longer_run_with_two_step_offset_has_sufficient_coverage(self):
        changes = [1 << i for i in range(9)]
        render = frames_from_masks(changes)
        lua = [bytes([101])*128, bytes([102])*128] + render[:-2]
        result = transition_diagnostic(render, lua, 2, 2)
        winner = result['transition_candidates'][-1]
        self.assertEqual(winner['overlapping_transitions'], 7)
        self.assertAlmostEqual(winner['overlap_fraction'], 7/9)
        self.assertTrue(winner['overlap_sufficient'])
        self.assertEqual(result['transition_best_offset_steps'], 2)
        self.assertTrue(result['transition_hypothesis_informative'])
        self.assertFalse(result['frame_sync_verified'])

    def test_early_matches_cannot_override_lack_of_overlap(self):
        changes = [1 << i for i in (0, 1, 2, 3, 4, 5, 6)]
        render = frames_from_masks(changes)
        lua = [bytes([88])*128, bytes([89])*128] + render[:-2]
        result = transition_diagnostic(render, lua, 1, 2)
        self.assertEqual(result['transition_top_scoring_offset_steps'], 2)
        self.assertAlmostEqual(result['transition_candidates'][-1]['overlap_fraction'],
                               5/7)
        self.assertIsNone(result['transition_best_offset_steps'])
        self.assertEqual(result['transition_assessment'], 'INSUFFICIENT_OVERLAP')
        self.assertFalse(result['transition_hypothesis_informative'])

    def test_exact_frame_alignment_reports_full_overlap(self):
        render = distinct_frames()
        result = transition_diagnostic(render, render, 2, 2)
        winner = result['transition_candidates'][2]
        self.assertEqual(winner['overlapping_transitions'], 5)
        self.assertEqual(winner['overlap_fraction'], 1)
        self.assertTrue(winner['overlap_sufficient'])
        self.assertEqual(result['transition_minimum_overlap_fraction'], 0.75)

    def test_static_scene_reason_is_ambiguous_not_low_coverage(self):
        render = [bytes(128)]*6
        result = transition_diagnostic(render, render, 2, 2)
        self.assertEqual(result['transition_assessment'], 'TIED_BEST_CANDIDATES')
        self.assertIsNone(result['transition_top_scoring_offset_steps'])
        self.assertIsNone(result['transition_best_offset_steps'])
        self.assertFalse(result['transition_hypothesis_informative'])

    def test_reject_wrong_types_lengths_and_offsets(self):
        frames = distinct_frames()
        for a, b, step, radius in (
                (frames[:3], frames[:3], 2, 1),
                (frames, frames[:4], 2, 1),
                (frames, frames, True, 1),
                (frames, frames, 2, -1),
                (frames, frames, 2, 4),
                (frames, [bytes(127)] * 6, 2, 1),
                (frames, [bytearray(128)] * 6, 2, 1),
                (frames, frames, 2, True)):
            with self.subTest(step=step, radius=radius):
                with self.assertRaises(ValueError):
                    transition_diagnostic(a, b, step, radius)


if __name__ == '__main__':
    unittest.main()
