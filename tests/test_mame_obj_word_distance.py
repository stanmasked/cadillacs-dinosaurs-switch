"""ROM-free tests of conservative CPS-1 register-word offset hints.

All comparisons are synthetic. A best word-distance score is not original
frame synchronization evidence and cannot make pixel parity eligible.
"""
import unittest

from tools.mame_obj_sequence_alignment import audit_sequence


def state(number):
    return bytes(((i * 19 + number * 73) & 255) for i in range(128))


def frames():
    return [state(i) for i in range(6)]


def change_one_word(raw, index=0):
    result=bytearray(raw)
    result[index*2] ^= 0x01
    return bytes(result)


class RegisterWordDistanceTests(unittest.TestCase):
    def test_exact_aligned_frames_remain_best_zero(self):
        ref=frames()
        report=audit_sequence(ref,ref,2,2)
        self.assertEqual(report['best_offset_steps'],0)
        self.assertEqual(report['closest_word_offset_steps'],0)
        self.assertEqual(report['closest_word_mismatch_fraction'],0)
        self.assertEqual(report['candidates'][2]['different_register_words'],0)
        self.assertEqual(report['candidates'][2]['compared_register_words'],6*64)
        self.assertTrue(report['offset_hypothesis_informative'])
        self.assertFalse(report['frame_sync_verified'])
        self.assertFalse(report['pixel_parity_eligible'])

    def test_no_exact_match_yields_no_strong_shift(self):
        ref=frames()
        other=[state(i+60) for i in range(6)]
        report=audit_sequence(ref,other,2,2)
        self.assertIsNone(report['best_offset_steps'])
        self.assertIsNone(report['best_offset_nominal_frames'])
        self.assertIsNone(report['best_overlap_pairs'])
        self.assertTrue(report['no_exact_register_pairs'])
        self.assertFalse(report['offset_hypothesis_informative'])

    def test_one_wrong_word_per_shifted_frame_reports_weak_hint(self):
        ref=frames()
        shifted=[state(99)]+[change_one_word(r,7) for r in ref[:-1]]
        report=audit_sequence(ref,shifted,2,2)
        self.assertTrue(report['no_exact_register_pairs'])
        self.assertIsNone(report['best_offset_steps'])
        self.assertEqual(report['closest_word_offset_steps'],1)
        self.assertEqual(report['closest_word_offset_nominal_frames'],2)
        self.assertAlmostEqual(report['closest_word_mismatch_fraction'],1/64)
        self.assertTrue(report['word_distance_diagnostic_only'])
        self.assertFalse(report['offset_hypothesis_informative'])
        self.assertFalse(report['frame_sync_verified'])

    def test_two_word_mutation_counts_two_not_four_byte_errors(self):
        ref=frames()
        altered=list(ref)
        altered[0]=change_one_word(change_one_word(ref[0],3),9)
        report=audit_sequence(ref,altered,1,0)
        self.assertEqual(report['candidates'][0]['different_register_words'],2)
        self.assertEqual(report['candidates'][0]['compared_register_words'],384)
        self.assertEqual(report['candidates'][0]['exact_equal_pairs'],5)

    def test_static_frames_do_not_pick_a_closest_offset(self):
        ref=[bytes(128)]*6
        report=audit_sequence(ref,ref,2,2)
        self.assertEqual(report['ambiguous_closest_word_offsets'],[-2,-1,0,1,2])
        self.assertIsNone(report['closest_word_offset_steps'])
        self.assertEqual(report['closest_word_mismatch_fraction'],0)
        self.assertFalse(report['offset_hypothesis_informative'])

    def test_repeated_cycle_does_not_pick_a_closest_offset(self):
        ref=[state(i%2) for i in range(6)]
        report=audit_sequence(ref,ref,2,2)
        self.assertEqual(report['ambiguous_closest_word_offsets'],[-2,0,2])
        self.assertIsNone(report['closest_word_offset_steps'])
        self.assertFalse(report['offset_hypothesis_informative'])

    def test_no_correspondence_is_not_presented_as_full_frame_match(self):
        ref=frames()
        report=audit_sequence(ref,[bytes(128)]*6,2,2)
        self.assertTrue(report['no_exact_register_pairs'])
        self.assertIsNone(report['best_offset_steps'])
        self.assertIsNone(report['closest_word_offset_steps'])
        self.assertFalse(report['frame_sync_verified'])

    def test_partial_shift_keeps_overlap_counts(self):
        ref=frames()
        shifted=[state(101),state(102)]+[change_one_word(r,0) for r in ref[:4]]
        report=audit_sequence(ref,shifted,2,2)
        self.assertEqual(report['closest_word_offset_steps'],2)
        cand=report['candidates'][-1]
        self.assertEqual(cand['compared_pairs'],4)
        self.assertEqual(cand['compared_register_words'],256)
        self.assertEqual(cand['different_register_words'],4)
        self.assertLess(cand['register_word_mismatch_fraction'],0.02)


if __name__ == '__main__':
    unittest.main()
