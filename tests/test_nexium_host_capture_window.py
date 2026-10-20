"""Stage 255: host-monotonic XGetImage sampling intervals (synthetic only).

These intervals are NOT measurements of actual guest input delivery, first
visual onset, GPU scanout, physical controller or LCD-to-photon latency.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

from tools import nexium_host_live_counter_pixel as pixel
from tools import verify_nexium_host_capture_window as timing
from test_nexium_host_frame_token_paired import RequiredDualFrameIdentityTests


class SyntheticClockSampler:
    def __init__(self,window):
        if window!='987':
            raise ValueError('bad fake window')
        self.n=0

    def sample(self):
        self.n+=1
        if self.n==1:
            return {'caption':(11,18,29),'impact':(62,83,74),
                    'player':(62,180,208),'ground':(62,83,74)}
        time.sleep(0.001)
        return {**pixel.EXPECTED,'frame_token_u16':2250}

    def close(self):
        pass


class HostCaptureWatcherTests(unittest.TestCase):
    def test_real_local_monotonic_clock_bounds_synthetic_x11_samples(self):
        watcher=pixel.CounterWindowWatcher('987',sampler_factory=SyntheticClockSampler,
                                           seconds=0.2)
        self.assertTrue(watcher.start())
        watcher.trigger()
        host=watcher.finish()
        report=watcher.capture_interval_result()
        self.assertEqual(host['status'],pixel.STATUS)
        self.assertTrue(report['host_x11_capture_window_observed'])
        self.assertEqual(report['frame_token_u16'],2250)
        self.assertLessEqual(report['post_keydown_command_to_capture_begin_us'],
                             report['post_keydown_command_to_capture_end_us'])
        self.assertEqual(
            report['xgetimage_call_duration_upper_us'],
            report['post_keydown_command_to_capture_end_us']-
            report['post_keydown_command_to_capture_begin_us'])
        self.assertFalse(report['precise_input_to_display_latency_verified'])
        self.assertFalse(report['physical_display_verified'])
        self.assertNotIn('window_id',report)
        self.assertNotIn('host_monotonic_timestamp_ns',report)

    def test_no_keydown_yields_inconclusive(self):
        watcher=pixel.CounterWindowWatcher('987',sampler_factory=SyntheticClockSampler,
                                           seconds=0.2)
        self.assertEqual(watcher.capture_interval_result()['status'],
                         'INCONCLUSIVE_NO_BOUND_X11_CAPTURE_WINDOW')
        self.assertFalse(
            watcher.capture_interval_result()['host_x11_capture_window_observed'])

    def test_explicit_fail_closed_report(self):
        rec=pixel.empty_capture_interval_result()
        self.assertIsNone(rec['frame_token_u16'])
        self.assertIsNone(rec['post_keydown_command_to_capture_begin_us'])
        self.assertFalse(rec['physical_controller_verified'])
        self.assertFalse(rec['gpu_scanout_timestamp_verified'])


class RawIntervalVerifierTests(unittest.TestCase):
    def setUp(self):
        fixture=RequiredDualFrameIdentityTests(
            'test_both_actual_gates_accept_synthetic_consistent_fixture')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root=fixture.root
        self.guests=fixture.guests
        self.nros=fixture.nros
        self.baseline=self.guests['baseline']
        self.extra=self.guests['extra-poll']
        for mode,g in self.guests.items():
            self.write(mode,{
                'schema':timing.SCHEMA,
                'status':timing.SUCCESS,
                'host_x11_capture_window_observed':True,
                'frame_token_u16':2250,
                'post_keydown_command_to_capture_begin_us':6000,
                'post_keydown_command_to_capture_end_us':6270,
                'xgetimage_call_duration_upper_us':270,
                'clock_domain':'HOST_MONOTONIC_ONLY',
                'precise_input_to_display_latency_verified':False,
                'actual_guest_input_delivery_timestamp_verified':False,
                'physical_controller_verified':False,
                'physical_display_verified':False,
                'gpu_scanout_timestamp_verified':False,
            })

    def path(self,mode):
        return self.guests[mode]/'host-capture-window-evidence.json'

    def write(self,mode,record):
        self.path(mode).write_text(json.dumps(record),encoding='ascii')

    def update(self,mode,**changes):
        record=json.loads(self.path(mode).read_text())
        record.update(changes)
        self.write(mode,record)

    def verify(self,mode='baseline'):
        return timing.verify(self.guests[mode],self.nros[mode],mode)

    def test_valid_host_time_window_bound_to_real_guest_frame_fixture(self):
        verified=self.verify()
        self.assertEqual(verified['status'],timing.BOUND)
        self.assertEqual(verified['matched_native_render_iteration'],2250)
        self.assertEqual(verified['host_command_completion_to_x11_call_start_us'],6000)
        self.assertEqual(verified['host_command_completion_to_x11_call_end_us'],6270)
        self.assertFalse(verified['precise_input_to_display_latency_verified'])

    def test_second_nro_mode_accepted_independently(self):
        self.assertEqual(self.verify('extra-poll')['status'],timing.BOUND)

    def test_complete_mode_swap_and_nro_pair_fails(self):
        with self.assertRaises(ValueError):
            timing.verify(self.extra,self.nros['extra-poll'],'baseline')

    def test_wrong_x11_frame_token_fails(self):
        self.update('baseline',frame_token_u16=2251)
        with self.assertRaises(ValueError):self.verify()

    def test_false_success_status_fails(self):
        self.update('baseline',status=timing.INCONCLUSIVE)
        with self.assertRaises(ValueError):self.verify()

    def test_missing_independent_guest_marker_fails(self):
        (self.baseline/'host-frame-token-evidence.json').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_missing_timing_report_fails(self):
        self.path('baseline').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_duration_and_monotonic_order_fails(self):
        for start,end,duration in [
            (8000,6000,-2000),(-1,6000,6001),(6000,2500002,2494002),
            (6000,6270,269),(6000,6270,True),(6000,'6270',270),
            (6000,6270,270.5)]:
            with self.subTest(v=(start,end,duration)):
                old=self.path('baseline').read_text()
                self.update('baseline',
                    post_keydown_command_to_capture_begin_us=start,
                    post_keydown_command_to_capture_end_us=end,
                    xgetimage_call_duration_upper_us=duration)
                with self.assertRaises(ValueError):self.verify()
                self.path('baseline').write_text(old)

    def test_unsupported_display_controller_and_latency_claims_fail(self):
        for flag in timing.FALSE_FLAGS:
            with self.subTest(flag=flag):
                old=self.path('baseline').read_text()
                self.update('baseline',**{flag:True})
                with self.assertRaises(ValueError):self.verify()
                self.path('baseline').write_text(old)

    def test_wrong_guest_nro_digest_fails(self):
        self.nros['baseline'].write_bytes(self.nros['baseline'].read_bytes()+b'fake')
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_json_field_fails(self):
        p=self.path('baseline')
        p.write_text(p.read_text().replace('"status":',
                           '"status":"FAKE","status":'))
        with self.assertRaises(ValueError):self.verify()

    def test_cli_inconclusive_does_not_assert_latency(self):
        self.path('extra-poll').unlink()
        target=self.root/'no-capture.json'
        args=['--guest-dir',str(self.extra),'--nro',str(self.nros['extra-poll']),
              '--mode','extra-poll','--out',str(target)]
        self.assertEqual(timing.main(args),0)
        report=json.loads(target.read_text())
        self.assertEqual(report['status'],timing.INCONCLUSIVE)
        self.assertFalse(report['precise_input_to_display_latency_verified'])
        self.assertFalse(report['host_sampling_interval_verified'])

    def test_cli_direct_no_pythonpath_from_external_directory(self):
        script=(Path(__file__).resolve().parents[1]/
                'tools/verify_nexium_host_capture_window.py')
        target=self.root/'direct.json'
        environment=os.environ.copy()
        environment.pop('PYTHONPATH',None)
        run=subprocess.run([sys.executable,str(script),
             '--guest-dir',str(self.baseline),
             '--nro',str(self.nros['baseline']),
             '--mode','baseline','--out',str(target)],
             cwd=self.root,env=environment,
             capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertEqual(json.loads(target.read_text())['status'],timing.BOUND)


if __name__=='__main__':
    unittest.main()
