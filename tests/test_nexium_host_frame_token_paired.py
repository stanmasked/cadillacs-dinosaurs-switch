"""Stage 254 required two-mode host X11 / guest render-iteration gate.

All fixtures are synthetic ROM-free and do not impersonate real NeXium CI.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import verify_nexium_host_frame_token as frame
from tools import verify_nexium_host_frame_token_paired as paired
from test_nexium_host_counter_window_paired import RequiredHostWindowTests


def write_csv(path,fields,rows):
    with path.open('w',encoding='ascii',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


class RequiredDualFrameIdentityTests(unittest.TestCase):
    def setUp(self):
        fixture=RequiredHostWindowTests(
            'test_both_nro_bound_host_pixel_windows_accepted')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.guests=fixture.guests
        self.nros=fixture.nros
        self.root=fixture.root
        self.rows={}
        for mode,guest in self.guests.items():
            row={
                'event':'TOKEN_SUBMITTED',
                'render_iteration':'2250',
                'arena_tick':'148',
                'feedback_ttl':'6',
                'impact_ttl':'6',
                'token_u16':'2250',
            }
            write_csv(guest/'guest-live-counter-frame-tokens.csv',
                      frame.CSV_FIELDS,[row])
            (guest/'host-frame-token-evidence.json').write_text(
                json.dumps({
                    'schema':frame.HOST_SCHEMA,
                    'status':frame.STATUS,
                    'token_u16':2250,
                    'token_same_x11_image_as_counter_pixels':True,
                    'guest_submitted_frame_identity_verified':False,
                    'exact_host_guest_frame_latency_verified':False,
                    'physical_display_verified':False,
                }),encoding='ascii')
            proof=frame.verify(
                guest/'host-frame-token-evidence.json',
                guest/'host-counter-window-evidence.json',
                guest/'guest-live-counter-frame-tokens.csv',
                guest/'guest-live-counter-framebuffer.csv',
                guest/'metadata.txt',
                self.nros[mode])
            (guest/'host-guest-frame-token-evidence.json').write_text(
                json.dumps(proof),encoding='ascii')
            self.rows[mode]=row

    def verify(self):
        return paired.verify(self.guests['baseline'],
                             self.guests['extra-poll'],
                             self.nros['baseline'],
                             self.nros['extra-poll'])

    def update(self,mode,name,**values):
        path=self.guests[mode]/name
        current=json.loads(path.read_text())
        current.update(values)
        path.write_text(json.dumps(current))

    def test_both_actual_gates_accept_synthetic_consistent_fixture(self):
        result=self.verify()
        self.assertTrue(
            result['both_real_nexium_host_frames_match_guest_submitted_tokens'])
        self.assertEqual(result['modes']['baseline']['x11_token_u16'],2250)
        self.assertEqual(result['modes']['extra-poll']['matched_native_render_iteration'],2250)
        self.assertFalse(result['physical_switch_display_verified'])
        self.assertFalse(result['exact_input_to_display_latency_verified'])

    def test_complete_matching_guest_and_nro_swap_fails(self):
        with self.assertRaises(ValueError):
            paired.verify(self.guests['extra-poll'],
                          self.guests['baseline'],
                          self.nros['extra-poll'],
                          self.nros['baseline'])

    def test_missing_host_token_in_second_guest_fails(self):
        (self.guests['extra-poll']/'host-frame-token-evidence.json').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_forged_token_even_with_valid_four_pixels_fails(self):
        self.update('baseline','host-frame-token-evidence.json',token_u16=2251)
        with self.assertRaises(ValueError):self.verify()

    def test_no_claim_of_same_x11_image_fails(self):
        self.update('baseline','host-frame-token-evidence.json',
                    token_same_x11_image_as_counter_pixels=False)
        with self.assertRaises(ValueError):self.verify()

    def test_guest_trace_is_required(self):
        (self.guests['baseline']/'guest-live-counter-frame-tokens.csv').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_16bit_token_across_native_frames_fails(self):
        row=self.rows['baseline']
        duplicate={**row,'render_iteration':str(2250+65536),
                   'arena_tick':'149','feedback_ttl':'5','impact_ttl':'5'}
        write_csv(self.guests['baseline']/'guest-live-counter-frame-tokens.csv',
                  frame.CSV_FIELDS,[row,duplicate])
        with self.assertRaises(ValueError):self.verify()

    def test_no_real_guest_pixel_frame_in_trace_fails(self):
        row={**self.rows['baseline'],'render_iteration':'2251','token_u16':'2251'}
        write_csv(self.guests['baseline']/'guest-live-counter-frame-tokens.csv',
                  frame.CSV_FIELDS,[row])
        with self.assertRaises(ValueError):self.verify()

    def test_replayed_or_forged_stored_attestation_fails(self):
        self.update('baseline','host-guest-frame-token-evidence.json',
                    matched_native_render_iteration=9999)
        with self.assertRaises(ValueError):self.verify()

    def test_inconclusive_record_cannot_satisfy_mandatory_gate(self):
        self.update('extra-poll','host-guest-frame-token-evidence.json',
                    status=frame.INCONCLUSIVE,
                    host_x11_guest_submitted_frame_identity_verified=False)
        with self.assertRaises(ValueError):self.verify()

    def test_false_guest_audio_mode_binding_fails(self):
        self.update('baseline','guest-audio-mode-binding.json',
                    selected_mode='extra-poll')
        with self.assertRaises(ValueError):self.verify()

    def test_original_nro_mutation_fails(self):
        path=self.nros['baseline']
        path.write_bytes(path.read_bytes()+b'bad')
        with self.assertRaises(ValueError):self.verify()

    def test_original_stress_report_mutation_fails(self):
        path=self.guests['extra-poll']/'guest-audio-stress-evidence.json'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ValueError):self.verify()

    def test_window_four_colors_cannot_be_claimed_false(self):
        self.update('extra-poll','host-counter-window-evidence.json',
                    same_x11_image_four_pixel_match=False)
        with self.assertRaises(ValueError):self.verify()

    def test_unsupported_physical_display_proof_fails(self):
        self.update('baseline','host-frame-token-evidence.json',
                    physical_display_verified=True)
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_json_field_fails_closed(self):
        path=self.guests['baseline']/'host-frame-token-evidence.json'
        path.write_text(path.read_text().replace(
            '"status":','"status":"FORGED","status":'))
        with self.assertRaises(ValueError):self.verify()

    def test_direct_script_ci_entrypoint_without_pythonpath(self):
        script=(Path(__file__).resolve().parents[1] /
                'tools/verify_nexium_host_frame_token_paired.py')
        output=self.root/'direct-script-attestation.json'
        args=[
            sys.executable,str(script),
            '--baseline-dir',str(self.guests['baseline']),
            '--extra-dir',str(self.guests['extra-poll']),
            '--baseline-nro',str(self.nros['baseline']),
            '--extra-nro',str(self.nros['extra-poll']),
            '--out',str(output)]
        environment=os.environ.copy()
        environment.pop('PYTHONPATH',None)
        done=subprocess.run(args,cwd=self.root,env=environment,
                            text=True,capture_output=True,timeout=10)
        self.assertEqual(done.returncode,0,done.stdout+done.stderr)
        self.assertEqual(json.loads(output.read_text())['status'],paired.STATUS)

    def test_cli_refuses_overwrite_or_inconclusive_input(self):
        report=self.root/'paired-result.json'
        args=[
            '--baseline-dir',str(self.guests['baseline']),
            '--extra-dir',str(self.guests['extra-poll']),
            '--baseline-nro',str(self.nros['baseline']),
            '--extra-nro',str(self.nros['extra-poll']),
            '--out',str(report)]
        self.assertEqual(paired.main(args),0)
        raw=report.read_bytes()
        with self.assertRaises(FileExistsError):paired.main(args)
        self.assertEqual(raw,report.read_bytes())
        report.unlink()
        (self.guests['extra-poll']/'host-frame-token-evidence.json').unlink()
        with self.assertRaises(ValueError):paired.main(args)
        self.assertFalse(report.exists())


if __name__=='__main__':
    unittest.main()
