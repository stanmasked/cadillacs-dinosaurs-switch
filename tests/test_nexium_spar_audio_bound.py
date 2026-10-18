"""ROM-free synthetic fixtures for Pulse monitor spar-response evidence."""
import json
import math
import struct
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import nexium_host_spar_audio as pulse
from tools import verify_nexium_spar_audio_bound as verifier


class SparAudioResponseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='dino-spar-sound-fixture-')
        self.root = Path(self.tmp.name)
        self.host = self.root / 'monitor.json'
        self.timeline = self.root / 'timeline.csv'
        self.controller = self.root / 'controller.csv'
        self.out = self.root / 'summary.json'
        self.value = pulse.record('HOST_SPAR_530HZ_PCM_OBSERVED_UNBOUND',
                                  host_monitor_read_upper_bound_ms=185,
                                  monitor_read_chunks=3,
                                  baseline_quiet=True,
                                  tone_reference_hz=530,
                                  tone_coherence_milli=980,
                                  format='s16le-stereo-48000')
        self.save()
        self.timeline.write_text(
            'event,tick,player_x,sparring,event_mask\n'
            'RESET,0,90,0,0\n'
            'MOVE,25,96,0,0\n'
            'ATTACK,80,184,0,8\n'
            'JUMP,115,184,0,2\n'
            'SPAR,151,184,1,1\n'
            'DONE,151,184,1,1\n', encoding='ascii')
        self.controller.write_text(
            'event,flags,player_x,sparring\n'
            'RESET,1,90,0\n'
            'INPUT_DONE,31,184,1\n', encoding='ascii')

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        self.host.write_text(json.dumps(self.value), encoding='ascii')

    def test_valid_host_monitor_and_actual_guest_spar(self):
        v = verifier.verify(self.host, self.timeline, self.controller)
        self.assertEqual(v['status'], 'GUEST_SPAR_AND_530HZ_MONITOR_TONE_OBSERVED')
        self.assertEqual(v['host_monitor_read_upper_bound_ms'], 185)
        self.assertEqual(v['host_monitor_read_chunks'], 3)
        self.assertTrue(v['host_read_and_pipe_overhead_included'])
        self.assertFalse(v['physical_switch_audio_latency_verified'])
        self.assertFalse(v['physical_speaker_latency_verified'])
        self.assertFalse(v['audible_sound_verified'])

    def test_little_endian_pcm_parser_and_threshold(self):
        # Signed stereo samples: exactly two of four frames exceed threshold.
        frames = [[0, 0], [180, -2], [-181, 7], [12, 23]]
        import struct
        raw = b''.join(struct.pack('<hh', *f) for f in frames)
        self.assertEqual(pulse.parse_pcm(raw), (4, 2))
        self.assertEqual(pulse.parse_pcm(b'\x00' * 32), (8, 0))

    def test_reject_truncated_stereo_pcm(self):
        for raw in (b'\x01', b'\x01\x02', b'\x01\x02\x03',
                    b'\x00' * 5):
            with self.subTest(length=len(raw)),self.assertRaises(ValueError):
                pulse.parse_pcm(raw)

    def test_requires_quiet_baseline_and_observed_post_event_pcm(self):
        for value in ('INCONCLUSIVE_NO_QUIET_BASELINE',
                      'INCONCLUSIVE_NO_POST_KEY_PCM',
                      'INCONCLUSIVE_AUDIO_MONITOR_UNAVAILABLE',
                      'INCONCLUSIVE_NOT_530HZ_SPAR_TONE'):
            with self.subTest(value=value):
                self.value['status'] = value
                self.save()
                with self.assertRaises(ValueError):
                    verifier.verify(self.host, self.timeline, self.controller)
        self.value['status'] = 'HOST_SPAR_530HZ_PCM_OBSERVED_UNBOUND'
        self.value['baseline_quiet'] = False
        self.save()
        with self.assertRaises(ValueError):
            verifier.verify(self.host, self.timeline, self.controller)

    def test_timestamp_and_sample_bound_checks(self):
        for field, options in (
            ('host_monitor_read_upper_bound_ms', (0, -1, 4001, 2.3, True, '150')),
            ('monitor_read_chunks', (0, -1, 513, True, 2.0, '2')),
        ):
            for value in options:
                with self.subTest(field=field, value=value):
                    previous = self.value[field]
                    self.value[field] = value
                    self.save()
                    with self.assertRaises(ValueError):
                        verifier.verify(self.host, self.timeline, self.controller)
                    self.value[field] = previous

    def test_forged_latency_and_arcade_parity_flags_fail(self):
        for field in ('audio_upper_bound_only', 'true_pcm_onset_verified',
                      'physical_speaker_latency_verified',
                      'physical_switch_audio_latency_verified',
                      'original_arcade_audio_verified'):
            with self.subTest(field=field):
                old = self.value[field]
                self.value[field] = not old
                self.save()
                with self.assertRaises(ValueError):
                    verifier.verify(self.host, self.timeline, self.controller)
                self.value[field] = old

    def test_matching_530hz_tone_and_rejection_of_other_tones(self):
        def make_pcm(hz):
            wave = []
            for i in range(pulse.TONE_WINDOW_FRAMES):
                # The production synth emits a roughly triangular tone;
                # the fundamental also dominates this simple sine fixture.
                v = round(1100*math.sin(2*math.pi*hz*i/pulse.RATE))
                wave.append(struct.pack('<hh',v,v))
            return b''.join(wave)
        good = pulse.spar_tone_coherence(make_pcm(530))
        wrong = pulse.spar_tone_coherence(make_pcm(260))
        self.assertGreater(good, 0.85)
        self.assertLess(wrong, 0.10)
        self.assertEqual(pulse.spar_tone_coherence(b'\x00' *
                         (pulse.TONE_WINDOW_FRAMES*4)),0.0)
        with self.assertRaises(ValueError):
            pulse.spar_tone_coherence(b'\x00'*8)

    def test_forged_spar_frequency_or_coherence_fails_closed(self):
        for field, vals in (('tone_reference_hz',(529,531,True,'530')),
                            ('tone_coherence_milli',(599,-1,1001,True,700.0))):
            for value in vals:
                with self.subTest(field=field,value=value):
                    old = self.value[field]
                    self.value[field] = value
                    self.save()
                    with self.assertRaises(ValueError):
                        verifier.verify(self.host,self.timeline,self.controller)
                    self.value[field] = old

    def test_missing_guest_timeline_refuses_host_pcm(self):
        self.timeline.unlink()
        with self.assertRaises(ValueError):
            verifier.verify(self.host, self.timeline, self.controller)

    def test_disagreement_in_guest_final_position_refuses_pcm(self):
        self.controller.write_text(
            'event,flags,player_x,sparring\nRESET,1,90,0\n'
            'INPUT_DONE,31,200,1\n', encoding='ascii')
        with self.assertRaises(ValueError):
            verifier.verify(self.host, self.timeline, self.controller)

    def test_missing_oversized_and_symlinked_monitor_refused(self):
        self.host.unlink()
        with self.assertRaises(ValueError):
            verifier.verify(self.host, self.timeline, self.controller)
        self.host.write_bytes(b'Z'*2049)
        with self.assertRaises(ValueError):
            verifier.verify(self.host, self.timeline, self.controller)
        self.host.unlink()
        p=self.root/'alias.json'
        p.write_text(json.dumps(self.value), encoding='ascii')
        self.host.symlink_to(p)
        with self.assertRaises(ValueError):
            verifier.verify(self.host, self.timeline, self.controller)

    def test_monitor_missing_still_delivers_guest_spar_key(self):
        # A broken PulseAudio recorder must not suppress the V key
        # required by the separate ROM-free native-HID check.
        with patch.object(pulse.subprocess, 'Popen',
                          side_effect=OSError('no monitor')), \
             patch.object(pulse, 'send_spar') as spar:
            result = pulse.measure()
        self.assertEqual(result['status'],
                         'INCONCLUSIVE_AUDIO_MONITOR_UNAVAILABLE')
        self.assertFalse(result['physical_speaker_latency_verified'])
        spar.assert_called_once_with()

    def test_direct_cli_valid_and_inconclusive_paths(self):
        script = Path(__file__).resolve().parents[1] / \
            'tools' / 'verify_nexium_spar_audio_bound.py'
        args = [sys.executable, str(script), '--host', str(self.host),
                '--timeline', str(self.timeline),
                '--controller', str(self.controller),
                '--out', str(self.out)]
        res = subprocess.run(args, cwd=self.root, capture_output=True,
                             text=True, check=False)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(self.out.read_text())['status'],
                         'GUEST_SPAR_AND_HOST_PCM_RESPONSE_OBSERVED')
        self.timeline.unlink()
        res = subprocess.run(args, cwd=self.root, capture_output=True,
                             text=True, check=False)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(self.out.read_text())['status'],
                         'INCONCLUSIVE_NO_BOUND_SPAR_MONITOR_RESPONSE')
        self.assertNotIn(str(self.root), self.out.read_text())


if __name__ == '__main__':
    unittest.main()
