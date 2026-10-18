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


def repartition_one_batch_frame_as_two_singles(report,window=0):
    """Make a coherent coarse exposure mismatch for helper-only tests.

    One two-tick batched frame becomes two single-tick frames. Keep all
    independent per-window and 900-tick step/frame-count ledgers aligned.
    The result is not an authenticated NeXium guest execution.
    """
    position=report['checkpoint_batch_position_intervals'][window]
    mode=report['checkpoint_mode_intervals'][window]
    assert position['first_tick_steps']>1
    assert position['later_tick_steps']>1
    position['first_tick_steps']-=1
    position['later_tick_steps']-=1
    mode['single_tick_render_steps']+=2
    mode['batched_render_steps']-=2
    mode['render_frames_with_batched_steps']-=1
    report['single_tick_render_steps']+=2
    report['batched_render_steps']-=2
    report['batched_first_tick_steps']-=1
    report['batched_later_tick_steps']-=1
    report['render_frames_with_batched_steps']-=1
    return report


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

    def test_repartitioned_fixture_is_valid_for_exposure_helper(self):
        candidate=repartition_one_batch_frame_as_two_singles(
            complete(True,1),window=3)
        profile=ab.exposure_profile(candidate)
        self.assertEqual(len(profile),6)
        self.assertEqual(profile[3]['single_ticks'],102)
        self.assertEqual(profile[3]['first_batch_ticks'],24)
        self.assertEqual(profile[3]['later_batch_ticks'],24)
        self.assertEqual(
            sum(w['single_ticks']+w['first_batch_ticks']+
                w['later_batch_ticks'] for w in profile),900)
        self.assertEqual(candidate['single_tick_render_steps'],602)
        self.assertEqual(candidate['batched_render_steps'],298)
        self.assertEqual(candidate['render_frames_with_batched_steps'],149)

    def test_repartition_changes_exposure_without_faking_releases(self):
        baseline=complete(False)
        candidate=repartition_one_batch_frame_as_two_singles(complete(True))
        profile=ab.compare_batch_exposure(baseline,candidate)
        self.assertFalse(profile['per_150tick_batch_exposure_matched'])
        self.assertIsNone(profile['matched_exposure_later_skip_count_delta'])
        self.assertIsNone(profile['matched_exposure_later_ack_count_delta'])
        self.assertIsNone(
            profile['matched_exposure_and_returns_later_skip_count_delta'])
        self.assertEqual(candidate['batched_later_released_pages'],30)
        self.assertFalse(profile['exact_frame_pacing_matched'])

    def test_unmatched_catchup_exposure_suppresses_skip_improvement(self):
        valid=complete(True,1)
        # A pure exposure diagnostic accepts a different legal render
        # partition; deep report verification happens before it is used.
        repartition_one_batch_frame_as_two_singles(valid)
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
        windows[0]['first_tick_skips']-=2
        windows[1]['later_tick_skips']-=2
        windows[1]['first_tick_skips']+=2
        # Keep per-window batch skips and global position totals aligned.
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
        repartition_one_batch_frame_as_two_singles(experimental,window=2)
        result=ab.compare_batch_exposure(baseline,experimental)
        self.assertFalse(result['per_150tick_batch_exposure_matched'])
        self.assertIsNone(result['matched_exposure_later_skip_window_deltas'])
        self.assertIsNone(result['matched_exposure_later_skip_windows_improved'])
        self.assertIsNone(result['matched_exposure_later_skip_windows_worsened'])
        self.assertIsNone(result['matched_exposure_later_skip_directions_mixed'])
        self.assertIsNone(result['matched_exposure_later_skip_count_delta'])

    def test_matched_exposure_reports_all_six_page_return_windows(self):
        result=ab.compare(self.a,self.b)
        windows=result['matched_exposure_later_ack_window_deltas']
        self.assertEqual(len(windows),6)
        self.assertEqual(
            [w['extra_minus_baseline_later_page_returns'] for w in windows],
            [0]*6)
        self.assertEqual(result['matched_exposure_later_ack_count_delta'],0)
        self.assertEqual(result['matched_exposure_later_ack_windows_increased'],0)
        self.assertEqual(result['matched_exposure_later_ack_windows_decreased'],0)
        self.assertFalse(result['matched_exposure_later_ack_directions_mixed'])
        self.assertFalse(result['causal_audio_improvement_verified'])

    def test_page_return_cross_window_cancellation_is_visible(self):
        baseline=complete(False)
        experimental=complete(True)
        windows=experimental['checkpoint_release_position_intervals']
        windows[0]['batched_later_released_pages']+=2
        windows[1]['batched_later_released_pages']-=2
        # Test descriptive arithmetic separately; this fixture is not
        # asserted to be a valid complete guest timing ledger.
        result=ab.compare_batch_exposure(baseline,experimental)
        self.assertTrue(result['per_150tick_batch_exposure_matched'])
        self.assertEqual(result['matched_exposure_later_ack_count_delta'],0)
        self.assertEqual(
            [w['extra_minus_baseline_later_page_returns']
             for w in result['matched_exposure_later_ack_window_deltas']],
            [2,-2,0,0,0,0])
        self.assertEqual(result['matched_exposure_later_ack_windows_increased'],1)
        self.assertEqual(result['matched_exposure_later_ack_windows_decreased'],1)
        self.assertTrue(result['matched_exposure_later_ack_directions_mixed'])
        self.assertFalse(result['exact_frame_pacing_matched'])

    def test_mismatched_exposure_nulls_all_ack_direction_claims(self):
        baseline=complete(False)
        experimental=complete(True)
        repartition_one_batch_frame_as_two_singles(experimental)
        result=ab.compare_batch_exposure(baseline,experimental)
        self.assertFalse(result['per_150tick_batch_exposure_matched'])
        self.assertIsNone(result['matched_exposure_later_ack_count_delta'])
        self.assertIsNone(result['matched_exposure_later_ack_window_deltas'])
        self.assertIsNone(result['matched_exposure_later_ack_windows_increased'])
        self.assertIsNone(result['matched_exposure_later_ack_windows_decreased'])
        self.assertIsNone(result['matched_exposure_later_ack_directions_mixed'])

    def test_exposure_helper_rejects_bad_page_return_window_ledgers(self):
        for kind in ('boolean','negative','total','start','missing'):
            with self.subTest(kind=kind):
                report=complete(False)
                windows=report['checkpoint_release_position_intervals']
                if kind=='boolean':
                    windows[0]['batched_later_released_pages']=True
                elif kind=='negative':
                    windows[0]['batched_later_released_pages']=-1
                elif kind=='total':
                    windows[0]['batched_later_released_pages']=6
                elif kind=='start':
                    windows[0]['tick_start']=1
                else:
                    windows.pop()
                with self.assertRaises(ValueError):
                    ab.exposure_profile(report)

    def test_matched_return_schedule_preserves_only_descriptive_skip_delta(self):
        result=ab.compare(self.a,self.b)
        self.assertTrue(result['per_150tick_batch_exposure_matched'])
        self.assertTrue(result['matched_exposure_later_return_counts_matched'])
        self.assertFalse(
            result['matched_exposure_return_shift_confounds_skip_comparison'])
        self.assertEqual(
            result['matched_exposure_and_returns_later_skip_count_delta'],-6)
        self.assertEqual(len(
            result['matched_exposure_and_returns_later_skip_window_deltas']),6)
        self.assertFalse(result['exact_frame_pacing_matched'])
        self.assertFalse(result['causal_audio_improvement_verified'])

    def test_reallocated_acks_hide_behind_unchanged_total_and_exposure(self):
        baseline=complete(False)
        experimental=complete(True,1)
        windows=experimental['checkpoint_release_position_intervals']
        windows[0]['batched_later_released_pages']+=2
        windows[1]['batched_later_released_pages']-=2
        profile=ab.compare_batch_exposure(baseline,experimental)
        self.assertTrue(profile['per_150tick_batch_exposure_matched'])
        self.assertEqual(profile['matched_exposure_later_ack_count_delta'],0)
        self.assertEqual(profile['matched_exposure_later_skip_count_delta'],-6)
        self.assertFalse(profile['matched_exposure_later_return_counts_matched'])
        self.assertTrue(
            profile['matched_exposure_return_shift_confounds_skip_comparison'])
        self.assertIsNone(
            profile['matched_exposure_and_returns_later_skip_count_delta'])
        self.assertIsNone(
            profile['matched_exposure_and_returns_later_skip_window_deltas'])

    def test_exposure_drift_cannot_validate_page_return_schedule(self):
        baseline=complete(False)
        experimental=complete(True)
        repartition_one_batch_frame_as_two_singles(experimental)
        profile=ab.compare_batch_exposure(baseline,experimental)
        self.assertFalse(profile['per_150tick_batch_exposure_matched'])
        self.assertIsNone(profile['matched_exposure_later_return_counts_matched'])
        self.assertIsNone(
            profile['matched_exposure_return_shift_confounds_skip_comparison'])
        self.assertIsNone(
            profile['matched_exposure_and_returns_later_skip_count_delta'])
        self.assertIsNone(
            profile['matched_exposure_and_returns_later_skip_window_deltas'])

    def test_one_extra_page_return_also_nulls_strict_skip_delta(self):
        baseline=complete(False)
        experimental=complete(True,1)
        experimental['checkpoint_release_position_intervals'][4][
            'batched_later_released_pages']+=1
        experimental['batched_later_released_pages']+=1
        # This is a focused arithmetic helper test, not a full guest ledger.
        profile=ab.compare_batch_exposure(baseline,experimental)
        self.assertTrue(profile['per_150tick_batch_exposure_matched'])
        self.assertEqual(profile['matched_exposure_later_ack_count_delta'],1)
        self.assertFalse(profile['matched_exposure_later_return_counts_matched'])
        self.assertIsNone(
            profile['matched_exposure_and_returns_later_skip_count_delta'])

    def test_all_three_release_positions_match_in_normal_fixture(self):
        report=ab.compare(self.a,self.b)
        self.assertTrue(report['matched_exposure_later_return_counts_matched'])
        self.assertTrue(
            report['matched_exposure_all_position_return_counts_matched'])
        self.assertFalse(
            report['matched_exposure_any_position_return_shift_confounds_skip_comparison'])
        self.assertEqual(
            report['matched_exposure_and_returns_later_skip_count_delta'],-6)
        self.assertEqual(len(report['matched_exposure_return_position_window_deltas']),6)
        self.assertFalse(report['causal_audio_improvement_verified'])

    def test_first_vs_single_returns_can_confuse_equal_later_returns(self):
        baseline=complete(False)
        experimental=complete(True,1)
        releases=experimental['checkpoint_release_position_intervals'][0]
        releases['single_frame_released_pages']-=1
        releases['batched_first_released_pages']+=1
        experimental['single_frame_released_pages']-=1
        experimental['batched_first_released_pages']+=1
        report=ab.compare_batch_exposure(baseline,experimental)
        self.assertTrue(report['per_150tick_batch_exposure_matched'])
        self.assertTrue(report['matched_exposure_later_return_counts_matched'])
        self.assertFalse(report['matched_exposure_all_position_return_counts_matched'])
        self.assertFalse(
            report['matched_exposure_return_shift_confounds_skip_comparison'])
        self.assertTrue(
            report['matched_exposure_any_position_return_shift_confounds_skip_comparison'])
        self.assertEqual(
            report['matched_exposure_return_position_window_deltas'][0],{
                'tick_start':0,'tick_end':150,
                'extra_minus_baseline_single_frame_page_returns':-1,
                'extra_minus_baseline_first_batch_page_returns':1,
                'extra_minus_baseline_later_batch_page_returns':0,
            })
        self.assertIsNone(
            report['matched_exposure_and_returns_later_skip_count_delta'])
        self.assertIsNone(
            report['matched_exposure_and_returns_later_skip_window_deltas'])

    def test_equal_global_first_returns_can_hide_window_reallocation(self):
        baseline=complete(False)
        experimental=complete(True,1)
        windows=experimental['checkpoint_release_position_intervals']
        windows[0]['batched_first_released_pages']-=1
        windows[1]['batched_first_released_pages']+=1
        report=ab.compare_batch_exposure(baseline,experimental)
        self.assertTrue(report['matched_exposure_later_return_counts_matched'])
        self.assertFalse(report['matched_exposure_all_position_return_counts_matched'])
        self.assertEqual(report['matched_exposure_later_ack_count_delta'],0)
        self.assertIsNone(
            report['matched_exposure_and_returns_later_skip_count_delta'])
        self.assertEqual(
            [w['extra_minus_baseline_first_batch_page_returns']
             for w in report['matched_exposure_return_position_window_deltas']],
            [-1,1,0,0,0,0])

    def test_first_and_single_page_return_ledgers_fail_closed(self):
        for position,total in (
                ('single_frame_released_pages','single_frame_released_pages'),
                ('batched_first_released_pages','batched_first_released_pages')):
            for kind in ('window_total','global_total','boolean','negative'):
                with self.subTest(position=position,kind=kind):
                    report=complete(False)
                    if kind=='window_total':
                        report['checkpoint_release_position_intervals'][0][position]+=1
                    elif kind=='global_total':
                        report[total]+=1
                    elif kind=='boolean':
                        report['checkpoint_release_position_intervals'][0][position]=True
                    else:
                        report['checkpoint_release_position_intervals'][0][position]=-1
                    with self.assertRaises(ValueError):
                        ab.exposure_profile(report)

    def test_exposure_drift_nulls_return_position_matching(self):
        baseline=complete(False)
        experimental=complete(True)
        repartition_one_batch_frame_as_two_singles(experimental)
        report=ab.compare_batch_exposure(baseline,experimental)
        self.assertFalse(report['per_150tick_batch_exposure_matched'])
        self.assertIsNone(report['matched_exposure_return_position_window_deltas'])
        self.assertIsNone(
            report['matched_exposure_all_position_return_counts_matched'])
        self.assertIsNone(
            report['matched_exposure_any_position_return_shift_confounds_skip_comparison'])
        self.assertIsNone(
            report['matched_exposure_and_returns_later_skip_count_delta'])

    def test_exposure_helper_rejects_misaligned_mode_window(self):
        for change in ('shift_start','short_end','boolean_start'):
            with self.subTest(change=change):
                report=complete(False)
                mode=report['checkpoint_mode_intervals'][0]
                if change=='shift_start':
                    mode['tick_start']=1
                elif change=='short_end':
                    mode['tick_end']=149
                else:
                    mode['tick_start']=False
                with self.assertRaises(ValueError):
                    ab.exposure_profile(report)

    def test_exposure_helper_rejects_corrupted_mode_batch_totals(self):
        cases=(
            ('batched_render_steps',49),
            ('skips_in_batched_render_frames',29),
            ('skips_in_single_tick_render_frames',101),
            ('batched_render_steps',True),
            ('skips_in_batched_render_frames',-1),
        )
        for field,bad in cases:
            with self.subTest(field=field,bad=bad):
                report=complete(False)
                report['checkpoint_mode_intervals'][0][field]=bad
                with self.assertRaises(ValueError):
                    ab.exposure_profile(report)

    def test_all_source_window_boundaries_are_canonical_in_helper(self):
        for source in (
                'checkpoint_batch_position_intervals',
                'checkpoint_mode_intervals',
                'checkpoint_release_position_intervals'):
            with self.subTest(source=source):
                report=complete(False)
                report[source][2]['tick_end']=450.0
                with self.assertRaises(ValueError):
                    ab.exposure_profile(report)

    def test_balanced_original_mode_ledgers_remain_accepted(self):
        report=complete(True,1)
        profile=ab.exposure_profile(report)
        self.assertEqual(len(profile),6)
        self.assertEqual(
            sum(w['single_ticks']+w['first_batch_ticks']+
                w['later_batch_ticks'] for w in profile),900)
        self.assertEqual(
            sum(w['first_batch_skips']+w['later_batch_skips']
                for w in profile),174)
        self.assertEqual(sum(w['later_batch_page_returns']
                             for w in profile),30)

    def test_exposure_helper_reconciles_all_global_position_totals(self):
        sample=complete(True,1)
        output=ab.exposure_profile(sample)
        for local,global_name in (
                ('single_ticks','single_tick_render_steps'),
                ('first_batch_ticks','batched_first_tick_steps'),
                ('later_batch_ticks','batched_later_tick_steps'),
                ('single_skips','skips_in_single_tick_render_frames'),
                ('first_batch_skips','batched_first_tick_skips'),
                ('later_batch_skips','batched_later_tick_skips')):
            with self.subTest(local=local):
                self.assertEqual(
                    sum(window[local] for window in output),
                    sample[global_name])

    def test_global_audio_exposure_counters_cannot_disagree_with_windows(self):
        fields=(
            'single_tick_render_steps','batched_first_tick_steps',
            'batched_later_tick_steps','skips_in_single_tick_render_frames',
            'batched_first_tick_skips','batched_later_tick_skips',
            'batched_render_steps','simulation_ticks',
            'skips_in_batched_render_frames',
        )
        for field in fields:
            with self.subTest(field=field):
                report=complete(False)
                report[field]+=1
                with self.assertRaises(ValueError):
                    ab.exposure_profile(report)

    def test_local_frame_repartition_requires_global_position_agreement(self):
        report=complete(False)
        steps=report['checkpoint_batch_position_intervals'][0]
        steps['first_tick_steps']+=1
        steps['later_tick_steps']-=1
        # Total 150-tick exposure is unchanged, as is its mode partition.
        # Global first/later position totals must still catch the drift.
        with self.assertRaises(ValueError):
            ab.exposure_profile(report)

    def test_reallocated_skips_must_match_global_first_later_counters(self):
        report=complete(False)
        skips=report['checkpoint_batch_position_intervals'][0]
        skips['first_tick_skips']+=1
        skips['later_tick_skips']-=1
        # Total batched skips are unchanged; the position-specific
        # global witnesses must not permit this partial report.
        with self.assertRaises(ValueError):
            ab.exposure_profile(report)

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
