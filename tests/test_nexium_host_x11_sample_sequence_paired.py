"""Stage 262 required paired native-NRO bound host X11 sample-series proofs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import verify_nexium_host_x11_sample_sequence as original
from tools import verify_nexium_host_x11_sample_sequence_paired as paired
from test_nexium_host_x11_sample_sequence import RawBoundedSequenceTests


class PairedRequiredX11SeriesTests(unittest.TestCase):
    def setUp(self):
        fixture=RawBoundedSequenceTests(
            'test_correct_all_three_x11_samples_bind_to_native_guest')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root=fixture.root
        self.guests=fixture.guests
        self.nros=fixture.nros
        # Real NeXium creates the stored one-mode attestation AFTER
        # native guest execution. Generate the fixture from actual
        # synthetic RAW inputs, not a hand-authored success indicator.
        for mode,guest in self.guests.items():
            fresh=original.verify(guest,self.nros[mode],mode)
            (guest/'host-x11-sample-sequence-attestation.json').write_text(
                json.dumps(fresh),encoding='ascii')

    def verify(self):
        return paired.verify(self.guests['baseline'],
                             self.guests['extra-poll'],
                             self.nros['baseline'],
                             self.nros['extra-poll'])

    def mutate(self,mode,filename,edit):
        path=self.guests[mode]/filename
        record=json.loads(path.read_text())
        edit(record)
        path.write_text(json.dumps(record),encoding='ascii')

    def test_authentic_consistent_pair_passes(self):
        result=self.verify()
        self.assertEqual(result['status'],paired.STATUS)
        self.assertTrue(result['both_real_ne_xium_ordered_sample_series_verified'])
        self.assertEqual(result['modes']['baseline']['total_x11_images'],3)
        self.assertEqual(result['modes']['extra-poll']['guest_submitted_render_iteration'],2250)
        self.assertFalse(result['exact_first_visible_frame_onset_verified'])

    def test_complete_guest_archive_plus_matching_nro_swap_rejected(self):
        with self.assertRaises(ValueError):
            paired.verify(self.guests['extra-poll'],self.guests['baseline'],
                          self.nros['extra-poll'],self.nros['baseline'])

    def test_missing_one_raw_trace_rejected(self):
        (self.guests['extra-poll']/'host-x11-sample-sequence-evidence.json').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_missing_saved_one_mode_proof_rejected(self):
        (self.guests['baseline']/'host-x11-sample-sequence-attestation.json').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_saved_forged_success_rejected(self):
        self.mutate('baseline','host-x11-sample-sequence-attestation.json',
                    lambda d:d.update(total_post_command_samples=99))
        with self.assertRaises(ValueError):self.verify()

    def test_dropped_intermediate_sample_rejected(self):
        self.mutate('extra-poll','host-x11-sample-sequence-evidence.json',
                    lambda d:d['samples'].pop(0))
        with self.assertRaises(ValueError):self.verify()

    def test_reordered_or_repeated_sample_index_rejected(self):
        self.mutate('baseline','host-x11-sample-sequence-evidence.json',
                    lambda d:d['samples'][1].update(index=1))
        with self.assertRaises(ValueError):self.verify()

    def test_forged_negative_four_counter_colors_rejected(self):
        from tools import nexium_host_live_counter_pixel as px
        self.mutate('extra-poll','host-x11-sample-sequence-evidence.json',
                    lambda d:d['samples'][0].update(
                        four_counter_point_rgb={k:list(v) for k,v in px.EXPECTED.items()}))
        with self.assertRaises(ValueError):self.verify()

    def test_forged_positive_native_frame_token_rejected(self):
        self.mutate('baseline','host-x11-sample-sequence-evidence.json',
                    lambda d:d['samples'][-1].update(frame_token_u16=12))
        with self.assertRaises(ValueError):self.verify()

    def test_overlapping_x11_capture_time_rejected(self):
        self.mutate('extra-poll','host-x11-sample-sequence-evidence.json',
                    lambda d:d['samples'][1].update(capture_begin_offset_us=5001))
        with self.assertRaises(ValueError):self.verify()

    def test_guest_mode_substitution_rejected(self):
        self.mutate('baseline','guest-audio-mode-binding.json',
                    lambda d:d.update(selected_mode='extra-poll'))
        with self.assertRaises(ValueError):self.verify()

    def test_exact_original_nro_byte_tamper_rejected(self):
        path=self.nros['baseline']
        path.write_bytes(path.read_bytes()+b'BAD')
        with self.assertRaises(ValueError):self.verify()

    def test_raw_900_tick_report_tamper_rejected(self):
        path=self.guests['extra-poll']/'guest-audio-stress-evidence.json'
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaises(ValueError):self.verify()

    def test_false_physical_first_frame_claim_rejected(self):
        self.mutate('baseline','host-x11-sample-sequence-evidence.json',
                    lambda d:d.update(precise_first_visible_frame_onset_verified=True))
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_json_status_key_rejected(self):
        path=self.guests['extra-poll']/'host-x11-sample-sequence-attestation.json'
        path.write_text(path.read_text().replace(
            '"status":','"status":"FORGED","status":'),encoding='ascii')
        with self.assertRaises(ValueError):self.verify()

    def test_direct_ci_script_without_pythonpath(self):
        script=(Path(__file__).resolve().parents[1]/
                'tools/verify_nexium_host_x11_sample_sequence_paired.py')
        outfile=self.root/'paired-full-series.json'
        args=['--baseline-dir',str(self.guests['baseline']),
              '--extra-dir',str(self.guests['extra-poll']),
              '--baseline-nro',str(self.nros['baseline']),
              '--extra-nro',str(self.nros['extra-poll']),
              '--out',str(outfile)]
        env=os.environ.copy()
        env.pop('PYTHONPATH',None)
        run=subprocess.run([sys.executable,str(script),*args],
                           cwd=self.root,env=env,
                           capture_output=True,text=True,timeout=10)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.assertEqual(json.loads(outfile.read_text())['status'],paired.STATUS)
        with self.assertRaises(FileExistsError):
            paired.main(args)

    def test_missing_source_cannot_produce_fake_positive_report(self):
        (self.guests['baseline']/'host-x11-sample-sequence-evidence.json').unlink()
        outfile=self.root/'should-not-exist.json'
        args=['--baseline-dir',str(self.guests['baseline']),
              '--extra-dir',str(self.guests['extra-poll']),
              '--baseline-nro',str(self.nros['baseline']),
              '--extra-nro',str(self.nros['extra-poll']),
              '--out',str(outfile)]
        with self.assertRaises(ValueError):paired.main(args)
        self.assertFalse(outfile.exists())


if __name__=='__main__':
    unittest.main()
