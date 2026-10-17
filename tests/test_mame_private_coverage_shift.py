"""ROM-free tests of six-frame coverage-lag hints, not video synchronization."""
import json
import unittest

from tools.mame_private_coverage_shift import (
    nominal_coverage_shift_hypotheses, SHIFTS,
)


def frame_rows(lua_indexes, cpp_indexes):
    rows = []
    for i in range(6):
        lua = i in lua_indexes
        cpp = i in cpp_indexes
        rows.append({
            'nominal_frame': 900 + 2 * i,
            'lua_files_present': 6 if lua else 0,
            'cpp_files_present': 3 if cpp else 0,
            'lua_valid_sized_files': 6 if lua else 0,
            'cpp_valid_sized_files': 3 if cpp else 0,
            'lua_size_only_state': 'COMPLETE_SIZE_ONLY' if lua else 'ABSENT',
            'cpp_size_only_state': 'COMPLETE_SIZE_ONLY' if cpp else 'ABSENT',
        })
    return rows


class PrivateCoverageShiftTests(unittest.TestCase):
    def test_plus_one_nominal_shift_is_unverified_hypothesis_only(self):
        result = nominal_coverage_shift_hypotheses(
            frame_rows({0, 1, 2}, {1, 2, 3}))
        self.assertEqual(result['status'], 'OFF_LABEL_COVERAGE_HYPOTHESIS_ONLY')
        self.assertEqual(result['candidate_cpp_relative_to_lua_shift_samples'], 1)
        self.assertEqual(result['candidate_cpp_relative_to_lua_shift_nominal_frames'], 2)
        self.assertEqual(result['same_nominal_label_complete_pairs'], 2)
        self.assertEqual(result['paired_full_size_only_frames_per_shift'], [0, 1, 2, 3, 2])
        self.assertFalse(result['hypothesis_verified'])
        self.assertFalse(result['hardware_vblank_observed'])

    def test_minus_one_nominal_shift_is_directional_not_timing_proof(self):
        result = nominal_coverage_shift_hypotheses(
            frame_rows({1, 2, 3}, {0, 1, 2}))
        self.assertEqual(result['status'], 'OFF_LABEL_COVERAGE_HYPOTHESIS_ONLY')
        self.assertEqual(result['candidate_cpp_relative_to_lua_shift_samples'], -1)
        self.assertEqual(result['candidate_cpp_relative_to_lua_shift_nominal_frames'], -2)
        self.assertFalse(result['obj_latch_age_verified'])

    def test_all_six_complete_does_not_suggest_a_shift(self):
        result = nominal_coverage_shift_hypotheses(
            frame_rows(set(range(6)), set(range(6))))
        self.assertEqual(result['status'], 'NO_OFF_LABEL_COVERAGE_ADVANTAGE')
        self.assertEqual(result['same_nominal_label_complete_pairs'], 6)
        self.assertIsNone(result['candidate_cpp_relative_to_lua_shift_samples'])
        self.assertFalse(result['frame_sync_verified'])

    def test_one_source_missing_or_sparse_is_insufficient(self):
        for lua, cpp in (({0, 1, 2}, set()), ({0}, {1, 2, 3}),
                         (set(), set())):
            with self.subTest(lua=lua, cpp=cpp):
                result = nominal_coverage_shift_hypotheses(frame_rows(lua, cpp))
                self.assertEqual(result['status'], 'INSUFFICIENT_COMPLETE_SOURCE_FRAMES')
                self.assertIsNone(result['candidate_cpp_relative_to_lua_shift_samples'])

    def test_candidate_not_present_if_same_label_overlap_is_stronger(self):
        result = nominal_coverage_shift_hypotheses(
            frame_rows({0, 2, 4}, {0, 2, 4}))
        self.assertEqual(result['status'], 'NO_OFF_LABEL_COVERAGE_ADVANTAGE')
        self.assertIsNone(result['candidate_cpp_relative_to_lua_shift_samples'])

    def test_rejects_spoofed_labels_counts_and_states(self):
        for key, value in (
            ('nominal_frame', 901), ('lua_valid_sized_files', True),
            ('cpp_valid_sized_files', 4), ('lua_size_only_state', 'COMPLETE_SIZE_ONLY'),
        ):
            rows = frame_rows({1}, {2})
            rows[0][key] = value
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'invalid|disagree'):
                    nominal_coverage_shift_hypotheses(rows)
        with self.assertRaisesRegex(ValueError, 'selection'):
            nominal_coverage_shift_hypotheses(frame_rows({0}, {0})[:-1])
        with self.assertRaisesRegex(ValueError, 'selection'):
            nominal_coverage_shift_hypotheses(frame_rows({0}, {0}), frame_step=True)

    def test_privacy_and_fixed_cautions(self):
        rows = frame_rows({0, 1, 2}, {1, 2, 3})
        rows[0]['private_path'] = '/secret/original-dino.zip'
        rows[0]['session_token'] = '0123456789abcdef' * 2
        out = nominal_coverage_shift_hypotheses(rows)
        encoded = json.dumps(out)
        self.assertNotIn('/secret/', encoded)
        self.assertNotIn('0123456789abcdef', encoded)
        self.assertEqual(out['shift_offsets_in_nominal_samples'], list(SHIFTS))
        self.assertFalse(out['pixel_parity_eligible'])


if __name__ == '__main__':
    unittest.main()
