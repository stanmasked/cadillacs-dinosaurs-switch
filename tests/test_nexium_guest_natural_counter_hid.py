"""Stage 244 optional NeXium natural AI ZR/PCM grammar checks.

Synthetic fixtures exercise fail-closed parsers; NEVER equate them with
an actual guest libnx input or natural-telegraph hardware proof.
"""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_nexium_guest_natural_counter_hid as verifier
from tools import nexium_natural_counter_hid_press as host

HEADER=(','.join(verifier.COLUMNS)+'\n')


def row(tick):
    return ('NATURAL_HID_COUNTER,'+str(tick)+
            ',90,134,'+str(129-tick)+
            ',5,3,0,9,48,2048,1,1,1169E164EDF5FD7D\n')


class GuestNaturalHidCounterTests(unittest.TestCase):
    def test_earliest_and_last_natural_windup_edge_exact(self):
        with tempfile.TemporaryDirectory() as d:
            for tick in (117,118,126,128):
                with self.subTest(tick=tick):
                    path=Path(d)/'natural.csv'
                    path.write_text(HEADER+row(tick),encoding='ascii')
                    result=verifier.verify(path)
                    self.assertEqual(result['counter_impact_tick'],tick)
                    self.assertEqual(result['counter_pre_windup'],129-tick)
                    self.assertTrue(result['guest_libnx_zr_edge_bound_to_counter_event'])
                    self.assertFalse(result['live_player_arena_input_verified'])
                    self.assertFalse(result['physical_joycon_verified'])
                    self.assertFalse(result['hardware_audio_output_verified'])

    def test_missing_late_early_duplicated_malformed_and_pcm_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'counter.csv'
            valid=HEADER+row(117)
            for raw in (
                '',
                HEADER,
                HEADER+row(116),
                HEADER+row(129),
                valid+row(117),
                valid.replace(',12,5,3,',',11,5,3,'),
                valid.replace(',90,134,',',91,134,'),
                valid.replace(',90,134,',',90,135,'),
                valid.replace(',2048,1,1,',',0,1,1,'),
                valid.replace(',2048,1,1,',',2048,0,1,'),
                valid.replace('1169E164EDF5FD7D','1169E164EDF5FD7C'),
                valid.replace('1169E164EDF5FD7D','1169e164edf5fd7d'),
                valid.replace('NATURAL_HID_COUNTER,117,',
                              'NATURAL_HID_COUNTER,0117,'),
                valid.replace('event,tick,','event,raw_input,'),
            ):
                with self.subTest(raw=raw[-64:]):
                    path.write_text(raw,encoding='ascii')
                    with self.assertRaises(ValueError):
                        verifier.verify(path)
            path.unlink()
            with self.assertRaises(ValueError):
                verifier.verify(path)
            real=Path(d)/'real.csv'
            real.write_text(valid,encoding='ascii')
            path.symlink_to(real)
            with self.assertRaises(ValueError):
                verifier.verify(path)

    def test_missing_guest_evidence_is_inconclusive_and_nonblocking(self):
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'result.json'
            self.assertEqual(verifier.main([
                '--report',str(Path(d)/'absent.csv'),
                '--out',str(out)]),0)
            self.assertIn(
                'INCONCLUSIVE_NO_GENUINE_UNSTAGED_GUEST_ZR_COUNTER',
                out.read_text(encoding='ascii'))

    def test_host_requires_exact_complete_marker_before_second_key(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            marker=root/host.READY_FILE
            with patch.object(host.subprocess,'run') as key:
                self.assertEqual(
                    host.probe('123',[root],timeout_seconds=0)['status'],
                    'INCONCLUSIVE_NO_COMPLETE_NATURAL_READY_MARKER')
                key.assert_not_called()
            for raw in (
                host.READY_BYTES[:-2],
                host.READY_BYTES.replace(b',134,12,',b',134,11,'),
                host.READY_BYTES+b'FAKE\n',
            ):
                marker.write_bytes(raw)
                self.assertFalse(host.natural_ready([root]))
            marker.write_bytes(host.READY_BYTES)
            self.assertTrue(host.natural_ready([root]))
            with patch.object(host.subprocess,'run') as key, \
                 patch.object(host.time,'sleep'):
                outcome=host.probe('123',[root],timeout_seconds=0.5)
            self.assertEqual(
                outcome['status'],
                'HOST_SECOND_ZR_ATTEMPT_AT_NATURAL_WINDUP')
            self.assertFalse(outcome['guest_natural_counter_verified'])
            commands=[call.args[0] for call in key.call_args_list]
            self.assertIn(['xdotool','keydown','t'],commands)
            self.assertIn(['xdotool','keyup','t'],commands)

    def test_symlinked_host_marker_never_arms_zr(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            target=root/'elsewhere'
            target.write_bytes(host.READY_BYTES)
            (root/host.READY_FILE).symlink_to(target)
            self.assertFalse(host.natural_ready([root]))

    def test_source_and_guest_ci_require_independent_real_zr_path(self):
        main=Path('source/main.c').read_text(encoding='utf-8')
        for required in (
            'cadillacs-natural-counter-ready.csv',
            'cadillacs-natural-counter-hid.csv',
            'guest_natural_counter.ticks==116u',
            'guest_counter_zr_edge_pending &&',
            '(step_pressed&DINO_ARENA_COUNTER)!=0u',
            'dino_arena_reset(&guest_natural_counter)',
        ):
            self.assertIn(required,main)
        self.assertNotIn('guest_natural_counter.x=220',main)
        self.assertNotIn('guest_natural_counter.dummy_windup=12',main)
        runner=Path('tools/nexium_guest_replay_probe.sh').read_text(
            encoding='utf-8')
        self.assertIn('nexium_natural_counter_hid_press.py',runner)
        self.assertIn('verify_nexium_guest_natural_counter_hid.py',runner)
        workflow=Path('.github/workflows/nexium-guest-replay.yml').read_text(
            encoding='utf-8')
        self.assertIn('guest-natural-counter-hid-evidence.json',workflow)


if __name__=='__main__':
    unittest.main()
