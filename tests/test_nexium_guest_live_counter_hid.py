"""Synthetic parser and input-guard regressions for Stage 246.

Fixtures never prove NeXium delivered controller input. The separate
guest CI job must write a real source-side `LIVE_HID_COUNTER` CSV.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_nexium_guest_live_counter_hid as checker
from tools import nexium_live_counter_hid_press as host

HEADER=','.join(checker.FIELDS)+'\n'


def row(tick):
    return ('LIVE_HID_COUNTER,'+str(tick)+',90,134,'+str(129-tick)+
            ',5,3,0,9,48,2048,1,1,1169E164EDF5FD7D\n')


class GuestVisibleArenaTests(unittest.TestCase):
    def test_full_legal_windup_in_visible_arena(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'arena.csv'
            for tick in (117,118,119,127,128):
                with self.subTest(tick=tick):
                    p.write_text(HEADER+row(tick),encoding='ascii')
                    proof=checker.verify(p)
                    self.assertEqual(proof['status'],checker.STATUS)
                    self.assertEqual(proof['counter_impact_relative_tick'],tick)
                    self.assertTrue(proof['live_rendered_arena_game_state_verified'])
                    self.assertTrue(proof['real_guest_y_reset_required'])
                    self.assertTrue(proof['real_guest_x_spar_toggle_required'])
                    for key in ('physical_joycon_verified',
                                'hardware_display_pixels_at_counter_verified',
                                'audible_speaker_sound_verified',
                                'input_latency_verified'):
                        self.assertFalse(proof[key])

    def test_late_early_corrupt_pcm_and_unauthorized_states_rejected(self):
        valid=HEADER+row(117)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'arena.csv'
            cases=(
                '',
                HEADER,
                HEADER+row(116),
                HEADER+row(129),
                valid+row(117),
                valid.replace('LIVE_HID_COUNTER','NATURAL_HID_COUNTER'),
                valid.replace(',90,134,',',91,134,'),
                valid.replace(',90,134,',',90,135,'),
                valid.replace(',12,5,3,',',11,5,3,'),
                valid.replace(',2048,1,1,',',0,1,1,'),
                valid.replace(',2048,1,1,',',2048,0,1,'),
                valid.replace('1169E164EDF5FD7D','1169E164EDF5FD7C'),
                valid.replace('1169E164EDF5FD7D','1169e164edf5fd7d'),
                valid.replace('LIVE_HID_COUNTER,117,','LIVE_HID_COUNTER,0117,'),
                valid.replace('event,tick,','event,host_key,'),
            )
            for bad in cases:
                with self.subTest(value=bad[-35:]):
                    p.write_text(bad,encoding='ascii')
                    with self.assertRaises(ValueError):
                        checker.verify(p)

    def test_missing_or_linked_guest_csv_is_never_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'absent.csv'
            with self.assertRaises(ValueError):
                checker.verify(p)
            target=Path(directory)/'elsewhere.csv'
            target.write_text(HEADER+row(117),encoding='ascii')
            p.symlink_to(target)
            with self.assertRaises(ValueError):
                checker.verify(p)

    def test_missing_guest_report_yields_explicit_optional_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory)
            output=d/'verdict.json'
            self.assertEqual(checker.main([
                '--report',str(d/'missing.csv'),
                '--out',str(output)]),0)
            verdict=json.loads(output.read_text(encoding='ascii'))
            self.assertEqual(verdict['status'],
                             'INCONCLUSIVE_NO_LIVE_GUEST_NATURAL_ZR_COUNTER')
            self.assertFalse(verdict['live_rendered_arena_game_state_verified'])

    def test_host_refuses_reset_and_zr_without_prior_real_natural_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(host.subprocess,'run') as calls:
                result=host.probe('123',[Path(directory)],natural_seconds=0)
            self.assertEqual(result['status'],
                             'INCONCLUSIVE_NO_PRIOR_GUEST_NATURAL_ZR')
            calls.assert_not_called()

    def test_host_sends_real_y_x_t_in_sequence_only_after_guest_markers(self):
        with patch.object(host,'until',side_effect=[True,True]) as preflight, \
             patch.object(host.subprocess,'run') as keys, \
             patch.object(host.time,'sleep'):
            report=host.probe('123',[Path('/tmp')],natural_seconds=1,
                              ready_seconds=1)
        self.assertEqual(preflight.call_count,2)
        self.assertEqual(report['status'],
                         'HOST_LIVE_SCENE_ZR_ATTEMPT_AFTER_REAL_Y_X')
        self.assertFalse(report['guest_live_counter_verified'])
        commands=[call.args[0] for call in keys.call_args_list]
        self.assertLess(commands.index(['xdotool','keydown','z']),
                        commands.index(['xdotool','keydown','v']))
        self.assertLess(commands.index(['xdotool','keydown','v']),
                        commands.index(['xdotool','keydown','t']))
        with patch.object(host,'until',side_effect=[True,False]), \
             patch.object(host.subprocess,'run') as keys, \
             patch.object(host.time,'sleep'):
            result=host.probe('123',[Path('/tmp')],natural_seconds=1,
                              ready_seconds=1)
        self.assertEqual(result['status'],
                         'INCONCLUSIVE_NO_LIVE_ARENA_WINDUP_MARKER')
        self.assertNotIn(['xdotool','keydown','t'],
                         [c.args[0] for c in keys.call_args_list])

    def test_source_workflow_preserves_evidence_and_no_manual_ai_setup(self):
        src=Path('source/main.c').read_text(encoding='utf-8')
        block=src.split('/* Stage 246: real X sparring',1)[1].split(
            'if (guest_controller_active && !demo_active)',1)[0]
        self.assertIn('guest_live_spar_origin=arena.ticks',block)
        self.assertIn('relative_tick==116u',block)
        self.assertIn('live_before.dummy_windup==129u-relative_tick',block)
        self.assertIn('arena.events==DINO_EVT_COUNTER',block)
        self.assertIn('sdmc:/cadillacs-live-counter-hid.csv',block)
        self.assertNotIn('arena.dummy_windup=12',block)
        self.assertNotIn('arena.x=220',block)
        self.assertNotIn('dino_arena_reset(&arena)',block)
        shell=Path('tools/nexium_guest_replay_probe.sh').read_text(
            encoding='utf-8')
        self.assertIn('nexium_live_counter_hid_press.py',shell)
        self.assertIn('verify_nexium_guest_live_counter_hid.py',shell)
        workflow=Path('.github/workflows/nexium-guest-replay.yml').read_text(
            encoding='utf-8')
        self.assertIn('guest-live-counter-hid-evidence.json',workflow)


if __name__=='__main__':
    unittest.main()
