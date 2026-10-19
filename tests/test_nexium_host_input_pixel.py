"""Synthetic tests do not constitute evidence of host or guest latency."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import nexium_host_input_pixel as pixel
from tools import verify_nexium_host_input_bound as witness


class HostInputPixelContractTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(prefix='dino-x11-mock-')
        self.root = Path(self.t.name)
        self.host = self.root/'host.json'
        self.trace = self.root/'timeline.csv'
        self.controller = self.root/'controller.csv'
        self.out = self.root/'out.json'
        self.data = pixel.result(
            'HOST_PIXEL_CHANGE_OBSERVED_UNBOUND',
            host_capture_upper_bound_ms=213, capture_probes=7,
            baseline_reset_pixel_verified=True,
            baseline_background_pixel_verified=True,
        )
        self.save()
        self.trace.write_text(
            'event,tick,player_x,sparring,event_mask\n'
            'RESET,0,90,0,0\n'
            'MOVE,2,96,0,0\n'
            'ATTACK,40,184,0,8\n'
            'JUMP,60,184,0,2\n'
            'SPAR,80,184,1,1\n'
            'DONE,80,184,1,1\n',encoding='ascii',
        )
        self.controller.write_text(
            'event,flags,player_x,sparring\n'
            'RESET,1,90,0\n'
            'INPUT_DONE,31,184,1\n',encoding='ascii',
        )

    def tearDown(self):
        self.t.cleanup()

    def save(self):
        self.host.write_text(json.dumps(self.data), encoding='ascii')

    def test_real_contract_requires_two_independent_evidences(self):
        got = witness.verify(self.host, self.trace, self.controller)
        self.assertEqual(got['status'],
                         'HOST_KEY_TO_SAMPLED_WINDOW_PIXEL_BOUND_WITNESSED')
        self.assertEqual(got['host_window_upper_bound_ms'],213)
        self.assertEqual(got['host_sample_count'],7)
        self.assertTrue(got['bound_includes_host_capture_overhead'])
        self.assertFalse(got['physical_display_latency_verified'])
        self.assertFalse(got['hardware_input_to_photons_verified'])
        self.assertFalse(got['audio_latency_verified'])

    def test_hex_and_rgb_pixel_values(self):
        self.assertEqual(pixel.parse_color(
            '# ImageMagick pixel enumeration: 1,1,255,srgb\n'
            '0,0: (62,180,208) #3EB4D0 srgb(62,180,208)\n'),
            pixel.PLAYER_BLUE)
        self.assertEqual(pixel.parse_color(
            '0,0: (62,83,74) srgb(62,83,74)\n'),
            pixel.BACKGROUND)

    def test_pixel_parser_rejects_empty_duplicated_and_unexpected(self):
        for value in ('', 'x,y: rgb(0,0,0)',
                      '0,0: missing',
                      '0,0: (999,5,2)',
                      '0,0: (1,2,3)\n0,0: (1,2,3)'):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    pixel.parse_color(value)

    def test_bad_host_bound_and_count_fail_closed(self):
        for key, values in (
            ('host_capture_upper_bound_ms', (0,8001,-1,True,1.2,'200')),
            ('capture_probes', (0,81,-1,False,'3')),
        ):
            for value in values:
                with self.subTest(key=key,val=value):
                    self.data[key]=value
                    self.save()
                    with self.assertRaises(ValueError):
                        witness.verify(self.host,self.trace,self.controller)
            self.data[key]=213 if key=='host_capture_upper_bound_ms' else 7

    def test_no_raw_host_observation_does_not_pass(self):
        for status in ('INCONCLUSIVE_PIXEL_NOT_OBSERVED',
                       'INCONCLUSIVE_HOST_PIXEL_CAPTURE_UNAVAILABLE'):
            self.data['status']=status
            self.save()
            with self.assertRaises(ValueError):
                witness.verify(self.host,self.trace,self.controller)

    def test_forged_capabilities_and_baseline_flags_rejected(self):
        for flag in ('host_screen_sample_upper_bound_only',
                     'baseline_reset_pixel_verified',
                     'baseline_background_pixel_verified',
                     'guest_hid_binding_verified',
                     'physical_joycon_latency_verified',
                     'physical_display_latency_verified',
                     'audio_latency_verified'):
            with self.subTest(flag=flag):
                original=self.data[flag]
                self.data[flag]=not original
                self.save()
                with self.assertRaises(ValueError):
                    witness.verify(self.host,self.trace,self.controller)
                self.data[flag]=original

    def test_guest_trace_mismatch_refuses_host_measurement(self):
        self.controller.write_text(
            'event,flags,player_x,sparring\n'
            'RESET,1,90,0\n'
            'INPUT_DONE,31,200,1\n',encoding='ascii')
        with self.assertRaises(ValueError):
            witness.verify(self.host,self.trace,self.controller)

    def test_missing_host_trace_refused(self):
        self.host.unlink()
        with self.assertRaises(ValueError):
            witness.verify(self.host,self.trace,self.controller)

    def test_oversized_symlink_and_malformed_input_refused(self):
        self.host.write_bytes(b'Z'*2049)
        with self.assertRaises(ValueError):
            witness.verify(self.host,self.trace,self.controller)
        self.host.unlink()
        other=self.root/'other.json'
        other.write_text('{}', encoding='ascii')
        self.host.symlink_to(other)
        with self.assertRaises(ValueError):
            witness.verify(self.host,self.trace,self.controller)

    def test_cli_missing_guest_is_inconclusive_not_success(self):
        self.trace.unlink()
        self.assertEqual(witness.main([
            '--host',str(self.host),'--timeline',str(self.trace),
            '--controller',str(self.controller),'--out',str(self.out)]),0)
        data=json.loads(self.out.read_text())
        self.assertEqual(data['status'],
                         'INCONCLUSIVE_NO_BOUND_AND_GUEST_HID_BINDING')
        self.assertFalse(data['hardware_input_to_photons_verified'])
        self.assertNotIn(str(self.trace),self.out.read_text())

    def test_direct_cli_invocation_works_without_repo_import_path(self):
        script=Path(__file__).resolve().parents[1] / \
            'tools' / 'verify_nexium_host_input_bound.py'
        res=subprocess.run([
            sys.executable,str(script),'--host',str(self.host),
            '--timeline',str(self.trace),'--controller',str(self.controller),
            '--out',str(self.out)], cwd=self.root, text=True,
            capture_output=True,check=False)
        self.assertEqual(res.returncode,0,res.stderr)
        self.assertEqual(json.loads(self.out.read_text())['status'],
                         'HOST_KEY_TO_SAMPLED_WINDOW_PIXEL_BOUND_WITNESSED')

    def test_invalid_window_id_fails_before_host_operations(self):
        for value in ('', '-4', '0', 'not_an_xid',str(2**32)):
            with self.subTest(value=value),self.assertRaises(ValueError):
                pixel.probe(value)


if __name__=='__main__':
    unittest.main()
