"""Stage 260 required paired actual X11 absent/present guest-frame evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import verify_nexium_host_x11_transition as individual
from tools import verify_nexium_host_x11_transition_paired as paired
from test_nexium_host_x11_transition import NativeBoundTransitionVerifierTests


class PairedRealX11TransitionsTests(unittest.TestCase):
    def setUp(self):
        fixture=NativeBoundTransitionVerifierTests(
            'test_real_guest_synthetic_source_is_consistent')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root=fixture.root
        self.guests=fixture.guests
        self.nros=fixture.nros
        # The real workflow saves independent single-mode proofs AFTER
        # NRO/audio selected mode is authenticated. Recompute, never
        # fabricate a stored SUCCESS from literal fixture text.
        for mode,guest in self.guests.items():
            real=individual.verify(guest,self.nros[mode],mode)
            (guest/'host-x11-transition-bracket-attestation.json').write_text(
                json.dumps(real),encoding='ascii')

    def verify(self):
        return paired.verify(self.guests['baseline'],
                             self.guests['extra-poll'],
                             self.nros['baseline'],
                             self.nros['extra-poll'])

    def edit(self,mode,name,**kwargs):
        file=self.guests[mode]/name
        val=json.loads(file.read_text())
        val.update(kwargs)
        file.write_text(json.dumps(val),encoding='ascii')

    def test_two_modes_genuine_X11_negative_to_positive_accept(self):
        result=self.verify()
        self.assertEqual(result['status'],paired.STATUS)
        self.assertTrue(result['both_nro_bound_host_x11_state_transitions_verified'])
        self.assertEqual(result['modes']['baseline']['guest_render_iteration'],2250)
        self.assertEqual(result['modes']['extra-poll']['conservative_observed_transition_interval_us'],[6000,6770])
        self.assertFalse(result['exact_first_visible_frame_onset_verified'])

    def test_complete_guest_and_matching_nro_mode_swap_rejected(self):
        with self.assertRaises(ValueError):
            paired.verify(self.guests['extra-poll'],
                          self.guests['baseline'],
                          self.nros['extra-poll'],
                          self.nros['baseline'])

    def test_missing_baseline_last_negative_image_rejected(self):
        (self.guests['baseline']/'host-x11-transition-bracket-evidence.json').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_missing_extra_stored_native_correlation_rejected(self):
        (self.guests['extra-poll']/'host-x11-transition-bracket-attestation.json').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_inconclusive_single_positive_image_does_not_pass(self):
        self.edit('baseline','host-x11-transition-bracket-evidence.json',
                  status='INCONCLUSIVE_NO_POST_TRIGGER_ABSENT_SAMPLE',
                  post_trigger_absent_x11_images=0)
        with self.assertRaises(ValueError):self.verify()

    def test_fake_negative_image_that_already_contains_counter_rejected(self):
        from tools import nexium_host_live_counter_pixel as pixel
        self.edit('extra-poll','host-x11-transition-bracket-evidence.json',
                  last_negative_x11_pixel_rgb={
                      k:list(v) for k,v in pixel.EXPECTED.items()})
        with self.assertRaises(ValueError):self.verify()

    def test_wrong_native_frame_token_rejected(self):
        self.edit('baseline','host-x11-transition-bracket-evidence.json',
                  x11_positive_frame_token_u16=2251)
        with self.assertRaises(ValueError):self.verify()

    def test_reversed_negative_to_positive_time_rejected(self):
        self.edit('baseline','host-x11-transition-bracket-evidence.json',
                  last_negative_xgetimage_begin_offset_us=8000)
        with self.assertRaises(ValueError):self.verify()

    def test_replayed_stored_success_with_forged_time_rejected(self):
        self.edit('extra-poll','host-x11-transition-bracket-attestation.json',
                  conservative_observed_pixel_transition_interval_start_us=5000)
        with self.assertRaises(ValueError):self.verify()

    def test_wrong_guest_mode_attestation_rejected(self):
        self.edit('baseline','guest-audio-mode-binding.json',
                  selected_mode='extra-poll')
        with self.assertRaises(ValueError):self.verify()

    def test_original_guest_nro_byte_mutation_rejected(self):
        p=self.nros['extra-poll']
        p.write_bytes(p.read_bytes()+b'TAMPER')
        with self.assertRaises(ValueError):self.verify()

    def test_prior_real_guest_native_frame_trace_is_mandatory(self):
        (self.guests['baseline']/'guest-live-counter-frame-tokens.csv').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_physical_first_frame_claim_explicitly_rejected(self):
        self.edit('baseline','host-x11-transition-bracket-evidence.json',
                  first_visible_frame_onset_verified=True)
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_json_status_rejected(self):
        p=self.guests['baseline']/'host-x11-transition-bracket-attestation.json'
        p.write_text(p.read_text().replace(
            '"status":','"status":"FORGED","status":'),encoding='ascii')
        with self.assertRaises(ValueError):self.verify()

    def test_cli_can_run_directly_without_pythonpath(self):
        script=(Path(__file__).resolve().parents[1]/
                'tools/verify_nexium_host_x11_transition_paired.py')
        outfile=self.root/'paired-transition.json'
        args=['--baseline-dir',str(self.guests['baseline']),
              '--extra-dir',str(self.guests['extra-poll']),
              '--baseline-nro',str(self.nros['baseline']),
              '--extra-nro',str(self.nros['extra-poll']),
              '--out',str(outfile)]
        env=os.environ.copy();env.pop('PYTHONPATH',None)
        command=subprocess.run([sys.executable,str(script),*args],
                cwd=self.root,env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(command.returncode,0,command.stdout+command.stderr)
        self.assertEqual(json.loads(outfile.read_text())['status'],paired.STATUS)
        with self.assertRaises(FileExistsError):paired.main(args)

    def test_fail_closed_incomplete_evidence_writes_no_success_file(self):
        (self.guests['extra-poll']/'host-x11-transition-bracket-evidence.json').unlink()
        target=self.root/'missing.json'
        args=['--baseline-dir',str(self.guests['baseline']),
              '--extra-dir',str(self.guests['extra-poll']),
              '--baseline-nro',str(self.nros['baseline']),
              '--extra-nro',str(self.nros['extra-poll']),
              '--out',str(target)]
        with self.assertRaises(ValueError):paired.main(args)
        self.assertFalse(target.exists())


if __name__=='__main__':
    unittest.main()
