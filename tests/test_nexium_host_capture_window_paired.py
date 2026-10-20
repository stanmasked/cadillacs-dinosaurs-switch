"""Stage 256 required paired real host X11 call interval, synthetic fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import verify_nexium_host_capture_window_paired as paired
from tools import verify_nexium_host_capture_window as single
from test_nexium_host_capture_window import RawIntervalVerifierTests


class RequiredDualX11CaptureWindowsTests(unittest.TestCase):
    def setUp(self):
        fixture=RawIntervalVerifierTests(
            'test_valid_host_time_window_bound_to_real_guest_frame_fixture')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root=fixture.root
        self.guests=fixture.guests
        self.nros=fixture.nros
        # The real NeXium guest workflow produces this single-mode
        # attestation AFTER binding its 900-tick audio mode. A valid
        # synthetic setup must produce it from its OWN raw X11 inputs;
        # never fabricate a hardcoded stored-success file.
        for mode in ('baseline','extra-poll'):
            report=single.verify(self.guests[mode],self.nros[mode],mode)
            (self.guests[mode]/'host-capture-interval-attestation.json').write_text(
                json.dumps(report),encoding='ascii')

    def verify(self):
        return paired.verify(
            self.guests['baseline'],self.guests['extra-poll'],
            self.nros['baseline'],self.nros['extra-poll'])

    def edit(self,mode,name,**updates):
        file=self.guests[mode]/name
        data=json.loads(file.read_text())
        data.update(updates)
        file.write_text(json.dumps(data))

    def test_two_nro_bound_host_call_windows_pass(self):
        report=self.verify()
        self.assertEqual(report['status'],paired.STATUS)
        self.assertTrue(report['both_real_guest_host_x11_capture_call_windows_bound'])
        self.assertEqual(report['modes']['baseline']['host_xgetimage_call_begin_offset_us'],6000)
        self.assertEqual(report['modes']['extra-poll']['host_xgetimage_call_end_offset_us'],6270)
        self.assertFalse(report['precise_input_to_display_latency_verified'])
        self.assertFalse(report['cross_mode_latency_comparison_verified'])

    def test_entire_mode_directories_and_matching_nro_swap_rejected(self):
        with self.assertRaises(ValueError):
            paired.verify(
                self.guests['extra-poll'],self.guests['baseline'],
                self.nros['extra-poll'],self.nros['baseline'])

    def test_absent_second_host_report_rejected(self):
        (self.guests['extra-poll']/'host-capture-window-evidence.json').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_inconclusive_second_interval_rejected(self):
        self.edit('extra-poll','host-capture-window-evidence.json',
                  status='INCONCLUSIVE_NO_BOUND_X11_CAPTURE_WINDOW',
                  host_x11_capture_window_observed=False)
        with self.assertRaises(ValueError):self.verify()

    def test_wrong_host_frame_token_rejected(self):
        self.edit('baseline','host-capture-window-evidence.json',frame_token_u16=1)
        with self.assertRaises(ValueError):self.verify()

    def test_no_independent_frame_identity_rejected(self):
        (self.guests['extra-poll']/'guest-live-counter-frame-tokens.csv').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_mutated_saved_success_report_rejected(self):
        self.edit('baseline','host-capture-interval-attestation.json',
                  host_command_completion_to_x11_call_start_us=5000)
        with self.assertRaises(ValueError):self.verify()

    def test_guest_mode_tamper_rejected(self):
        self.edit('extra-poll','guest-audio-mode-binding.json',
                  selected_mode='baseline')
        with self.assertRaises(ValueError):self.verify()

    def test_nro_digest_change_rejected(self):
        path=self.nros['baseline']
        path.write_bytes(path.read_bytes()+b'forged')
        with self.assertRaises(ValueError):self.verify()

    def test_modified_900_tick_stress_source_rejected(self):
        path=self.guests['baseline']/'guest-audio-stress-evidence.json'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ValueError):self.verify()

    def test_negative_or_decreasing_capture_time_rejected(self):
        self.edit('baseline','host-capture-window-evidence.json',
                  post_keydown_command_to_capture_begin_us=7500,
                  post_keydown_command_to_capture_end_us=6200)
        with self.assertRaises(ValueError):self.verify()

    def test_host_physical_latency_false_claim_rejected(self):
        self.edit('baseline','host-capture-window-evidence.json',
                  precise_input_to_display_latency_verified=True)
        with self.assertRaises(ValueError):self.verify()

    def test_replayed_json_duplicate_field_rejected(self):
        path=self.guests['extra-poll']/'host-capture-interval-attestation.json'
        path.write_text(path.read_text().replace(
            '"status":','"status": "FORGED", "status":'))
        with self.assertRaises(ValueError):self.verify()

    def test_direct_cli_without_pythonpath_verifies_two_independent_modes(self):
        script=(Path(__file__).resolve().parents[1] /
                'tools/verify_nexium_host_capture_window_paired.py')
        outfile=self.root/'real-cli-output.json'
        args=[
            sys.executable,str(script),
            '--baseline-dir',str(self.guests['baseline']),
            '--extra-dir',str(self.guests['extra-poll']),
            '--baseline-nro',str(self.nros['baseline']),
            '--extra-nro',str(self.nros['extra-poll']),
            '--out',str(outfile)]
        env=os.environ.copy()
        env.pop('PYTHONPATH',None)
        proc=subprocess.run(args,cwd=self.root,env=env,
                            capture_output=True,text=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        report=json.loads(outfile.read_text())
        self.assertEqual(report['status'],paired.STATUS)
        with self.assertRaises(FileExistsError):paired.main(args[2:])

    def test_fail_closed_no_partial_success_artifact(self):
        (self.guests['baseline']/'host-capture-window-evidence.json').unlink()
        output=self.root/'absent.json'
        args=['--baseline-dir',str(self.guests['baseline']),
              '--extra-dir',str(self.guests['extra-poll']),
              '--baseline-nro',str(self.nros['baseline']),
              '--extra-nro',str(self.nros['extra-poll']),
              '--out',str(output)]
        with self.assertRaises(ValueError):paired.main(args)
        self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()
