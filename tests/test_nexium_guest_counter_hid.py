"""Stage 234 real libnx guest-ZR evidence verifier, not HID emulation.

Static CSV fixtures validate the fail-closed grammar ONLY. They are
not evidence that NeXium delivered a real controller event.
"""
import tempfile
from pathlib import Path
import unittest

from tools import verify_nexium_guest_counter_hid as verifier

HEADER='phase,tick,player_hp,enemy_hp,windup,stun,cooldown,event_mask,hid_edge\n'
READY='READY,1,5,3,12,0,0,1,0\n'
SUCCESS='HID_COUNTER,2,5,3,0,9,48,2048,1\n'


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
            SUCCESS.replace(',2048,1',',0,1'),
            SUCCESS.replace(',2048,1',',2048,0'),
            SUCCESS.replace(',9,48,',',9,47,'),
            SUCCESS.replace(',5,3,',',4,3,'),
            SUCCESS.replace('HID_COUNTER','READY'),
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
