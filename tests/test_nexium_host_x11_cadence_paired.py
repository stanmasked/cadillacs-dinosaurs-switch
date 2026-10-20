"""Stage 263 coverage/gap audit from raw real-NRO-bound X11 source."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import verify_nexium_host_x11_cadence_paired as cadence
from tools import verify_nexium_host_x11_sample_sequence_paired as previous
from test_nexium_host_x11_sample_sequence_paired import PairedRequiredX11SeriesTests


class X11CaptureCadenceTests(unittest.TestCase):
    def setUp(self):
        fixture = PairedRequiredX11SeriesTests('test_authentic_consistent_pair_passes')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        self.guests = fixture.guests
        self.nros = fixture.nros

    def verify(self):
        return cadence.verify(self.guests['baseline'], self.guests['extra-poll'],
                              self.nros['baseline'], self.nros['extra-poll'])

    def edit(self, mode, filename, callback):
        path = self.guests[mode] / filename
        d = json.loads(path.read_text(encoding='ascii'))
        callback(d)
        path.write_text(json.dumps(d), encoding='ascii')

    def test_exact_rounded_capture_coverage_equation_for_both_modes(self):
        report = self.verify()
        self.assertEqual(report['status'], cadence.STATUS)
        for mode in ('baseline', 'extra-poll'):
            entry = report['modes'][mode]
            self.assertEqual(entry['x11_sample_count'], 3)
            self.assertEqual(entry['negative_before_counter_count'], 2)
            self.assertEqual(entry['total_rounded_capture_span_us'], 1770)
            self.assertEqual(entry['sum_rounded_xgetimage_call_envelopes_us'], 470)
            self.assertEqual(entry['sum_between_capture_call_gaps_us'], 1300)
            self.assertEqual(entry['max_between_capture_call_gap_us'], 900)
            self.assertEqual(
                entry['last_negative_to_first_positive_capture_gap_us'], 400)
            self.assertFalse(entry['first_visible_frame_onset_verified'])
            self.assertFalse(entry['cross_mode_causal_comparison_verified'])

    def test_stage262_required_verifier_still_accepts_unchanged_inputs(self):
        self.assertEqual(
            previous.verify(self.guests['baseline'], self.guests['extra-poll'],
                            self.nros['baseline'], self.nros['extra-poll'])['status'],
            previous.STATUS)

    def test_full_mode_and_nro_swap_rejected(self):
        with self.assertRaises(ValueError):
            cadence.verify(self.guests['extra-poll'], self.guests['baseline'],
                           self.nros['extra-poll'], self.nros['baseline'])

    def test_missing_intermediate_negative_rejected(self):
        self.edit('baseline', 'host-x11-sample-sequence-evidence.json',
                  lambda d: d['samples'].pop(0))
        with self.assertRaises(ValueError):
            self.verify()

    def test_overlapping_capture_envelopes_rejected(self):
        self.edit('extra-poll', 'host-x11-sample-sequence-evidence.json',
                  lambda d: d['samples'][1].update(capture_begin_offset_us=5050))
        with self.assertRaises(ValueError):
            self.verify()

    def test_negative_rgb_forgery_rejected_before_cadence_metrics(self):
        from tools import nexium_host_live_counter_pixel as pixels
        self.edit('baseline', 'host-x11-sample-sequence-evidence.json',
                  lambda d: d['samples'][0].update(
                      four_counter_point_rgb={
                          k:list(v) for k,v in pixels.EXPECTED.items()}))
        with self.assertRaises(ValueError):
            self.verify()

    def test_forged_saved_attestation_rejected(self):
        self.edit('extra-poll', 'host-x11-sample-sequence-attestation.json',
                  lambda d: d.update(total_post_command_samples=100))
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_exact_nro_rejected(self):
        self.nros['baseline'].unlink()
        with self.assertRaises((ValueError, OSError)):
            self.verify()

    def test_duplicate_raw_json_keys_rejected(self):
        path = self.guests['baseline'] / 'host-x11-sample-sequence-evidence.json'
        path.write_text(path.read_text().replace(
            '"status":', '"status":"FORGED","status":'), encoding='ascii')
        with self.assertRaises(ValueError):
            self.verify()

    def test_cli_standalone_without_pythonpath_and_no_overwrite(self):
        script = (Path(__file__).resolve().parents[1] /
                  'tools/verify_nexium_host_x11_cadence_paired.py')
        out = self.root / 'cadence.json'
        args = ['--baseline-dir', str(self.guests['baseline']),
                '--extra-dir', str(self.guests['extra-poll']),
                '--baseline-nro', str(self.nros['baseline']),
                '--extra-nro', str(self.nros['extra-poll']),
                '--out', str(out)]
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        run = subprocess.run([sys.executable, str(script), *args],
                             cwd=self.root, env=env,
                             capture_output=True, text=True, timeout=12)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(out.read_text())['status'], cadence.STATUS)
        with self.assertRaises(FileExistsError):
            cadence.main(args)

    def test_invalid_input_never_creates_success_output(self):
        (self.guests['extra-poll'] / 'host-x11-sample-sequence-evidence.json').unlink()
        out = self.root / 'no-false-cadence.json'
        args = ['--baseline-dir', str(self.guests['baseline']),
                '--extra-dir', str(self.guests['extra-poll']),
                '--baseline-nro', str(self.nros['baseline']),
                '--extra-nro', str(self.nros['extra-poll']),
                '--out', str(out)]
        with self.assertRaises((ValueError, OSError)):
            cadence.main(args)
        self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
