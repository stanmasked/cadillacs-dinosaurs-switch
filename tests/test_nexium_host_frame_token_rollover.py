"""Stage 266: 16-bit X11 token vs full-width guest render iteration.

The real NRO-frame verifier already proves a unique native iteration;
these are synthetic *interface* regression cases for its wrap boundary,
not new emulator measurements or guest binary modifications.
"""
import unittest
from unittest.mock import patch

from tools import verify_nexium_host_x11_sample_sequence as sequence
from tools import verify_nexium_host_first_sample_gap_paired as gap
from test_nexium_host_x11_sample_sequence import RawBoundedSequenceTests
from test_nexium_host_first_sample_gap_paired import PairedFirstSampleGapTests


class FullWidthHostFrameIdentityTests(unittest.TestCase):
    def setUp(self):
        fixture = RawBoundedSequenceTests(
            'test_correct_all_three_x11_samples_bind_to_native_guest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.guest=fixture.guests['baseline']
        self.nro=fixture.nros['baseline']
        # Ground all other raw evidence and exact NRO from the normal
        # independently verified synthetic fixture before replacing the
        # single prior full-width native iteration in a scoped mock.
        self.original=sequence.prior.verify(self.guest,self.nro,'baseline')

    def replay_with_native_iteration(self,iteration):
        prior={**self.original,'guest_render_iteration':iteration}
        with patch.object(sequence.prior,'verify',return_value=prior):
            return sequence.verify(self.guest,self.nro,'baseline')

    def test_unwrapped_native_iteration_is_not_truncated(self):
        got=self.replay_with_native_iteration(2250)
        self.assertEqual(got['guest_submitted_render_iteration'],2250)

    def test_first_wrap_preserves_full_native_iteration(self):
        got=self.replay_with_native_iteration(65536+2250)
        self.assertEqual(got['guest_submitted_render_iteration'],67786)

    def test_second_wrap_preserves_full_native_iteration(self):
        got=self.replay_with_native_iteration(2*65536+2250)
        self.assertEqual(got['guest_submitted_render_iteration'],133322)

    def test_wrong_low_sixteen_bits_rejected_after_wrap(self):
        with self.assertRaises(ValueError):
            self.replay_with_native_iteration(65536+2251)

    def test_invalid_guest_iteration_type_or_overflow_rejected(self):
        for iteration in (False,2250.0,'67786',-1,0,2**32,2**32+2250):
            with self.subTest(iteration=iteration):
                with self.assertRaises(ValueError):
                    self.replay_with_native_iteration(iteration)

    def test_wrap_with_wrong_raw_positive_token_rejected(self):
        import json
        path=self.guest/'host-x11-sample-sequence-evidence.json'
        raw=json.loads(path.read_text())
        raw['samples'][-1]['frame_token_u16']=2251
        path.write_text(json.dumps(raw),encoding='ascii')
        with self.assertRaises(ValueError):
            self.replay_with_native_iteration(65536+2250)


class FullWidthPairedGapTests(unittest.TestCase):
    def setUp(self):
        fixture=PairedFirstSampleGapTests('test_initial_gap_bounded_by_both_host_clocks')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.guest=fixture.guests['baseline']
        self.nro=fixture.nros['baseline']
        self.observed=gap.cadence.summarize('baseline',self.guest,self.nro)
        self.command=gap.keydown.one('baseline',self.guest,self.nro)

    def emulate_full_native_iteration(self,observed_iteration,command_iteration):
        sample={**self.observed,
                'guest_submitted_render_iteration':observed_iteration}
        bracket={**self.command,'native_render_iteration':command_iteration}
        with (patch.object(gap.cadence,'summarize',return_value=sample),
              patch.object(gap.keydown,'one',return_value=bracket)):
            return gap.one('baseline',self.guest,self.nro)

    def test_first_wrap_keeps_matching_full_native_frame(self):
        result=self.emulate_full_native_iteration(65536+2250,65536+2250)
        self.assertEqual(result['guest_submitted_render_iteration'],67786)
        self.assertTrue(result['host_first_sample_blind_interval_audited'])
        self.assertFalse(result['first_visible_frame_onset_verified'])

    def test_second_wrap_keeps_matching_full_native_frame(self):
        result=self.emulate_full_native_iteration(2*65536+2250,2*65536+2250)
        self.assertEqual(result['guest_submitted_render_iteration'],133322)

    def test_same_low_bits_but_different_full_frame_rejected(self):
        with self.assertRaises(ValueError):
            self.emulate_full_native_iteration(65536+2250,2*65536+2250)

    def test_wrong_native_full_frame_rejected(self):
        with self.assertRaises(ValueError):
            self.emulate_full_native_iteration(65536+2250,65536+2251)


if __name__=='__main__':
    unittest.main()
