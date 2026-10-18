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
