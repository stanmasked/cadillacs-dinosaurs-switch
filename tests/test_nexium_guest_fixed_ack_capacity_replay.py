"""ROM-free exact DP/guest-fixed-ACK admission regressions.

Synthetic inputs are NOT NeXium evidence. The real paired comparison
calls the existing NRO/mode/SHA-bound 900-tick guest validators.
"""
import itertools
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from tools import nexium_guest_fixed_ack_capacity_replay as replay
from test_nexium_audio_ack_tick_trace import fixture


def independent_bruteforce(credits,cap,initial):
    states={(initial,0)}
    for credit in credits:
        next_states=set()
        for pending,admitted in states:
            after=pending-min(pending,credit)
            next_states.add((after,admitted))
            if after<cap:
                next_states.add((after+1,admitted+1))
        states=next_states
    return max(x[1] for x in states)


class RealGuestFixedACKReplayTests(unittest.TestCase):
    def test_real_guest_guest_depth_two_ledger_reconciles_synthetic_source(self):
        rows,report=fixture()
        credits=[r['released'] for r in rows]
        for cap in replay.DEPTHS:
            with self.subTest(capacity=cap):
                result=replay.replay_credits(credits,cap,1,rows)
                self.assertEqual(result['submitted'],900)
                self.assertEqual(result['skipped'],0)
                self.assertEqual(result['ack_pages_consumed'],900)
                self.assertEqual(result['end_pending'],1)
                self.assertEqual(result['exact_max_admissions_under_frozen_ack'],900)
                self.assertEqual(len(result['windows']),6)
                self.assertEqual(result['windows'][-1]['tick_end'],900)
                self.assertFalse(
                    result['guest_device_ack_schedule_preserved_counterfactually'])

    def test_short_horizon_finite_dp_equal_independent_exhaustive_search(self):
        # DP proof does not rely on the greedy reference implementation.
        for length in (1,2,3,4):
            for credits in itertools.product((0,1,2),repeat=length):
                for start in (0,1,2):
                    for cap in replay.DEPTHS:
                        with self.subTest(credits=credits,start=start,cap=cap):
                            exact=replay.exact_best_admissions(
                                list(credits),cap,start)
                            self.assertEqual(
                                exact,independent_bruteforce(credits,cap,start))
                            # Some hypothetical schedules demand more ACKs
                            # than outstanding pages. Only valid schedules
                            # may be projected as fully consumed.
                            try:
                                guest=replay.replay_credits(
                                    list(credits),cap,start)
                            except ValueError as exc:
                                self.assertIn('nonexistent',str(exc))
                            else:
                                self.assertEqual(guest['submitted'],exact)
                                self.assertEqual(
                                    guest['submitted']+guest['skipped'],length)

    def test_no_ack_can_have_one_two_hypothetical_extra_slots(self):
        credits=[0]*900
        rows=[]
        for cap in replay.DEPTHS:
            result=replay.replay_credits(credits,cap,2)
            self.assertEqual(result['submitted'],cap-2)
            self.assertEqual(result['skipped'],902-cap)
            self.assertEqual(result['peak_pending'],cap)
            self.assertEqual(result['end_pending'],cap)
            self.assertEqual(result['unavoidable_skips_under_frozen_ack'],
                             902-cap)
            self.assertTrue(all(w['released']==0 for w in result['windows']))

    def test_nonuniform_ack_bursts_and_windows_reconcile(self):
        credits=([2,0,0,2,0,1]*150)
        for cap in replay.DEPTHS:
            result=replay.replay_credits(credits,cap,2)
            self.assertEqual(result['ticks'],900)
            self.assertEqual(result['frozen_ack_pages'],sum(credits))
            self.assertEqual(sum(w['released'] for w in result['windows']),
                             sum(credits))
            self.assertEqual(sum(w['submitted'] for w in result['windows']),
                             result['submitted'])
            self.assertEqual(sum(w['skipped'] for w in result['windows']),
                             result['skipped'])
            self.assertEqual(result['end_pending'],
                             2+result['submitted']-result['ack_pages_consumed'])
            self.assertLessEqual(result['peak_pending'],cap)

    def test_forged_guest_depth_two_ack_sequence_is_rejected(self):
        rows,report=fixture()
        credits=[r['released'] for r in rows]
        fake=[dict(x) for x in rows]
        fake[220]['submitted']=0
        with self.assertRaisesRegex(ValueError,'guest admission'):
            replay.replay_credits(credits,2,1,fake)
        fake=[dict(x) for x in rows]
        fake[360]['pending']=2
        with self.assertRaisesRegex(ValueError,'guest admission'):
            replay.replay_credits(credits,2,1,fake)
        with self.assertRaises(ValueError):
            replay.replay_credits(credits,2,1,rows[:-1])

    def test_noncanonical_credits_capacity_and_initial_fail_closed(self):
        for credits in ([],[0]*901,[3],[True],[False],[0.5],None,{},'1'):
            with self.subTest(credits=repr(credits)),self.assertRaises(ValueError):
                replay.replay_credits(credits,2,2)
        for invalid in (-1,0,1,5,True,2.0,None):
            with self.subTest(cap=invalid),self.assertRaises(ValueError):
                replay.replay_credits([0],invalid,2)
        for invalid in (-1,3,True,1.0,None):
            with self.subTest(initial=invalid),self.assertRaises(ValueError):
                replay.replay_credits([0],2,invalid)

    def test_missing_real_guest_files_do_not_create_a_success_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            args=[]
            for flag in ('baseline-trace','baseline-report','baseline-binding',
                         'baseline-nro','experimental-trace','experimental-report',
                         'experimental-binding','experimental-nro'):
                args.extend(['--'+flag,str(directory/flag)])
            output=directory/'hypotheses.json'
            args+=['--out',str(output)]
            with redirect_stdout(StringIO()) as results:
                self.assertEqual(replay.main(args),1)
            self.assertIn('INCONCLUSIVE_FROZEN_GUEST_ACK_CAPACITY_HYPOTHESES',
                          results.getvalue())
            self.assertFalse(output.exists())


if __name__=="__main__":
    unittest.main()
