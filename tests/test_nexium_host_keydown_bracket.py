"""Stage 257: host-only xdotool invocation and X11 frame sampling brackets."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import nexium_host_live_counter_pixel as pixel
from tools import verify_nexium_host_keydown_bracket as bound
from test_nexium_host_capture_window import (
    RawIntervalVerifierTests, SyntheticClockSampler,
)


class HostKeydownBoundsTests(unittest.TestCase):
    def test_bracket_host_only_monotonic_clock_with_true_sample(self):
        watcher=pixel.CounterWindowWatcher('987',sampler_factory=SyntheticClockSampler,
                                           seconds=0.2)
        self.assertTrue(watcher.start())
        watcher.begin_keydown_command()
        watcher.trigger()
        self.assertEqual(watcher.finish()['status'],pixel.STATUS)
        raw=watcher.command_bracket_result()
        self.assertEqual(raw['status'],bound.RAW_SUCCESS)
        self.assertTrue(raw['host_command_to_x11_bracket_observed'])
        self.assertEqual(raw['host_frame_token_u16'],2250)
        self.assertLessEqual(raw['keydown_command_duration_floor_us'],
                             raw['keydown_command_duration_ceil_us'])
        self.assertEqual(raw['clock_domain'],'HOST_MONOTONIC_ONLY')
        self.assertFalse(raw['physical_switch_lcd_latency_verified'])
        self.assertFalse(raw['first_visible_frame_onset_verified'])
        self.assertNotIn('host_monotonic_ns',raw)
        self.assertNotIn('window_id',raw)

    def test_no_command_start_never_claims_success(self):
        watcher=pixel.CounterWindowWatcher('987',sampler_factory=SyntheticClockSampler)
        self.assertTrue(watcher.start())
        watcher.trigger()
        watcher.finish()
        self.assertEqual(watcher.command_bracket_result()['status'],
                         'INCONCLUSIVE_NO_HOST_KEYDOWN_BRACKET')

    def test_empty_bracket_is_honest(self):
        raw=pixel.empty_command_bracket_result()
        self.assertFalse(raw['host_command_to_x11_bracket_observed'])
        self.assertIsNone(raw['keydown_call_begin_to_x11_begin_us'])
        self.assertFalse(raw['physical_joycon_latency_verified'])


class StandaloneBracketVerifierTests(unittest.TestCase):
    def setUp(self):
        fixture=RawIntervalVerifierTests(
            'test_valid_host_time_window_bound_to_real_guest_frame_fixture')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root=fixture.root
        self.guests=fixture.guests
        self.nros=fixture.nros
        self.mode='baseline'
        for mode,guest in self.guests.items():
            (guest/'host-keydown-bracket-evidence.json').write_text(
                json.dumps({
                    'schema':bound.SCHEMA,
                    'status':bound.RAW_SUCCESS,
                    'host_command_to_x11_bracket_observed':True,
                    'host_frame_token_u16':2250,
                    'keydown_command_duration_floor_us':500,
                    'keydown_command_duration_ceil_us':501,
                    'keydown_call_begin_to_x11_begin_us':6500,
                    'keydown_call_begin_to_x11_end_us':6770,
                    'keydown_call_complete_to_x11_begin_us':6000,
                    'keydown_call_complete_to_x11_end_us':6270,
                    'clock_domain':'HOST_MONOTONIC_ONLY',
                    'guest_input_delivery_timestamp_verified':False,
                    'first_visible_frame_onset_verified':False,
                    'physical_joycon_latency_verified':False,
                    'physical_switch_lcd_latency_verified':False,
                    'gpu_scanout_timestamp_verified':False,
                    'cross_mode_causal_comparison_verified':False,
                }),encoding='ascii')

    def update(self,**fields):
        p=self.guests[self.mode]/'host-keydown-bracket-evidence.json'
        report=json.loads(p.read_text())
        report.update(fields)
        p.write_text(json.dumps(report))

    def verify(self):
        return bound.verify(self.guests[self.mode],self.nros[self.mode],self.mode)

    def test_consistent_host_bounds_and_guest_frame_accepted(self):
        result=self.verify()
        self.assertEqual(result['status'],bound.SUCCESS)
        self.assertEqual(result['matched_native_render_iteration'],2250)
        self.assertEqual(result['keydown_subprocess_call_duration_floor_us'],500)
        self.assertEqual(result['keydown_invocation_to_x11_call_end_us'],6770)
        self.assertFalse(result['physical_controller_verified'])

    def test_extra_poll_mode_independently_accepted(self):
        self.mode='extra-poll'
        self.assertEqual(self.verify()['status'],bound.SUCCESS)

    def test_missing_bracket_rejected(self):
        (self.guests['baseline']/'host-keydown-bracket-evidence.json').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_inconclusive_not_mistaken_for_success(self):
        self.update(status='INCONCLUSIVE_NO_HOST_KEYDOWN_BRACKET',
                    host_command_to_x11_bracket_observed=False)
        with self.assertRaises(ValueError):self.verify()

    def test_wrong_guest_token_rejected(self):
        self.update(host_frame_token_u16=2251)
        with self.assertRaises(ValueError):self.verify()

    def test_out_of_order_monotonic_timestamps_rejected(self):
        self.update(keydown_call_begin_to_x11_begin_us=200)
        with self.assertRaises(ValueError):self.verify()

    def test_forged_subprocess_duration_rejected(self):
        self.update(keydown_command_duration_floor_us=501,
                    keydown_command_duration_ceil_us=500)
        with self.assertRaises(ValueError):self.verify()

    def test_conflicts_with_previous_x11_interval_rejected(self):
        self.update(keydown_call_complete_to_x11_end_us=6271)
        with self.assertRaises(ValueError):self.verify()

    def test_physical_and_guest_input_claims_refused(self):
        for name in bound.FALSE_CLAIMS:
            with self.subTest(name=name):
                p=self.guests['baseline']/'host-keydown-bracket-evidence.json'
                prior=p.read_text()
                self.update(**{name:True})
                with self.assertRaises(ValueError):self.verify()
                p.write_text(prior)

    def test_guest_selected_mode_must_match(self):
        with self.assertRaises(ValueError):
            bound.verify(self.guests['baseline'],self.nros['baseline'],'extra-poll')

    def test_no_original_nro_mutation(self):
        p=self.nros['baseline']
        p.write_bytes(p.read_bytes()+b'fake')
        with self.assertRaises(ValueError):self.verify()

    def test_direct_cli_without_pythonpath(self):
        script=(Path(__file__).resolve().parents[1]/
                'tools/verify_nexium_host_keydown_bracket.py')
        path=self.root/'host-bracket.json'
        env=os.environ.copy();env.pop('PYTHONPATH',None)
        done=subprocess.run([
            sys.executable,str(script),
            '--guest-dir',str(self.guests['baseline']),
            '--nro',str(self.nros['baseline']),
            '--mode','baseline','--out',str(path)],
            cwd=self.root,env=env,text=True,capture_output=True,timeout=10)
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)
        self.assertEqual(json.loads(path.read_text())['status'],bound.SUCCESS)

    def test_cli_inconclusive_writes_no_latency_claim(self):
        (self.guests['baseline']/'host-keydown-bracket-evidence.json').unlink()
        path=self.root/'no-proof.json'
        self.assertEqual(bound.main([
            '--guest-dir',str(self.guests['baseline']),
            '--nro',str(self.nros['baseline']),
            '--mode','baseline','--out',str(path)]),0)
        raw=json.loads(path.read_text())
        self.assertEqual(raw['status'],bound.INCONCLUSIVE)
        self.assertFalse(raw['host_only_bracket_verified'])
        self.assertFalse(raw['physical_display_verified'])


if __name__=='__main__':
    unittest.main()
