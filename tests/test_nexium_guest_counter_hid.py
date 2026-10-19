"""Stage 234 real libnx guest-ZR evidence verifier, not HID emulation.

Static CSV fixtures validate the fail-closed grammar ONLY. They are
not evidence that NeXium delivered a real controller event.
"""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from tools import verify_nexium_guest_counter_hid as verifier
from tools import nexium_counter_hid_press as host_zr

HEADER='phase,tick,player_hp,enemy_hp,windup,stun,cooldown,event_mask,hid_edge,pcm_nonzero,pcm_fnv64\n'
READY='READY,1,5,3,12,0,0,1,0,0,CBF29CE484222325\n'
SUCCESS='HID_COUNTER,2,5,3,0,9,48,2048,1,1,1169E164EDF5FD7D\n'


class GuestHidCounterVerifierTests(unittest.TestCase):
    def test_valid_fixture_parses_but_never_claims_hardware(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fake.csv'
            p.write_text(HEADER+READY+SUCCESS,encoding='ascii')
            result=verifier.verify(p)
            self.assertEqual(result['status'],
                             'GUEST_LIBNX_ZR_EDGE_AND_COUNTER_EFFECT_WITNESSED')
            self.assertTrue(result['controlled_ready_training_arena_only'])
            self.assertFalse(result['physical_controller_hardware_verified'])
            self.assertFalse(result['natural_combat_counter_window_verified'])
            self.assertFalse(result['audio_output_verified'])
            self.assertTrue(result['synthetic_pcm_verified'])
            self.assertEqual(result['counter_pcm_fnv64'],'1169E164EDF5FD7D')

    def test_verifier_rejects_missing_and_symlinked_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'absent.csv'
            with self.assertRaises(ValueError): verifier.verify(p)
            real=Path(d)/'real.csv'
            real.write_text(HEADER+READY+SUCCESS,encoding='ascii')
            p.symlink_to(real)
            with self.assertRaises(ValueError): verifier.verify(p)

    def test_rejects_attempt_without_guest_counter_game_event(self):
        for bad in (
            SUCCESS.replace(',2048,1,1,',',0,1,1,'),
            SUCCESS.replace(',2048,1,1,',',2048,0,1,'),
            SUCCESS.replace(',9,48,',',9,47,'),
            SUCCESS.replace(',5,3,',',4,3,'),
            SUCCESS.replace('HID_COUNTER','READY'),
            SUCCESS.replace(',2048,1,1,',',2048,1,0,'),
            SUCCESS.replace('1169E164EDF5FD7D','1169E164EDF5FD7C'),
            SUCCESS.replace('1169E164EDF5FD7D','1169e164edf5fd7d'),
            SUCCESS.replace('1169E164EDF5FD7D','CBF29CE484222325'),
        ):
            with self.subTest(bad=bad):
                with tempfile.TemporaryDirectory() as d:
                    p=Path(d)/'wrong.csv'
                    p.write_text(HEADER+READY+bad,encoding='ascii')
                    with self.assertRaises(ValueError):verifier.verify(p)

    def test_rejects_reordered_extra_or_noncanonical_rows(self):
        for contents in (
            HEADER+SUCCESS+READY,
            HEADER+READY,
            HEADER+READY+SUCCESS+SUCCESS,
            HEADER+READY.replace('READY,1,','READY,01,')+SUCCESS,
            HEADER.replace('hid_edge','raw_key')+READY+SUCCESS,
            HEADER+READY+SUCCESS.replace('2048','02048'),
        ):
            with self.subTest(case=contents[-45:]):
                with tempfile.TemporaryDirectory() as d:
                    p=Path(d)/'bad.csv'
                    p.write_text(contents,encoding='ascii')
                    with self.assertRaises(ValueError):verifier.verify(p)

    def test_main_reports_inconclusive_if_guest_file_absent(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'result.json'
            self.assertEqual(verifier.main([
                '--report',str(Path(d)/'absent.csv'),
                '--out',str(out)]),0)
            self.assertIn('INCONCLUSIVE_',out.read_text(encoding='ascii'))

    def test_host_t_mapping_attempt_only_after_stress_done(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            witness=root/'cadillacs-audio-stress.csv'
            witness.write_text('event,elapsed_ticks,'+'x'*95+'\n'+'STRESS_DONE,900,1\n',
                               encoding='ascii')
            self.assertTrue(host_zr.stress_complete([root]))
            with patch.object(host_zr.subprocess,'run') as run, \
                 patch.object(host_zr.time,'sleep'):
                result=host_zr.probe('12345',[root],timeout_seconds=0.5)
            self.assertEqual(result['status'],'HOST_ZR_KEY_ATTEMPT_AFTER_STRESS')
            keys=[call.args[0] for call in run.call_args_list]
            self.assertIn(['xdotool','keydown','t'],keys)
            self.assertIn(['xdotool','keyup','t'],keys)
            self.assertFalse(result['guest_hid_counter_verified'])

    def test_host_no_stress_never_sends_zr(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(host_zr.subprocess,'run') as run:
                result=host_zr.probe('12345',[root],timeout_seconds=0)
            self.assertEqual(result['status'],
                             'INCONCLUSIVE_NO_COMPLETED_GUEST_STRESS')
            run.assert_not_called()
            # A symlinked fake completion must never arm the host press.
            external=root/'outside.csv'
            external.write_text('STRESS_DONE,900,1\n',encoding='ascii')
            (root/'cadillacs-audio-stress.csv').symlink_to(external)
            self.assertFalse(host_zr.stress_complete([root]))

    def test_real_input_source_is_separate_from_scripted_guest_probe(self):
        source=Path('source/main.c').read_text(encoding='utf-8')
        self.assertIn('guest_counter_zr_edge_pending=true;',source)
        self.assertIn('(down&HidNpadButton_ZR)',source)
        self.assertIn('guest_audio_stress_done && guest_controller_done',source)
        self.assertIn('(step_pressed&DINO_ARENA_COUNTER)',source)
        self.assertIn('cadillacs-counter-hid.csv',source)
        runner=Path('tools/nexium_guest_replay_probe.sh').read_text(
            encoding='utf-8')
        self.assertIn('nexium_counter_hid_press.py',runner)
        self.assertIn('verify_nexium_guest_counter_hid.py',runner)


if __name__=='__main__':
    unittest.main()
