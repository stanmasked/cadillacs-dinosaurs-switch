"""Synthetic Stage 157 A/B negatives; not actual NeXium execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools import verify_nexium_audio_mid_batch_ab as ab
from test_compare_nexium_audio_stress_runs import (
    fixture,with_release_probe,with_batch_position,
    with_batch_position_poll,with_released_page_positions,
    with_fixed_ack_headroom,
)


def complete(enabled,variation=0):
    r=with_fixed_ack_headroom(with_released_page_positions(
        with_batch_position_poll(with_batch_position(
            with_release_probe(fixture(variation),25)))))
    w=[]
    for i in range(6):
        w.append({
            'tick_start':i*150,'tick_end':(i+1)*150,
            'poll_calls':25 if enabled else 0,
            'poll_released_pages':1 if enabled else 0,
        })
    r.update({
        'guest_mid_batch_extra_poll_probe_present':True,
        'guest_mid_batch_extra_poll_enabled':enabled,
        'guest_mid_batch_extra_poll_calls':150 if enabled else 0,
        'guest_mid_batch_extra_poll_released_pages':6 if enabled else 0,
        'checkpoint_guest_mid_batch_extra_poll_intervals':w,
    })
    return r


class ExperimentalABTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='dino-mid-ab-test-')
        root=Path(self.temp.name)
        self.a=root/'baseline.json'
        self.b=root/'experimental.json'
        self.write(self.a,complete(False,0))
        self.write(self.b,complete(True,1))

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(path,data):
        path.write_text(json.dumps(data,sort_keys=True)+'\n',
                        encoding='ascii')

    def test_verified_guest_mode_and_exact_extra_poll_invocations(self):
        result=ab.compare(self.a,self.b)
        self.assertEqual(result['status'],
                         'UNCONTROLLED_GUEST_RUN_DESCRIPTIVE_ONLY')
        self.assertEqual(result['baseline']
                         ['additional_nonblocking_poll_calls'],0)
        self.assertEqual(result['experimental']
                         ['additional_nonblocking_poll_calls'],150)
        self.assertEqual(result['experimental']
                         ['pages_released_by_additional_polls'],6)
        self.assertFalse(result['causal_audio_improvement_verified'])
        self.assertFalse(result['audio_latency_verified'])

    def test_swapped_variants_are_rejected(self):
        with self.assertRaises(ValueError):
            ab.compare(self.b,self.a)

    def test_legacy_reports_lack_guest_mode_witness(self):
        self.write(self.a,fixture())
        with self.assertRaises(ValueError):
            ab.compare(self.a,self.b)

    def test_forged_experimental_mode_and_counters_are_rejected(self):
        valid=complete(True,1)
        for name,bad in (
                ('guest_mid_batch_extra_poll_enabled',False),
                ('guest_mid_batch_extra_poll_enabled',1),
                ('guest_mid_batch_extra_poll_probe_present',False),
                ('guest_mid_batch_extra_poll_calls',149),
                ('guest_mid_batch_extra_poll_calls',True),
                ('guest_mid_batch_extra_poll_released_pages',31),
                ('guest_mid_batch_extra_poll_released_pages',7)):
            with self.subTest(name=name,bad=bad):
                forged=copy.deepcopy(valid)
                forged[name]=bad
                self.write(self.b,forged)
                with self.assertRaises(ValueError):
                    ab.compare(self.a,self.b)

    def test_forged_experimental_windows_fail_even_if_totals_match(self):
        valid=complete(True,1)
        for change in ('calls','releases','fields','start','move'):
            with self.subTest(change=change):
                broken=copy.deepcopy(valid)
                windows=broken['checkpoint_guest_mid_batch_extra_poll_intervals']
                if change=='calls':
                    windows[0]['poll_calls']=24
                elif change=='releases':
                    windows[0]['poll_released_pages']=6
                elif change=='fields':
                    windows[0]['fake_audio_fix']=True
                elif change=='start':
                    windows[0]['tick_start']=1
                else:
                    # Preserve the global sum of six, but assign all
                    # six ACKs to one window that independently proves
                    # only five later-tick page returns.
                    for window in windows:
                        window['poll_released_pages']=0
                    windows[0]['poll_released_pages']=6
                self.write(self.b,broken)
                with self.assertRaises(ValueError):
                    ab.compare(self.a,self.b)

    def test_valid_reallocation_between_intervals_is_not_a_forgery(self):
        # No per-call timestamps are witnessed: shifting a single ACK
        # between two windows remains consistent with five confirmed
        # later-tick page returns in either interval. Do not reject it.
        moved=complete(True,1)
        windows=moved['checkpoint_guest_mid_batch_extra_poll_intervals']
        windows[0]['poll_released_pages']=0
        windows[1]['poll_released_pages']=2
        self.write(self.b,moved)
        result=ab.compare(self.a,self.b)
        self.assertEqual(result['experimental']
                         ['pages_released_by_additional_polls'],6)
        self.assertFalse(result['causal_audio_improvement_verified'])


    def test_identical_150tick_tick_exposure_is_not_causal_matching(self):
        result=ab.compare(self.a,self.b)
        self.assertTrue(result['per_150tick_batch_exposure_matched'])
        self.assertFalse(result['exact_frame_pacing_matched'])
        self.assertEqual(result['matched_exposure_later_skip_count_delta'],-6)
        self.assertEqual(result['matched_exposure_later_ack_count_delta'],0)
        self.assertFalse(result['causal_audio_improvement_verified'])

    def test_unmatched_catchup_exposure_suppresses_skip_improvement(self):
        valid=complete(True,1)
        # A pure exposure diagnostic accepts a different legal render
        # partition; deep report verification happens before it is used.
        windows=valid['checkpoint_batch_position_intervals']
        modes=valid['checkpoint_mode_intervals']
        windows[0]['later_tick_steps']=24
        windows[0]['first_tick_steps']=24
        modes[0]['single_tick_render_steps']=102
        profile=ab.compare_batch_exposure(complete(False),valid)
        self.assertFalse(profile['per_150tick_batch_exposure_matched'])
        self.assertIsNone(
            profile['matched_exposure_later_skip_count_delta'])
        self.assertIsNone(
            profile['matched_exposure_later_ack_count_delta'])
        self.assertFalse(profile['exact_frame_pacing_matched'])

    def test_catchup_exposure_mismatch_is_descriptive_not_a_failed_run(self):
        # Production report validation correctly rejects a single forged
        # window when it disagrees with all other guest ledger fields.
        bad=complete(True,1)
        bad['checkpoint_batch_position_intervals'][0][
            'later_tick_steps']=24
        self.write(self.b,bad)
        with self.assertRaises(ValueError):
            ab.compare(self.a,self.b)

    def test_exposure_helper_rejects_noncanonical_and_unpartitioned_ticks(self):
        for bad in (True,-1,151,24):
            with self.subTest(bad=bad):
                forged=complete(False)
                forged['checkpoint_batch_position_intervals'][0][
                    'later_tick_steps']=bad
                with self.assertRaises(ValueError):
                    ab.exposure_profile(forged)

    def test_exposure_profile_keeps_all_six_disjoint_windows(self):
        out=ab.exposure_profile(complete(True,1))
        self.assertEqual(len(out),6)
        self.assertEqual(sum(w['single_ticks']+
                             w['first_batch_ticks']+
                             w['later_batch_ticks'] for w in out),900)
        self.assertEqual(out[0]['tick_start'],0)
        self.assertEqual(out[-1]['tick_end'],900)
        self.assertEqual(sum(w['later_batch_skips'] for w in out),114)

    def test_six_matched_windows_report_separate_skip_directions(self):
        result=ab.compare(self.a,self.b)
        windows=result['matched_exposure_later_skip_window_deltas']
        self.assertEqual(len(windows),6)
        self.assertEqual(
            [w['extra_minus_baseline_later_skips'] for w in windows],
            [-1]*6)
        self.assertEqual(
            [w['tick_start'] for w in windows],
            [0,150,300,450,600,750])
        self.assertEqual(result['matched_exposure_later_skip_windows_improved'],6)
        self.assertEqual(result['matched_exposure_later_skip_windows_worsened'],0)
        self.assertFalse(
            result['matched_exposure_later_skip_directions_mixed'])
        self.assertFalse(result['causal_audio_improvement_verified'])

    def test_zero_aggregate_can_hide_opposing_window_changes(self):
        baseline=complete(False)
        experimental=complete(True)
        windows=experimental['checkpoint_batch_position_intervals']
        windows[0]['later_tick_skips']+=2
        windows[1]['later_tick_skips']-=2
        # This helper exercises descriptive arithmetic only; a forged
        # standalone guest report must still fail the full ledger verifier.
        result=ab.compare_batch_exposure(baseline,experimental)
        self.assertTrue(result['per_150tick_batch_exposure_matched'])
        self.assertEqual(result['matched_exposure_later_skip_count_delta'],0)
        self.assertEqual(
            [w['extra_minus_baseline_later_skips']
             for w in result['matched_exposure_later_skip_window_deltas']],
            [2,-2,0,0,0,0])
        self.assertEqual(result['matched_exposure_later_skip_windows_improved'],1)
        self.assertEqual(result['matched_exposure_later_skip_windows_worsened'],1)
        self.assertTrue(result['matched_exposure_later_skip_directions_mixed'])
        self.assertFalse(result['exact_frame_pacing_matched'])

    def test_equal_exposure_and_equal_skips_is_not_an_improvement(self):
        result=ab.compare_batch_exposure(complete(False),complete(True))
        self.assertEqual(result['matched_exposure_later_skip_count_delta'],0)
        self.assertEqual(result['matched_exposure_later_skip_windows_improved'],0)
        self.assertEqual(result['matched_exposure_later_skip_windows_worsened'],0)
        self.assertFalse(result['matched_exposure_later_skip_directions_mixed'])

    def test_exposure_drift_nulls_all_window_direction_claims(self):
        baseline=complete(False)
        experimental=complete(True)
        windows=experimental['checkpoint_batch_position_intervals']
        modes=experimental['checkpoint_mode_intervals']
        windows[2]['later_tick_steps']=24
        windows[2]['first_tick_steps']=24
        modes[2]['single_tick_render_steps']=102
        result=ab.compare_batch_exposure(baseline,experimental)
        self.assertFalse(result['per_150tick_batch_exposure_matched'])
        self.assertIsNone(result['matched_exposure_later_skip_window_deltas'])
        self.assertIsNone(result['matched_exposure_later_skip_windows_improved'])
        self.assertIsNone(result['matched_exposure_later_skip_windows_worsened'])
        self.assertIsNone(result['matched_exposure_later_skip_directions_mixed'])
        self.assertIsNone(result['matched_exposure_later_skip_count_delta'])

    def test_baseline_cannot_claim_unexplained_poll(self):
        s=complete(False,0)
        for field in ('guest_mid_batch_extra_poll_calls',
                      'guest_mid_batch_extra_poll_released_pages'):
            bad=copy.deepcopy(s)
            bad[field]=1
            self.write(self.a,bad)
            with self.assertRaises(ValueError):
                ab.compare(self.a,self.b)

    def test_cli_fail_closed_with_status_and_nonzero_exit(self):
        self.write(self.b,complete(False,1))
        rc=ab.main(['--baseline',str(self.a),
                    '--experimental',str(self.b)])
        self.assertEqual(rc,1)


if __name__=='__main__':
    unittest.main()
