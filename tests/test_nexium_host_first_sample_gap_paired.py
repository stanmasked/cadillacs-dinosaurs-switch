"""Stage 264 mandatory host first X11 unsampled interval proof."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import verify_nexium_host_first_sample_gap_paired as first
from tools import verify_nexium_host_keydown_bracket as keydown
from test_nexium_host_x11_cadence_paired import X11CaptureCadenceTests


class PairedFirstSampleGapTests(unittest.TestCase):
    def setUp(self):
        fixture = X11CaptureCadenceTests(
            'test_exact_rounded_capture_coverage_equation_for_both_modes')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        self.guests = fixture.guests
        self.nros = fixture.nros
        # Real guest jobs save this proof immediately after raw xdotool
        # observation. Synthetic fixtures must derive it, not forge success.
        for mode in ('baseline', 'extra-poll'):
            proof = keydown.verify(self.guests[mode], self.nros[mode], mode)
            (self.guests[mode] / 'host-keydown-bracket-attestation.json').write_text(
                json.dumps(proof), encoding='ascii')

    def verify(self):
        return first.verify(self.guests['baseline'], self.guests['extra-poll'],
                            self.nros['baseline'], self.nros['extra-poll'])

    def mutate(self, mode, filename, change):
        p = self.guests[mode] / filename
        d = json.loads(p.read_text(encoding='ascii'))
        change(d)
        p.write_text(json.dumps(d), encoding='ascii')

    def test_initial_gap_bounded_by_both_host_clocks(self):
        result = self.verify()
        self.assertEqual(result['status'], first.STATUS)
        for mode in ('baseline', 'extra-poll'):
            d = result['modes'][mode]
            self.assertEqual(d['host_xdotool_command_duration_floor_us'], 500)
            self.assertEqual(d['host_xdotool_command_duration_ceil_us'], 501)
            self.assertEqual(d['first_post_command_capture_begin_offset_floor_us'],
                             5000)
            self.assertEqual(d['initial_unsampled_interval_conservative_lower_us'],
                             4499)
            self.assertEqual(d['initial_unsampled_interval_conservative_upper_us'],
                             4501)
            self.assertEqual(d['inter_call_gap_sum_rounded_us'], 1300)
            self.assertFalse(d['physical_input_to_first_display_latency_verified'])

    def test_missing_saved_keydown_proof_fails_closed(self):
        (self.guests['baseline'] / 'host-keydown-bracket-attestation.json').unlink()
        with self.assertRaises((ValueError, OSError)):
            self.verify()

    def test_forged_keydown_attestation_fails_closed(self):
        self.mutate('extra-poll', 'host-keydown-bracket-attestation.json',
                    lambda r: r.update(
                        keydown_subprocess_call_duration_floor_us=100))
        with self.assertRaises(ValueError):
            self.verify()

    def test_command_duration_forgery_fails_closed(self):
        self.mutate('baseline', 'host-keydown-bracket-evidence.json',
                    lambda r: r.update(keydown_command_duration_floor_us=100))
        with self.assertRaises(ValueError):
            self.verify()

    def test_raw_initial_sample_missing_rejected(self):
        self.mutate('baseline', 'host-x11-sample-sequence-evidence.json',
                    lambda r: r['samples'].pop(0))
        with self.assertRaises(ValueError):
            self.verify()

    def test_raw_first_sample_before_keydown_return_rejected(self):
        self.mutate('baseline', 'host-x11-sample-sequence-evidence.json',
                    lambda r: r['samples'][0].update(
                        capture_begin_offset_us=100))
        with self.assertRaises(ValueError):
            self.verify()

    def test_replayed_guest_mode_and_nro_rejected(self):
        with self.assertRaises(ValueError):
            first.verify(self.guests['extra-poll'], self.guests['baseline'],
                         self.nros['extra-poll'], self.nros['baseline'])

    def test_raw_x11_overlapping_capture_calls_rejected(self):
        self.mutate('baseline', 'host-x11-sample-sequence-evidence.json',
                    lambda r: r['samples'][1].update(
                        capture_begin_offset_us=5010))
        with self.assertRaises(ValueError):
            self.verify()

    def test_false_physical_claim_in_keydown_evidence_rejected(self):
        self.mutate('baseline', 'host-keydown-bracket-evidence.json',
                    lambda r: r.update(physical_switch_lcd_latency_verified=True))
        with self.assertRaises(ValueError):
            self.verify()

    def test_duplicate_json_attestation_rejected(self):
        path = self.guests['extra-poll'] / 'host-keydown-bracket-attestation.json'
        path.write_text(path.read_text().replace(
            '"status":', '"status":"FABRICATED","status":'), encoding='ascii')
        with self.assertRaises(ValueError):
            self.verify()

    def test_cli_without_pythonpath_and_refuses_overwrite(self):
        script = (Path(__file__).resolve().parents[1] /
                  'tools/verify_nexium_host_first_sample_gap_paired.py')
        out = self.root / 'host-first-sample.json'
        args = ['--baseline-dir', str(self.guests['baseline']),
                '--extra-dir', str(self.guests['extra-poll']),
                '--baseline-nro', str(self.nros['baseline']),
                '--extra-nro', str(self.nros['extra-poll']),
                '--out', str(out)]
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        done = subprocess.run([sys.executable, str(script), *args],
                              cwd=self.root, env=env,
                              text=True, capture_output=True, timeout=12)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(json.loads(out.read_text())['status'], first.STATUS)
        with self.assertRaises(FileExistsError):
            first.main(args)

    def test_no_success_output_when_source_missing(self):
        (self.guests['extra-poll'] /
         'host-x11-sample-sequence-evidence.json').unlink()
        out = self.root / 'missing-source-proof.json'
        args = ['--baseline-dir', str(self.guests['baseline']),
                '--extra-dir', str(self.guests['extra-poll']),
                '--baseline-nro', str(self.nros['baseline']),
                '--extra-nro', str(self.nros['extra-poll']),
                '--out', str(out)]
        with self.assertRaises((ValueError, OSError)):
            first.main(args)
        self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
