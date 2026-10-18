"""Synthetic, ROM-free checks of cross-run audout summary validation."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from tools import compare_nexium_audio_stress_runs as check


def fixture(variation=0):
    windows = []
    for i in range(6):
        ss = 20 + variation
        bs = 30 - variation
        windows.append({
            'tick_start': i*150, 'tick_end': (i+1)*150,
            'single_tick_render_steps': 100,
            'batched_render_steps': 50,
            'skips_in_single_tick_render_frames': ss,
            'skips_in_batched_render_frames': bs,
            'render_frames_with_batched_steps': 25,
            'full_queue_skips': 50,
            'single_skip_percent_rounded': ss,
            'batched_skip_percent_rounded': 2*bs,
        })
    return {
        'schema':check.SCHEMA,
        'status':check.STATUS,
        'native_guest_hid_bound':True,
        'queued_buffers_never_above_two':True,
        'catchup_causality_verified':False,
        'host_wall_clock_real_time_verified':False,
        'sound_device_audible_verified':False,
        'physical_switch_audio_verified':False,
        'audio_latency_verified':False,
        'original_arcade_audio_verified':False,
        'simulation_ticks':900, 'pcm_generated_ticks':900, 'checkpoints':7,
        'audout_blocks_submitted':600, 'audout_blocks_released':600,
        'audout_blocks_skipped':300, 'full_queue_skips':300,
        'inactive_backend_skips':0,'unexpected_slot_skips':0,
        'single_tick_render_steps':600, 'batched_render_steps':300,
        'skips_in_single_tick_render_frames':6*(20+variation),
        'skips_in_batched_render_frames':6*(30-variation),
        'render_frames_with_batched_steps':150,
        'largest_scheduled_tick_batch':2, 'peak_observed_pending':1,
        'audio_errors_added':0,
        'windows_with_both_render_modes':6,
        'windows_with_higher_batched_skip_rate':6,
        'single_skip_percent_rounded':20+variation,
        'batched_skip_percent_rounded':60-2*variation,
        'checkpoint_skipped_deltas':[50]*6,
        'checkpoint_mode_intervals':windows,
    }


def with_release_probe(report, recovery=25):
    """Add consistent, per-window, synthetic guest release observations."""
    report=copy.deepcopy(report)
    windows=[]
    for i,w in enumerate(report['checkpoint_mode_intervals']):
        drops=w['full_queue_skips']
        windows.append({
            'tick_start':i*150,
            'tick_end':(i+1)*150,
            'full_before_poll':drops+recovery,
            'recovered_before_admission':recovery,
            'still_full_after_poll':drops,
        })
    report.update({
        'pre_poll_capacity_probe_present':True,
        'full_before_release_poll_ticks':sum(
            w['full_before_poll'] for w in windows),
        'full_recovered_before_admission_ticks':6*recovery,
        'checkpoint_release_poll_intervals':windows,
    })
    return report



def with_batch_position(report):
    """Synthetically partition 50 batch steps per window, never raw PCM."""
    report=copy.deepcopy(report)
    windows=[]
    for i,w in enumerate(report['checkpoint_mode_intervals']):
        steps=w['batched_render_steps']
        if steps!=50:
            raise ValueError('position fixture only supports 50 batch steps')
        first_skips=10
        later_skips=w['skips_in_batched_render_frames']-first_skips
        windows.append({
            'tick_start':150*i,'tick_end':150*(i+1),
            'first_tick_steps':25,'later_tick_steps':25,
            'first_tick_skips':first_skips,
            'later_tick_skips':later_skips,
            'first_skip_percent_rounded':40,
            'later_skip_percent_rounded':check.rounded(later_skips,25),
        })
    report.update({
        'batch_tick_position_probe_present':True,
        'batched_first_tick_steps':150,
        'batched_later_tick_steps':150,
        'batched_first_tick_skips':60,
        'batched_later_tick_skips':sum(
            w['later_tick_skips'] for w in windows),
        'checkpoint_batch_position_intervals':windows,
    })
    return report


def with_batch_position_poll(report):
    """Stage 146 nested release-poll counters, exactly reconciled."""
    report=copy.deepcopy(report)
    windows=[]
    for i,(mode,pos,poll) in enumerate(zip(
            report['checkpoint_mode_intervals'],
            report['checkpoint_batch_position_intervals'],
            report['checkpoint_release_poll_intervals'])):
        first_skips=pos['first_tick_skips']
        later_skips=pos['later_tick_skips']
        first_full=first_skips+4
        first_recovered=4
        later_full=later_skips+1
        later_recovered=1
        single_full=poll['full_before_poll']-first_full-later_full
        single_recovered=poll['recovered_before_admission']-5
        assert single_full-single_recovered==mode[
            'skips_in_single_tick_render_frames']
        windows.append({
            'tick_start':i*150,'tick_end':(i+1)*150,
            'first_full_before_poll':first_full,
            'first_recovered_after_poll':first_recovered,
            'later_full_before_poll':later_full,
            'later_recovered_after_poll':later_recovered,
            'single_full_before_poll':single_full,
            'single_recovered_after_poll':single_recovered,
        })
    report.update({
        'batch_position_poll_probe_present':True,
        'batched_first_full_before_poll':sum(
            w['first_full_before_poll'] for w in windows),
        'batched_first_recovered_after_poll':24,
        'batched_later_full_before_poll':sum(
            w['later_full_before_poll'] for w in windows),
        'batched_later_recovered_after_poll':6,
        'checkpoint_batch_position_poll_intervals':windows,
    })
    return report



def with_released_page_positions(report):
    """Stage 151 complete ROM-free fixture with fixed, valid 900-tick data."""
    report=copy.deepcopy(report)
    windows=[]
    for i in range(6):
        windows.append({
            'tick_start':150*i,
            'tick_end':150*(i+1),
            'single_frame_released_pages':85,
            'batched_first_released_pages':10,
            'batched_later_released_pages':5,
        })
    report.update({
        'release_tick_position_probe_present':True,
        'single_frame_released_pages':510,
        'batched_first_released_pages':60,
        'batched_later_released_pages':30,
        'checkpoint_release_position_intervals':windows,
    })
    return report



class MultiRunAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='synthetic-cross-run-')
        self.root = Path(self.temp.name)
        self.one = self.root / 'first.json'
        self.two = self.root / 'second.json'
        self.save(self.one, fixture())
        self.save(self.two, fixture(1))

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def save(path, data):
        path.write_text(json.dumps(data, sort_keys=True)+'\n', encoding='ascii')

    def report(self, which=0):
        return json.loads((self.one if which==0 else self.two).read_text())

    def mutate(self, field, value, index=None):
        sample = self.report()
        if index is None:
            sample[field] = value
        else:
            sample['checkpoint_mode_intervals'][index][field] = value
        self.save(self.one, sample)
        with self.assertRaises(ValueError):
            check.compare([self.one,self.two])

    def test_two_valid_comparable_synthetic_reports(self):
        result = check.compare([self.one,self.two])
        self.assertEqual(result['reports_compared'],2)
        self.assertEqual(result['total_guest_simulation_ticks'],1800)
        self.assertEqual(result['combined_full_queue_skips'],600)
        self.assertEqual(result['single_tick_render_steps'],1200)
        self.assertEqual(result['batched_render_steps'],600)
        self.assertEqual(result['single_tick_render_skips'],246)
        self.assertEqual(result['batched_render_skips'],354)
        self.assertEqual(result['single_skip_percent_rounded'],21)
        self.assertEqual(result['batched_skip_percent_rounded'],59)
        self.assertEqual(result['eligible_150tick_mode_comparisons'],12)
        self.assertEqual(result['windows_with_higher_batched_skip_fraction'],12)
        self.assertEqual(result['runs_with_batched_higher_in_all_six_windows'],2)
        self.assertFalse(result['independent_guest_execution_authenticated'])
        self.assertFalse(result['catchup_causality_verified'])

    def test_all_extended_reports_produce_only_complete_pool(self):
        self.save(self.one,with_release_probe(fixture(),25))
        self.save(self.two,with_release_probe(fixture(1),30))
        result=check.compare([self.one,self.two])
        self.assertTrue(result['all_reports_have_release_poll_probe'])
        self.assertEqual(result['reports_with_release_poll_probe'],2)
        self.assertEqual(result['pooled_full_before_release_poll_ticks'],930)
        self.assertEqual(result['pooled_recovered_before_admission_ticks'],330)
        self.assertEqual(result['pooled_still_full_after_poll_ticks'],600)
        self.assertEqual(result['release_poll_recovery_percent_rounded'],35)
        self.assertFalse(result['catchup_causality_verified'])
        self.assertFalse(result['independent_guest_execution_authenticated'])

    def test_mixed_legacy_extended_does_not_publish_partial_recovery(self):
        self.save(self.one,with_release_probe(fixture(),25))
        result=check.compare([self.one,self.two])
        self.assertEqual(result['reports_with_release_poll_probe'],1)
        self.assertFalse(result['all_reports_have_release_poll_probe'])
        self.assertIsNone(result['pooled_full_before_release_poll_ticks'])
        self.assertIsNone(result['pooled_recovered_before_admission_ticks'])
        self.assertIsNone(result['pooled_still_full_after_poll_ticks'])
        self.assertIsNone(result['release_poll_recovery_percent_rounded'])
        self.assertEqual(result['combined_full_queue_skips'],600)

    def test_missing_probe_is_not_falsely_reported_as_zero_recovery(self):
        report=check.compare([self.one,self.two])
        self.assertEqual(report['reports_with_release_poll_probe'],0)
        self.assertIsNone(report['release_poll_recovery_percent_rounded'])
        self.save(self.one,dict(fixture(),
            pre_poll_capacity_probe_present=False,
            full_before_release_poll_ticks=None,
            full_recovered_before_admission_ticks=None,
            checkpoint_release_poll_intervals=None))
        report=check.compare([self.one,self.two])
        self.assertEqual(report['reports_with_release_poll_probe'],0)
        self.assertIsNone(report['pooled_full_before_release_poll_ticks'])

    def test_reject_partial_false_or_nonboolean_probe_claims(self):
        sample=with_release_probe(fixture())
        for key in check.POLL_PROBE_KEYS:
            with self.subTest(key=key):
                r=copy.deepcopy(sample)
                del r[key]
                self.save(self.one,r)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])
        for flag in (1,0,None,'true'):
            with self.subTest(flag=flag):
                r=copy.deepcopy(sample)
                r['pre_poll_capacity_probe_present']=flag
                self.save(self.one,r)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])
        r=copy.deepcopy(sample)
        r.update(pre_poll_capacity_probe_present=False)
        self.save(self.one,r)
        with self.assertRaises(ValueError):
            check.compare([self.one,self.two])

    def test_reject_corrupted_global_release_poll_counts(self):
        sample=with_release_probe(fixture())
        for name,bad in (
                ('full_before_release_poll_ticks',449),
                ('full_before_release_poll_ticks',True),
                ('full_before_release_poll_ticks',901),
                ('full_recovered_before_admission_ticks',151),
                ('full_recovered_before_admission_ticks',False),
                ('full_recovered_before_admission_ticks',500)):
            with self.subTest(name=name,bad=bad):
                r=copy.deepcopy(sample)
                r[name]=bad
                self.save(self.one,r)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])

    def test_release_windows_cannot_hide_a_forged_distribution(self):
        sample=with_release_probe(fixture())
        for i,key,bad in (
                (0,'tick_start',1),
                (1,'tick_end',301),
                (2,'full_before_poll',74),
                (3,'recovered_before_admission',24),
                (4,'still_full_after_poll',49),
                (5,'full_before_poll',151),
                (0,'recovered_before_admission',False)):
            with self.subTest(i=i,key=key,bad=bad):
                r=copy.deepcopy(sample)
                r['checkpoint_release_poll_intervals'][i][key]=bad
                self.save(self.one,r)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])
        for mutator in ('missing','extra','short'):
            with self.subTest(mutator=mutator):
                r=copy.deepcopy(sample)
                ws=r['checkpoint_release_poll_intervals']
                if mutator=='missing':
                    del ws[0]['full_before_poll']
                elif mutator=='extra':
                    ws[0]['invented_probe']=1
                else:
                    ws.pop()
                self.save(self.one,r)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])

    def test_zero_occupancy_probe_has_null_recovery_not_zero_percent(self):
        sample=fixture()
        for window in sample['checkpoint_mode_intervals']:
            window.update({
                'skips_in_single_tick_render_frames':0,
                'skips_in_batched_render_frames':0,
                'full_queue_skips':0,
                'single_skip_percent_rounded':0,
                'batched_skip_percent_rounded':0,
            })
        sample.update({
            'audout_blocks_submitted':900,
            'audout_blocks_released':900,
            'audout_blocks_skipped':0,
            'full_queue_skips':0,
            'skips_in_single_tick_render_frames':0,
            'skips_in_batched_render_frames':0,
            'single_skip_percent_rounded':0,
            'batched_skip_percent_rounded':0,
            'checkpoint_skipped_deltas':[0]*6,
            'windows_with_higher_batched_skip_rate':0,
        })
        self.save(self.one,with_release_probe(sample,0))
        self.save(self.two,with_release_probe(sample,1))
        result=check.compare([self.one,self.two])
        self.assertEqual(result['pooled_full_before_release_poll_ticks'],6)
        self.assertEqual(result['release_poll_recovery_percent_rounded'],100)
        self.assertEqual(result['combined_full_queue_skips'],0)
        self.assertFalse(result['catchup_causality_verified'])


    def test_full_stage146_comparison_reconciles_nested_audio_witnesses(self):
        one=with_batch_position_poll(with_batch_position(
            with_release_probe(fixture(),25)))
        two=with_batch_position_poll(with_batch_position(
            with_release_probe(fixture(1),30)))
        self.save(self.one,one)
        self.save(self.two,two)
        result=check.compare([self.one,self.two])
        self.assertEqual(result['reports_with_batch_position_probe'],2)
        self.assertEqual(result['reports_with_batch_position_poll_probe'],2)
        self.assertEqual(result['pooled_batched_first_tick_steps'],300)
        self.assertEqual(result['pooled_batched_later_tick_steps'],300)
        self.assertEqual(result['pooled_batched_first_tick_skips'],120)
        self.assertEqual(result['pooled_batched_later_tick_skips'],234)
        self.assertEqual(result['batched_first_skip_percent_rounded'],40)
        self.assertEqual(result['batched_later_skip_percent_rounded'],78)
        self.assertEqual(result['pooled_batched_first_full_before_poll'],168)
        self.assertEqual(result['pooled_batched_first_recovered_after_poll'],48)
        self.assertEqual(result['pooled_batched_later_full_before_poll'],246)
        self.assertEqual(result['pooled_batched_later_recovered_after_poll'],12)
        self.assertFalse(result['catchup_causality_verified'])

    def test_stage145_without_position_poll_keeps_missing_data_null(self):
        one=with_batch_position(with_release_probe(fixture(),25))
        self.save(self.one,one)
        self.save(self.two,with_batch_position(
            with_release_probe(fixture(1),30)))
        result=check.compare([self.one,self.two])
        self.assertTrue(result['all_reports_have_batch_position_probe'])
        self.assertEqual(result['reports_with_batch_position_poll_probe'],0)
        self.assertIsNone(result['pooled_batched_first_full_before_poll'])
        self.assertIsNone(result['pooled_batched_later_recovered_after_poll'])

    def test_mixed_stage145_stage146_suppresses_partial_poll_totals(self):
        sample=with_batch_position(with_release_probe(fixture(),25))
        self.save(self.one,with_batch_position_poll(sample))
        self.save(self.two,with_batch_position(
            with_release_probe(fixture(1),30)))
        result=check.compare([self.one,self.two])
        self.assertEqual(result['reports_with_batch_position_probe'],2)
        self.assertEqual(result['reports_with_batch_position_poll_probe'],1)
        self.assertIsNone(result['pooled_batched_later_full_before_poll'])

    def test_mixed_legacy_and_stage146_suppresses_position_rates(self):
        sample=with_batch_position_poll(with_batch_position(
            with_release_probe(fixture(),25)))
        self.save(self.one,sample)
        result=check.compare([self.one,self.two])
        self.assertEqual(result['reports_with_batch_position_probe'],1)
        self.assertIsNone(result['batched_first_skip_percent_rounded'])
        self.assertIsNone(result['pooled_batched_first_tick_skips'])

    def test_position_partial_nonboolean_and_fake_presence_rejected(self):
        sample=with_batch_position_poll(with_batch_position(
            with_release_probe(fixture())))
        for fields,flag in (
                (check.POSITION_FIELDS,'batch_tick_position_probe_present'),
                (check.POSITION_POLL_FIELDS,'batch_position_poll_probe_present')):
            for key in fields:
                with self.subTest(missing=key):
                    r=copy.deepcopy(sample)
                    del r[key]
                    self.save(self.one,r)
                    with self.assertRaises(ValueError):
                        check.compare([self.one,self.two])
            for value in (0,1,None,'true'):
                with self.subTest(flag=flag,value=value):
                    r=copy.deepcopy(sample)
                    r[flag]=value
                    self.save(self.one,r)
                    with self.assertRaises(ValueError):
                        check.compare([self.one,self.two])
        sample['batch_tick_position_probe_present']=False
        self.save(self.one,sample)
        with self.assertRaises(ValueError):
            check.compare([self.one,self.two])

    def test_stage146_forged_windows_are_rejected_with_plausible_totals(self):
        sample=with_batch_position_poll(with_batch_position(
            with_release_probe(fixture())))
        for key,bad,which in (
                ('first_tick_steps',24,'checkpoint_batch_position_intervals'),
                ('later_tick_skips',19,'checkpoint_batch_position_intervals'),
                ('first_skip_percent_rounded',39,
                 'checkpoint_batch_position_intervals'),
                ('first_full_before_poll',13,
                 'checkpoint_batch_position_poll_intervals'),
                ('single_recovered_after_poll',19,
                 'checkpoint_batch_position_poll_intervals'),
                ('later_full_before_poll',True,
                 'checkpoint_batch_position_poll_intervals'),
                ('tick_end',149,'checkpoint_batch_position_poll_intervals')):
            with self.subTest(key=key,bad=bad):
                r=copy.deepcopy(sample)
                r[which][0][key]=bad
                self.save(self.one,r)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])

    def test_position_poll_cannot_exist_without_stage143_or_stage145(self):
        sample=with_batch_position_poll(with_batch_position(
            with_release_probe(fixture())))
        for fields in (check.POLL_PROBE_KEYS,check.POSITION_FIELDS):
            r=copy.deepcopy(sample)
            for name in fields:
                del r[name]
            self.save(self.one,r)
            with self.assertRaises(ValueError):
                check.compare([self.one,self.two])


    def test_complete_stage151_probes_pool_only_confirmed_pages(self):
        one=with_released_page_positions(with_batch_position_poll(
            with_batch_position(with_release_probe(fixture(),25))))
        two=with_released_page_positions(with_batch_position_poll(
            with_batch_position(with_release_probe(fixture(1),30))))
        self.save(self.one,one)
        self.save(self.two,two)
        result=check.compare([self.one,self.two])
        self.assertTrue(result['all_reports_have_release_tick_position_probe'])
        self.assertEqual(result['reports_with_release_tick_position_probe'],2)
        self.assertEqual(result['pooled_single_frame_released_pages'],1020)
        self.assertEqual(result['pooled_batched_first_released_pages'],120)
        self.assertEqual(result['pooled_batched_later_released_pages'],60)
        self.assertEqual(
            result['batched_later_release_pages_per_100_ticks_rounded'],20)
        self.assertFalse(result['independent_guest_execution_authenticated'])
        self.assertFalse(result['catchup_causality_verified'])

    def test_mixed_stage146_stage151_must_not_pool_partial_releases(self):
        one=with_batch_position_poll(with_batch_position(
            with_release_probe(fixture(),25)))
        self.save(self.one,with_released_page_positions(one))
        self.save(self.two,with_batch_position_poll(with_batch_position(
            with_release_probe(fixture(1),30))))
        result=check.compare([self.one,self.two])
        self.assertEqual(result['reports_with_release_tick_position_probe'],1)
        self.assertFalse(result['all_reports_have_release_tick_position_probe'])
        self.assertIsNone(result['pooled_batched_later_released_pages'])
        self.assertIsNone(
            result['batched_later_release_pages_per_100_ticks_rounded'])
        self.assertEqual(result['reports_with_batch_position_poll_probe'],2)

    def test_old_reports_report_absence_not_fabricated_zero_ack(self):
        result=check.compare([self.one,self.two])
        self.assertEqual(result['reports_with_release_tick_position_probe'],0)
        self.assertIsNone(result['pooled_single_frame_released_pages'])
        self.assertIsNone(result['pooled_batched_later_released_pages'])
        legacy=fixture()
        legacy.update(
            release_tick_position_probe_present=False,
            single_frame_released_pages=None,
            batched_first_released_pages=None,
            batched_later_released_pages=None,
            checkpoint_release_position_intervals=None)
        self.save(self.one,legacy)
        result=check.compare([self.one,self.two])
        self.assertEqual(result['reports_with_release_tick_position_probe'],0)
        self.assertIsNone(result['pooled_batched_first_released_pages'])

    def test_new_probe_requires_exact_fields_and_boolean_provenance(self):
        full=with_released_page_positions(with_batch_position_poll(
            with_batch_position(with_release_probe(fixture()))))
        for key in check.RELEASE_POSITION_FIELDS:
            with self.subTest(missing=key):
                bad=copy.deepcopy(full)
                del bad[key]
                self.save(self.one,bad)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])
        for claimed in (0,1,None,'true',[]):
            with self.subTest(claimed=claimed):
                bad=copy.deepcopy(full)
                bad['release_tick_position_probe_present']=claimed
                self.save(self.one,bad)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])

    def test_ack_probe_needs_stage146_poll_prerequisites(self):
        complete=with_released_page_positions(with_batch_position_poll(
            with_batch_position(with_release_probe(fixture()))))
        for keys in (check.POLL_PROBE_KEYS,
                     check.POSITION_FIELDS,check.POSITION_POLL_FIELDS):
            with self.subTest(keys=keys):
                missing=copy.deepcopy(complete)
                for key in keys:
                    del missing[key]
                self.save(self.one,missing)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])

    def test_forged_global_ack_counters_are_refused(self):
        full=with_released_page_positions(with_batch_position_poll(
            with_batch_position(with_release_probe(fixture()))))
        for name,bad in (
                ('single_frame_released_pages',511),
                ('single_frame_released_pages',True),
                ('batched_first_released_pages',59),
                ('batched_later_released_pages',0),
                ('batched_later_released_pages',2**32),
                ('batched_later_released_pages',False)):
            with self.subTest(name=name,bad=bad):
                forged=copy.deepcopy(full)
                forged[name]=bad
                self.save(self.one,forged)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])

    def test_window_counts_cannot_hide_forged_release_ack_position(self):
        full=with_released_page_positions(with_batch_position_poll(
            with_batch_position(with_release_probe(fixture()))))
        for idx,key,bad in (
                (0,'tick_start',1),
                (1,'tick_end',301),
                (2,'single_frame_released_pages',86),
                (3,'batched_first_released_pages',True),
                (4,'batched_later_released_pages',0),
                (5,'batched_later_released_pages',200)):
            with self.subTest(idx=idx,key=key):
                forged=copy.deepcopy(full)
                forged['checkpoint_release_position_intervals'][idx][key]=bad
                self.save(self.one,forged)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])
        for kind in ('missing','extra','short'):
            with self.subTest(kind=kind):
                forged=copy.deepcopy(full)
                w=forged['checkpoint_release_position_intervals']
                if kind=='missing':
                    del w[0]['single_frame_released_pages']
                elif kind=='extra':
                    w[0]['imagined_ack']=5
                else:
                    w.pop()
                self.save(self.one,forged)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])

    def test_redistributed_release_ack_window_invalid_even_if_totals_match(self):
        full=with_released_page_positions(with_batch_position_poll(
            with_batch_position(with_release_probe(fixture()))))
        first=full['checkpoint_release_position_intervals'][0]
        second=full['checkpoint_release_position_intervals'][1]
        first['batched_later_released_pages']=0
        second['batched_later_released_pages']=10
        self.save(self.one,full)
        # Total count still agrees, but interval 0 no longer has enough
        # recovered-after-poll releases to justify an ACK count of zero.
        with self.assertRaises(ValueError):
            check.compare([self.one,self.two])

    def stage151(self,variant=0,later_ack_per_window=5):
        record=with_released_page_positions(with_batch_position_poll(
            with_batch_position(with_release_probe(fixture(variant),25))))
        # Preserve exact per-window and global release totals while
        # moving ACK observations from later to single-tick steps.
        shift=5-later_ack_per_window
        if not 0<=later_ack_per_window<=5:
            raise ValueError('unsupported synthetic test delta')
        if later_ack_per_window==0:
            # Original Stage 146 fixture has one later-tick recovery per
            # window. A zero-page-return witness cannot retain that ACK.
            # Move the *same* full+recovered poll event to the first
            # batch tick, leaving first/later skip counts unchanged.
            poll_windows=record[
                'checkpoint_batch_position_poll_intervals']
            for w in poll_windows:
                w['first_full_before_poll']+=1
                w['first_recovered_after_poll']+=1
                w['later_full_before_poll']-=1
                w['later_recovered_after_poll']-=1
            record['batched_first_full_before_poll']+=6
            record['batched_first_recovered_after_poll']+=6
            record['batched_later_full_before_poll']-=6
            record['batched_later_recovered_after_poll']-=6
        record['single_frame_released_pages']+=6*shift
        record['batched_later_released_pages']-=6*shift
        for window in record['checkpoint_release_position_intervals']:
            window['single_frame_released_pages']+=shift
            window['batched_later_released_pages']-=shift
        return record

    def test_no_later_ack_is_separated_from_no_capacity_recovery(self):
        self.save(self.one,self.stage151(0,0))
        self.save(self.two,self.stage151(1,5))
        result=check.compare([self.one,self.two])
        self.assertEqual(result['eligible_later_tick_release_windows'],12)
        self.assertEqual(result['windows_with_later_ticks_and_zero_ack'],6)
        self.assertEqual(result['windows_with_later_skips_and_zero_ack'],6)
        self.assertEqual(result['windows_with_later_skips_and_nonzero_ack'],6)
        self.assertEqual(result['runs_with_later_skips_and_zero_ack_window'],1)
        self.assertEqual(result['runs_with_zero_later_page_returns'],1)
        self.assertEqual(result['pooled_batched_later_released_pages'],30)
        self.assertFalse(result['catchup_causality_verified'])

    def test_all_later_ack_windows_without_ack_are_counted(self):
        self.save(self.one,self.stage151(0,0))
        self.save(self.two,self.stage151(1,0))
        result=check.compare([self.one,self.two])
        self.assertEqual(result['eligible_later_tick_release_windows'],12)
        self.assertEqual(result['windows_with_later_ticks_and_zero_ack'],12)
        self.assertEqual(result['windows_with_later_skips_and_zero_ack'],12)
        self.assertEqual(result['windows_with_later_skips_and_nonzero_ack'],0)
        self.assertEqual(result['runs_with_zero_later_page_returns'],2)
        self.assertEqual(result['pooled_batched_later_released_pages'],0)

    def test_nonzero_later_ack_can_coexist_with_later_skips(self):
        self.save(self.one,self.stage151(0,5))
        self.save(self.two,self.stage151(1,5))
        result=check.compare([self.one,self.two])
        self.assertEqual(result['windows_with_later_skips_and_zero_ack'],0)
        self.assertEqual(result['windows_with_later_skips_and_nonzero_ack'],12)
        self.assertEqual(result['runs_with_zero_later_page_returns'],0)
        self.assertEqual(result['runs_with_later_skips_and_zero_ack_window'],0)

    def test_legacy_reports_must_not_invent_zero_later_ack_windows(self):
        self.save(self.one,self.stage151(0,0))
        report=check.compare([self.one,self.two])
        for field in (
                'eligible_later_tick_release_windows',
                'windows_with_later_ticks_and_zero_ack',
                'windows_with_later_skips_and_zero_ack',
                'windows_with_later_skips_and_nonzero_ack',
                'runs_with_later_skips_and_zero_ack_window',
                'runs_with_zero_later_page_returns'):
            self.assertIsNone(report[field],field)
        self.assertEqual(report['reports_with_release_tick_position_probe'],1)

    def test_window_skip_data_cannot_fake_a_descriptive_pattern(self):
        a=self.stage151(0,0)
        b=self.stage151(1,5)
        self.save(self.two,b)
        for tamper in ('drop','step','ack','window'):
            with self.subTest(tamper=tamper):
                forged=copy.deepcopy(a)
                if tamper=='drop':
                    forged['checkpoint_batch_position_intervals'][0][
                        'later_tick_skips']=0
                elif tamper=='step':
                    forged['checkpoint_batch_position_intervals'][0][
                        'later_tick_steps']=0
                elif tamper=='ack':
                    forged['checkpoint_release_position_intervals'][0][
                        'batched_later_released_pages']=1
                else:
                    forged['checkpoint_release_position_intervals'][0][
                        'single_frame_released_pages']=150
                self.save(self.one,forged)
                with self.assertRaises(ValueError):
                    check.compare([self.one,self.two])

    def test_real_guest_metadata_cannot_prove_extra_poll_would_fix_skips(self):
        self.save(self.one,self.stage151(0,0))
        self.save(self.two,self.stage151(1,5))
        result=check.compare([self.one,self.two])
        self.assertFalse(result['independent_guest_execution_authenticated'])
        self.assertFalse(result['catchup_causality_verified'])
        self.assertFalse(result['physical_switch_audio_verified'])
        self.assertFalse(result['original_arcade_audio_verified'])

    def test_refuse_duplicate_file_content_and_too_few_runs(self):
        for paths in ([self.one,self.one],[self.one],[self.one]*9):
            with self.subTest(length=len(paths)):
                with self.assertRaises(ValueError):
                    check.compare(paths)
        self.save(self.two, fixture())
        with self.assertRaisesRegex(ValueError,'reused identical'):
            check.compare([self.one,self.two])

    def test_window_forgery_detected_despite_valid_global_totals(self):
        self.mutate('skips_in_batched_render_frames',31,index=2)
        self.mutate('render_frames_with_batched_steps',2,index=3)
        self.mutate('full_queue_skips',49,index=4)
        self.mutate('batched_skip_percent_rounded',59,index=1)
        self.mutate('tick_start',299,index=2)

    def test_global_accounting_and_proof_flag_forgery_rejected(self):
        self.mutate('audout_blocks_skipped',299)
        self.mutate('batched_render_steps',301)
        self.mutate('windows_with_higher_batched_skip_rate',0)
        self.mutate('native_guest_hid_bound',False)
        self.mutate('catchup_causality_verified',True)
        self.mutate('audio_latency_verified',True)
        self.mutate('audout_blocks_submitted',True)

    def test_bogus_window_wins_rejected(self):
        self.mutate('windows_with_both_render_modes',5)
        self.mutate('single_skip_percent_rounded',19)

    def test_empty_batch_mode_rates_are_nullable(self):
        report = fixture()
        for w in report['checkpoint_mode_intervals']:
            w.update({
                'single_tick_render_steps':150,'batched_render_steps':0,
                'skips_in_single_tick_render_frames':50,
                'skips_in_batched_render_frames':0,
                'render_frames_with_batched_steps':0,
                'single_skip_percent_rounded':33,
                'batched_skip_percent_rounded':None,
            })
        report.update({
            'single_tick_render_steps':900,'batched_render_steps':0,
            'skips_in_single_tick_render_frames':300,
            'skips_in_batched_render_frames':0,
            'render_frames_with_batched_steps':0,
            'largest_scheduled_tick_batch':1,
            'single_skip_percent_rounded':33,'batched_skip_percent_rounded':None,
            'windows_with_both_render_modes':0,
            'windows_with_higher_batched_skip_rate':0,
        })
        self.save(self.one,report)
        result=check.compare([self.one,self.two])
        self.assertEqual(result['eligible_150tick_mode_comparisons'],6)
        self.assertEqual(result['runs_with_batched_higher_in_all_six_windows'],1)
        self.assertFalse(result['independent_guest_execution_authenticated'])

    def test_bad_json_schema_duplicate_keys_and_symlinks(self):
        self.one.write_text('{"foo": 1, "foo": 2}\n',encoding='ascii')
        with self.assertRaises(ValueError):
            check.compare([self.one,self.two])
        self.save(self.one,fixture())
        self.one.unlink()
        self.one.symlink_to(self.two)
        with self.assertRaises(ValueError):
            check.compare([self.one,self.two])
        self.one.unlink()
        self.one.write_bytes(b'x'*32769)
        with self.assertRaises(ValueError):
            check.compare([self.one,self.two])

    def test_cli_path_free_fail_closed_output(self):
        script = Path(__file__).resolve().parents[1]/'tools'/'compare_nexium_audio_stress_runs.py'
        output = self.root/'safe.json'
        cmd = [sys.executable,str(script),'--report',str(self.one),
               '--report',str(self.two),'--out',str(output)]
        ok = subprocess.run(cmd,cwd=self.root,capture_output=True,text=True)
        self.assertEqual(ok.returncode,0,ok.stderr)
        self.assertEqual(json.loads(output.read_text())['reports_compared'],2)
        self.one.unlink()
        fail = subprocess.run(cmd,cwd=self.root,capture_output=True,text=True)
        self.assertEqual(fail.returncode,0,fail.stderr)
        self.assertEqual(json.loads(output.read_text())['status'],
                         'INCONCLUSIVE_UNVERIFIED_CROSS_RUN_AUDIO_EVIDENCE')
        self.assertNotIn(str(self.root),fail.stdout+fail.stderr+output.read_text())


if __name__ == '__main__':
    unittest.main()
