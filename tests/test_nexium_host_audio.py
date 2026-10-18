"""Synthetic tests for *host* virtual-sink recording inspection.

Artificial raw PCM fixtures are NEVER evidence that NeXium rendered audio.
"""
from array import array
from pathlib import Path
import json
import tempfile
import unittest

from tools import verify_nexium_host_audio as monitor


class HostAudioMonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='dino-fake-host-monitor-')
        self.raw = Path(self.tmp.name) / 'mock.raw'

    def tearDown(self):
        self.tmp.cleanup()

    def write_pcm(self, amplitude=500, windows=(0, 2, 4),
                  frames_per_window=800, low_noise=0):
        total = 6 * monitor.WINDOW_FRAMES
        samples = array('h', [low_noise]) * (total * 2)
        for window in windows:
            for frame in range(window * monitor.WINDOW_FRAMES,
                               window * monitor.WINDOW_FRAMES + frames_per_window):
                samples[2 * frame] = amplitude
                samples[2 * frame + 1] = -amplitude
        if __import__('sys').byteorder != 'little':
            samples.byteswap()
        self.raw.write_bytes(samples.tobytes())

    def test_multiple_non_silent_windows_detect_host_monitor_signal(self):
        self.write_pcm()
        result = monitor.inspect(self.raw)
        self.assertEqual(result['status'], 'VIRTUAL_SINK_PCM_DETECTED')
        self.assertTrue(result['virtual_sink_pcm_detected'])
        self.assertEqual(result['peak_absolute_sample'], 500)
        self.assertEqual(result['active_100ms_windows'], 3)
        self.assertEqual(result['above_threshold_frames'], 2400)
        self.assertFalse(result['physical_speaker_audio_verified'])
        self.assertFalse(result['arcade_audio_parity_verified'])

    def test_silent_monitor_is_not_audio_evidence(self):
        self.write_pcm(windows=())
        result = monitor.inspect(self.raw)
        self.assertFalse(result['virtual_sink_pcm_detected'])
        self.assertEqual(result['peak_absolute_sample'], 0)

    def test_low_amplitude_and_spike_do_not_count_as_signal(self):
        self.write_pcm(amplitude=149)
        self.assertFalse(monitor.inspect(self.raw)['virtual_sink_pcm_detected'])
        self.write_pcm(windows=(2,), frames_per_window=100)
        self.assertFalse(monitor.inspect(self.raw)['virtual_sink_pcm_detected'])
        self.write_pcm(windows=(0, 1, 2), frames_per_window=100)
        self.assertFalse(monitor.inspect(self.raw)['virtual_sink_pcm_detected'])

    def test_three_windows_with_enough_samples_detect_signal(self):
        self.write_pcm(windows=(1, 3, 5), frames_per_window=160)
        result = monitor.inspect(self.raw)
        self.assertTrue(result['virtual_sink_pcm_detected'])
        self.assertEqual(result['above_threshold_frames'], 480)

    def test_bad_sizes_refused_without_reading_samples(self):
        for data in (b'', b'\x00', b'\x01\x02\x03',
                     b'\x00' * 5):
            with self.subTest(length=len(data)):
                self.raw.write_bytes(data)
                with self.assertRaises(ValueError):
                    monitor.inspect(self.raw)
        with self.raw.open('wb') as output:
            output.truncate(monitor.MAX_BYTES + 4)
        with self.assertRaises(ValueError):
            monitor.inspect(self.raw)

    def test_missing_and_symlinked_capture_refused(self):
        with self.assertRaises(ValueError):
            monitor.inspect(self.raw)
        self.write_pcm()
        target = Path(self.tmp.name) / 'alias.raw'
        try:
            target.symlink_to(self.raw)
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(ValueError):
            monitor.inspect(target)

    def test_cli_invalid_input_gives_path_free_inconclusive_json(self):
        out = Path(self.tmp.name) / 'status.json'
        self.assertEqual(monitor.main([
            '--raw', str(self.raw), '--out', str(out)
        ]), 0)
        report = json.loads(out.read_text())
        self.assertEqual(report['status'], 'INCONCLUSIVE_CAPTURE_UNAVAILABLE')
        self.assertFalse(report['virtual_sink_pcm_detected'])
        self.assertNotIn(str(self.raw), out.read_text())

    def test_cli_signal_report_is_not_audibility_claim(self):
        self.write_pcm()
        out = Path(self.tmp.name) / 'status.json'
        self.assertEqual(monitor.main([
            '--raw', str(self.raw), '--out', str(out)
        ]), 0)
        report = json.loads(out.read_text())
        self.assertTrue(report['virtual_sink_pcm_detected'])
        self.assertFalse(report['physical_speaker_audio_verified'])
        self.assertFalse(report['arcade_audio_parity_verified'])


if __name__ == '__main__':
    unittest.main()
