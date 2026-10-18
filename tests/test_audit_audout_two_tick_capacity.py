"""No-ROM counterfactual checks; never treats fixed releases as audout."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from tools import audit_audout_two_tick_capacity as model


class FixedReleaseTwoTickTests(unittest.TestCase):
    def test_full_queue_one_release_first_no_release_later(self):
        out=model.compare(2,1,0)
        a=out['eager_current_policy']
        b=out['reserve_later_hypothesis']
        self.assertEqual((a['first_tick_admitted'],a['later_tick_admitted']),
                         (True,False))
        self.assertEqual((b['first_tick_admitted'],b['later_tick_admitted']),
                         (False,True))
        self.assertEqual((a['submitted_ticks'],b['submitted_ticks']),(1,1))
        self.assertEqual((a['skipped_ticks'],b['skipped_ticks']),(1,1))
        self.assertFalse(out['does_reserving_improve_total_admissions'])
        self.assertTrue(out['does_reserving_shift_which_tick_is_dropped'])
        self.assertFalse(out['audio_fix_verified'])

    def test_additional_exogenous_release_second_tick_allows_two(self):
        out=model.compare(2,1,1)
        a=out['eager_current_policy']
        self.assertEqual(a['submitted_ticks'],2)
        self.assertEqual(a['skipped_ticks'],0)
        self.assertFalse(a['later_tick_skipped'])
        self.assertFalse(out['audio_fix_verified'])

    def test_zero_release_and_full_queue_drops_both(self):
        out=model.compare(2,0,0)
        for key in ('eager_current_policy','reserve_later_hypothesis'):
            trial=out[key]
            self.assertEqual((trial['submitted_ticks'],trial['skipped_ticks']),
                             (0,2))
            self.assertEqual(trial['pending_after_later'],2)

    def test_empty_queue_can_admit_two_without_release(self):
        out=model.compare(0,0,0)
        self.assertEqual(out['eager_current_policy']['submitted_ticks'],2)
        self.assertEqual(out['eager_current_policy']['pending_after_later'],2)

    def test_single_pending_without_release_shifts_drop_only(self):
        out=model.compare(1,0,0)
        a,b=out['eager_current_policy'],out['reserve_later_hypothesis']
        self.assertEqual((a['submitted_ticks'],b['submitted_ticks']),(1,1))
        self.assertTrue(a['later_tick_skipped'])
        self.assertTrue(b['first_tick_skipped'])

    def test_release_at_second_is_not_a_fix_when_externally_assumed(self):
        out=model.compare(2,0,1)
        self.assertEqual(out['eager_current_policy']['submitted_ticks'],1)
        self.assertTrue(out['eager_current_policy']['first_tick_skipped'])
        self.assertFalse(out['eager_current_policy']['later_tick_skipped'])
        self.assertFalse(out['real_guest_execution_authenticated'])

    def test_invalid_inputs_rejected_including_bools_and_fake_releases(self):
        for args in ((True,0,0),(2,3,0),(2,-1,0),(2,0,3),
                     (2,2,1),(0,1,0),(0,0,1)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    model.compare(*args)
        with self.assertRaises(ValueError):
            model.simulate(2,1,0,'stale-pcm-rewrite')

    def test_all_synthetic_valid_schedules_never_queue_more_than_two(self):
        for start in range(3):
            for first in range(start+1):
                for later in range(3):
                    for policy in ('eager','reserve_later'):
                        try:
                            state=model.simulate(start,first,later,policy)
                        except ValueError:
                            continue
                        self.assertLessEqual(state['pending_after_first'],2)
                        self.assertLessEqual(state['pending_after_later'],2)
                        self.assertEqual(state['tick_steps'],2)
                        self.assertEqual(state['submitted_ticks']+
                                         state['skipped_ticks'],2)

    def test_cli_explicitly_disclaims_audio_fix_or_guest_provenance(self):
        script=Path(__file__).resolve().parents[1]/'tools'/(
            'audit_audout_two_tick_capacity.py')
        proc=subprocess.run([sys.executable,str(script)],
                            check=True,capture_output=True,text=True)
        data=json.loads(proc.stdout)
        self.assertEqual(data['status'],
                         'SYNTHETIC_NO_DEVICE_TIMING_OR_CAUSAL_PROOF')
        self.assertEqual(data['eager_current_policy']['skipped_ticks'],1)
        self.assertFalse(data['speaker_audibility_verified'])
        self.assertFalse(data['latency_verified'])
        self.assertFalse(data['audio_fix_verified'])
        invalid=subprocess.run(
            [sys.executable,str(script),'--initial-pending','3'],
            check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(invalid.stdout)['status'],
                         'INCONCLUSIVE_INVALID_SYNTHETIC_SCHEDULE')


if __name__=='__main__':
    unittest.main()
