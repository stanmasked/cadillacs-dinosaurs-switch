#!/usr/bin/env python3
"""Observe host PulseAudio monitor response to an actual NeXium X/spar key.

CI-only, ROM-free prototype. The host clock spans sending xdotool 'v' and
reading PCM from the private PulseAudio monitor stream. The measured time
is a coarse *sampled host read completion upper bound* with recorder,
scheduling, emulator, audout, server and pipe overhead. It does NOT measure
actual speaker playback, QSound parity or physical Switch audio latency.

Never record or upload PCM, host absolute timestamps, keyboard history,
paths, firmware, keys, game resources or user-owned ROM samples.
"""
import argparse
from array import array
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import time

RATE = 48000
MIN_BASELINE_FRAMES = 2400
THRESHOLD = 180
MIN_SIGNAL_FRAMES = 20
BASELINE_SECONDS = 0.40
MAX_OBSERVE_SECONDS = 2.0
MAX_OBSERVE_MS = 4000
WINDOW_SAMPLE_MAX = 65536
PCM_FORMAT = 's16le-stereo-48000'


def record(status, **kwargs):
    return {
        'schema': 'dino-nexium-spar-host-audio-v1',
        'status': status,
        'measurement_type': 'host_spar_key_to_first_sampled_pulse_monitor_pcm',
        'audio_upper_bound_only': True,
        'true_pcm_onset_verified': False,
        'physical_speaker_latency_verified': False,
        'physical_switch_audio_latency_verified': False,
        'original_arcade_audio_verified': False,
        **kwargs,
    }


def parse_pcm(data):
    """Return (stereo_frames, frames_with_meaningful_signal), no samples saved."""
    if len(data) % 4:
        raise ValueError('partial stereo frame')
    samples = array('h')
    samples.frombytes(data)
    if sys.byteorder != 'little':
        samples.byteswap()
    count = 0
    for i in range(0, len(samples), 2):
        if max(abs(samples[i]), abs(samples[i + 1])) >= THRESHOLD:
            count += 1
    return len(data) // 4, count


def send_spar():
    """Send the same published keyboard binding used by the guest HID test."""
    subprocess.run(['xdotool', 'keydown', 'v'], check=True,
                   capture_output=True, timeout=4)
    try:
        time.sleep(0.25)
    finally:
        subprocess.run(['xdotool', 'keyup', 'v'], check=False,
                       capture_output=True, timeout=4)


def _consume(proc, max_wait=0.03):
    if proc.poll() is not None:
        raise OSError('Pulse monitor process quit')
    ready, _, _ = select.select([proc.stdout], [], [], max_wait)
    if not ready:
        return 0, 0
    data = os.read(proc.stdout.fileno(), WINDOW_SAMPLE_MAX)
    if not data:
        raise OSError('no data from Pulse monitor')
    return parse_pcm(data)


def measure():
    proc = None
    sent = False
    try:
        proc = subprocess.Popen(
            ['parec', '--raw', '--format=s16le', '--rate=48000',
             '--channels=2', '--device=dino_ci_sink.monitor',
             '--latency-msec=10'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
        start = time.monotonic()
        baseline_frames = 0
        baseline_strong = 0
        while time.monotonic() - start < BASELINE_SECONDS:
            frames, strong = _consume(proc)
            baseline_frames += frames
            baseline_strong += strong
        if baseline_frames < MIN_BASELINE_FRAMES or baseline_strong:
            # Do not mistake leftover jump/landing SFX or Pulse startup for
            # the spark/spar marker: fail closed but still deliver the key.
            send_spar()
            sent = True
            return record('INCONCLUSIVE_NO_QUIET_BASELINE',
                          baseline_quiet=False)
        start_ns = time.monotonic_ns()
        # Timestamp is BEFORE host key-dispatch, not a guest sound event.
        subprocess.run(['xdotool', 'keydown', 'v'], check=True,
                       capture_output=True, timeout=4)
        sent = True
        pressed = True
        count = 0
        strong_count = 0
        deadline = time.monotonic() + MAX_OBSERVE_SECONDS
        release_ns = start_ns + 250_000_000
        try:
            while time.monotonic() < deadline:
                if pressed and time.monotonic_ns() >= release_ns:
                    subprocess.run(['xdotool', 'keyup', 'v'], check=False,
                                   capture_output=True, timeout=4)
                    pressed = False
                frames, strong = _consume(proc)
                if frames:
                    count += 1
                    strong_count += strong
                    if strong_count >= MIN_SIGNAL_FRAMES:
                        elapsed_ms = (time.monotonic_ns() - start_ns + 999_999)//1_000_000
                        if not 1 <= elapsed_ms <= MAX_OBSERVE_MS:
                            raise ValueError('monitor observation outside bounds')
                        return record(
                            'HOST_SPAR_PCM_OBSERVED_UNBOUND',
                            host_monitor_read_upper_bound_ms=int(elapsed_ms),
                            monitor_read_chunks=count,
                            baseline_quiet=True,
                            format=PCM_FORMAT)
            return record('INCONCLUSIVE_NO_POST_KEY_PCM',
                          baseline_quiet=True)
        finally:
            if pressed:
                # Preserve the actual guest HID key-up even on errors.
                wait_ns = release_ns - time.monotonic_ns()
                if wait_ns > 0:
                    time.sleep(wait_ns / 1_000_000_000)
                subprocess.run(['xdotool', 'keyup', 'v'], check=False,
                               capture_output=True, timeout=4)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        # No exception text goes into evidence; it may include private paths.
        return record('INCONCLUSIVE_AUDIO_MONITOR_UNAVAILABLE')
    finally:
        if not sent:
            # A missing monitoring backend must never suppress the spar
            # command required by the already-proven guest HID test.
            try:
                send_spar()
            except (OSError, subprocess.SubprocessError):
                pass
        if proc is not None:
            if proc.poll() is None:
                proc.terminate()
            try:
                proc.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args(argv)
    result = measure()
    args.out.write_text(json.dumps(result, sort_keys=True) + '\n',
                        encoding='ascii')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
