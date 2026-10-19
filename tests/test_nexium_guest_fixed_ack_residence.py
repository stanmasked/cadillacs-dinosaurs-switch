"""ROM-free tests: guest-observed ACK time != actual speaker latency.

An independent Python-list FIFO oracle validates the counterfactual ledger.
Real guest reports remain SHA-bound only in the existing paired NeXium job.
"""
import copy
import itertools
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from tools import nexium_guest_fixed_ack_residence as residence


def independent_oracle(credits,capacity,initial):
    q=list(range(-initial,0))
    last_release=-initial-1
    ages=[]
    accepted=skipped=older=peak=0
    for tick,c in enumerate(credits):
        if c>len(q):
            raise ValueError("bad frozen credits")
        for _ in range(c):
            gen=q.pop(0)
            if gen<=last_release:
                raise AssertionError("oracle FIFO monotonicity")
            last_release=gen
            ages.append(tick-gen)
        if len(q)<capacity:
            q.append(tick)
            accepted+=1
        else:
            skipped+=1
        if q:
            peak=max(peak,tick-q[0])
            older+=sum(tick-gen>=3 for gen in q)
    return accepted,skipped,len(q),ages,peak,older


class GuestFrozenACKResidenceTests(unittest.TestCase):
    def test_short_horizon_frozen_guest_fifo_age_matches_independent_list_oracle(self):
        for length in (1,2,3,4):
            for credits in itertools.product((0,1,2),repeat=length):
                for initial in (0,1,2):
                    for capacity in residence.bound.DEPTHS:
                        try:
                            accepted,skipped,pending,ages,peak,older=(
                                independent_oracle(credits,capacity,initial))
                        except ValueError:
                            with self.assertRaises(ValueError):
                                residence.fifo_residence(list(credits),
                                                         capacity,initial)
                            continue
                        result=residence.fifo_residence(
                            list(credits),capacity,initial)
                        with self.subTest(credits=credits,initial=initial,
                                          capacity=capacity):
                            self.assertEqual(
                                (result['accepted_new_pcm_pages'],
                                 result['skipped_pcm_pages_discarded'],
                                 result['end_pending_pages']),
                                (accepted,skipped,pending))
                            self.assertEqual(
                                result['sum_enqueued_generation_to_observed_ack_age_ticks'],
                                sum(ages))
                            self.assertEqual(
                                result['max_enqueued_generation_to_observed_ack_age_ticks'],
                                max(ages) if ages else None)
                            self.assertEqual(
                                result['max_oldest_pending_generation_age_ticks'],
                                peak if pending or accepted else None)
                            self.assertEqual(
                                result['sum_pending_page_ticks_at_age_at_least_three'],
                                older)
                            self.assertFalse(result['physical_audio_latency_verified'])
                            self.assertFalse(result['service_timestamp_verified'])

    def test_900tick_stalled_depth_gain_is_only_extra_slot(self):
        credits=[0]*900
        for depth in residence.bound.DEPTHS:
            out=residence.fifo_residence(credits,depth,2)
            self.assertEqual(out['accepted_new_pcm_pages'],depth-2)
            self.assertEqual(out['skipped_pcm_pages_discarded'],902-depth)
            self.assertIsNone(
                out['max_enqueued_generation_to_observed_ack_age_ticks'])
            self.assertEqual(out['sum_enqueued_generation_to_observed_ack_age_ticks'],0)
            self.assertEqual(len(out['per_150tick_windows']),6)
            self.assertEqual(out['max_oldest_pending_generation_age_ticks'],901)

    def test_extra_capacity_frozen_credits_can_increase_observed_model_age(self):
        # Release one page each simulated tick: deeper capacities may
        # retain more PCM, with no demonstrated real-world benefit.
        credits=[1]*900
        profiles=[residence.fifo_residence(credits,cap,2)
                  for cap in residence.bound.DEPTHS]
        self.assertTrue(all(x['skipped_pcm_pages_discarded']==0
                            for x in profiles))
        self.assertTrue(all(x['released_pages']==900 for x in profiles))
        self.assertTrue(all(x['fifo_release_generation_order_verified']
                            for x in profiles))
        self.assertEqual(profiles[0]['max_enqueued_generation_to_observed_ack_age_ticks'],2)
        self.assertTrue(all(p['max_enqueued_generation_to_observed_ack_age_ticks']
                            >=2 for p in profiles))
        for row in profiles:
            self.assertEqual(row['mean_enqueued_age_fraction_ticks']['denominator'],
                             900)

    def test_real_depth_two_guest_rows_and_missing_tick_fail_closed(self):
        credits=[0,2,0,1,0,1]
        out=residence.fifo_residence(credits,2,2)
        rows=[]
        # Build an independent guest proof of the same two-page ledger.
        pending=2
        for credit in credits:
            pending-=credit
            submitted=int(pending<2)
            pending+=submitted
            rows.append({
                'released':credit,'submitted':submitted,
                'skipped':1-submitted,'pending':pending})
        check=residence.fifo_residence(credits,2,2,rows)
        self.assertEqual(out['released_pages'],check['released_pages'])
        forged=copy.deepcopy(rows)
        forged[-1]['pending']=0
        with self.assertRaises(ValueError):
            residence.fifo_residence(credits,2,2,forged)
        with self.assertRaises(ValueError):
            residence.fifo_residence(credits,2,2,rows[:-1])

    def test_noncanonical_credit_inputs_never_create_age_proof(self):
        for credits in ([],[0]*901,[True],[3],[-1],[1.0],{},'0',None):
            with self.subTest(credits=repr(credits)),self.assertRaises(ValueError):
                residence.fifo_residence(credits,2,2)
        for cap in (0,1,5,2.0,True,None):
            with self.subTest(cap=cap),self.assertRaises(ValueError):
                residence.fifo_residence([0],cap,2)
        for initial in (-1,3,False,1.0,None):
            with self.subTest(initial=initial),self.assertRaises(ValueError):
                residence.fifo_residence([0],2,initial)

    def test_no_guest_artifacts_is_inconclusive_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            args=[]
            for key in ('baseline-trace','baseline-report','baseline-binding',
                        'baseline-nro','experimental-trace','experimental-report',
                        'experimental-binding','experimental-nro'):
                args+=['--'+key,str(root/key)]
            output=root/'fifo-residence.json'
            args+=['--out',str(output)]
            with redirect_stdout(StringIO()) as stream:
                self.assertEqual(residence.main(args),1)
            self.assertIn('INCONCLUSIVE_GUEST_FROZEN_FIFO_AGE_MODEL',
                          stream.getvalue())
            self.assertFalse(output.exists())


if __name__=="__main__":
    unittest.main()
