"""Stage 258: mandatory paired real X11 keydown brackets, ROM-free fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import verify_nexium_host_keydown_bracket as individual
from tools import verify_nexium_host_keydown_bracket_paired as paired
from test_nexium_host_keydown_bracket import StandaloneBracketVerifierTests


class PairedKeydownX11Tests(unittest.TestCase):
    def setUp(self):
        fixture=StandaloneBracketVerifierTests(
            'test_consistent_host_bounds_and_guest_frame_accepted')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root=fixture.root
        self.guests=fixture.guests
        self.nros=fixture.nros
        # Follow the real workflow: the single-mode optional attestation
        # comes from that mode's own independent raw host/guest source.
        for mode,g in self.guests.items():
            proof=individual.verify(g,self.nros[mode],mode)
            (g/'host-keydown-bracket-attestation.json').write_text(
                json.dumps(proof),encoding='ascii')

    def verify(self):
        return paired.verify(self.guests['baseline'],
                             self.guests['extra-poll'],
                             self.nros['baseline'],
                             self.nros['extra-poll'])

    def edit(self,mode,name,**changes):
        target=self.guests[mode]/name
        value=json.loads(target.read_text())
        value.update(changes)
        target.write_text(json.dumps(value),encoding='ascii')

    def test_two_real_nro_mode_brackets_pass(self):
        proof=self.verify()
        self.assertEqual(proof['status'],paired.STATUS)
        self.assertTrue(proof['both_nro_bound_host_keydown_x11_brackets_verified'])
        self.assertEqual(proof['modes']['baseline']['native_render_iteration'],2250)
        self.assertEqual(proof['modes']['extra-poll']['keydown_call_duration_floor_us'],500)
        self.assertFalse(proof['cross_mode_latency_comparison_verified'])
        self.assertFalse(proof['precise_physical_input_to_display_latency_verified'])

    def test_whole_guest_directories_plus_nros_swapped_rejected(self):
        with self.assertRaises(ValueError):
            paired.verify(self.guests['extra-poll'],self.guests['baseline'],
                          self.nros['extra-poll'],self.nros['baseline'])

    def test_missing_second_raw_host_bracket_rejected(self):
        (self.guests['extra-poll']/'host-keydown-bracket-evidence.json').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_missing_baseline_stored_attestation_rejected(self):
        (self.guests['baseline']/'host-keydown-bracket-attestation.json').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_false_stored_success_rejected(self):
        self.edit('baseline','host-keydown-bracket-attestation.json',
                  keydown_invocation_to_x11_call_begin_us=7000)
        with self.assertRaises(ValueError):self.verify()

    def test_raw_host_token_mismatch_rejected(self):
        self.edit('extra-poll','host-keydown-bracket-evidence.json',
                  host_frame_token_u16=999)
        with self.assertRaises(ValueError):self.verify()

    def test_unsupported_physical_claim_rejected(self):
        self.edit('baseline','host-keydown-bracket-evidence.json',
                  physical_joycon_latency_verified=True)
        with self.assertRaises(ValueError):self.verify()

    def test_cross_mode_latency_comparison_refused(self):
        self.edit('baseline','host-keydown-bracket-evidence.json',
                  cross_mode_causal_comparison_verified=True)
        with self.assertRaises(ValueError):self.verify()

    def test_reverse_monotonic_host_clock_rejected(self):
        self.edit('baseline','host-keydown-bracket-evidence.json',
                  keydown_call_begin_to_x11_begin_us=100)
        with self.assertRaises(ValueError):self.verify()

    def test_mutated_exact_nro_rejected(self):
        p=self.nros['extra-poll']
        p.write_bytes(p.read_bytes()+b'tampered')
        with self.assertRaises(ValueError):self.verify()

    def test_invalid_guest_audio_mode_rejected(self):
        self.edit('baseline','guest-audio-mode-binding.json',
                  selected_mode='extra-poll')
        with self.assertRaises(ValueError):self.verify()

    def test_guest_900_tick_report_modified_rejected(self):
        p=self.guests['extra-poll']/'guest-audio-stress-evidence.json'
        p.write_bytes(p.read_bytes()+b' ')
        with self.assertRaises(ValueError):self.verify()

    def test_host_16bit_frame_missing_rejected(self):
        (self.guests['baseline']/'guest-live-counter-frame-tokens.csv').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_stored_json_status_key_rejected(self):
        p=self.guests['baseline']/'host-keydown-bracket-attestation.json'
        p.write_text(p.read_text().replace(
            '"status":','"status": "FORGED", "status":'),encoding='ascii')
        with self.assertRaises(ValueError):self.verify()

    def test_direct_ci_entrypoint_without_pythonpath(self):
        script=Path(__file__).resolve().parents[1]/'tools/verify_nexium_host_keydown_bracket_paired.py'
        out=self.root/'paired-host-keydown-proof.json'
        args=[
            '--baseline-dir',str(self.guests['baseline']),
            '--extra-dir',str(self.guests['extra-poll']),
            '--baseline-nro',str(self.nros['baseline']),
            '--extra-nro',str(self.nros['extra-poll']),
            '--out',str(out),
        ]
        env=os.environ.copy()
        env.pop('PYTHONPATH',None)
        proc=subprocess.run([sys.executable,str(script),*args],cwd=self.root,
                            env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        self.assertEqual(json.loads(out.read_text())['status'],paired.STATUS)
        with self.assertRaises(FileExistsError):paired.main(args)

    def test_fail_closed_without_written_positive_attestation(self):
        (self.guests['extra-poll']/'host-keydown-bracket-evidence.json').unlink()
        output=self.root/'absent.json'
        args=[
            '--baseline-dir',str(self.guests['baseline']),
            '--extra-dir',str(self.guests['extra-poll']),
            '--baseline-nro',str(self.nros['baseline']),
            '--extra-nro',str(self.nros['extra-poll']),
            '--out',str(output)
        ]
        with self.assertRaises(ValueError):paired.main(args)
        self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()
