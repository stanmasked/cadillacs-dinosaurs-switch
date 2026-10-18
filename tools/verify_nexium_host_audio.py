#!/usr/bin/env python3
"""Inspect an isolated *host* PulseAudio monitor recording, never gameplay audio.

The input is raw 48 kHz stereo signed-16 little-endian PCM sampled by
parec from a private null sink. A detectable signal proves only that the
host virtual monitor produced non-silent PCM, NOT audible loudspeaker
output, original arcade audio or any particular guest cue identity.
"""
import argparse
from array import array
import json
from pathlib import Path
import sys

RATE = 48000
CHANNELS = 2
WINDOW_FRAMES = RATE // 10
MAX_BYTES = 32 * 1024 * 1024
MIN_PEAK = 150
MIN_NONZERO_FRAMES = 480
MIN_ACTIVE_WINDOWS = 3


def inspect(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('monitor capture unavailable')
    size = path.stat().st_size
    if size < 4 or size > MAX_BYTES or size % 4:
        raise ValueError('monitor capture size invalid')
    frames = size // 4
    active = set()
    strong_frames = 0
    peak = 0
    cursor = 0
    with path.open('rb') as source:
        while True:
            block = source.read(64 * 1024)
            if not block:
                break
            if len(block) % 4:
                raise ValueError('partial interleaved stereo sample')
            samples = array('h')
            samples.frombytes(block)
            if sys.byteorder != 'little':
                samples.byteswap()
            for i in range(0, len(samples), 2):
                left, right = abs(samples[i]), abs(samples[i+1])
                level = max(left, right)
                peak = max(peak, level)
                if level >= MIN_PEAK:
                    strong_frames += 1
                    active.add(cursor // WINDOW_FRAMES)
                cursor += 1
    if cursor != frames:
        raise ValueError('monitor capture length changed during read')
    has_signal = (peak >= MIN_PEAK and
                  strong_frames >= MIN_NONZERO_FRAMES and
                  len(active) >= MIN_ACTIVE_WINDOWS)
    return {
        'schema': 'dino-isolated-host-monitor-v1',
        'status': 'VIRTUAL_SINK_PCM_DETECTED' if has_signal
                  else 'INCONCLUSIVE_NO_HOST_SIGNAL',
        'format': 's16le-stereo-48000',
        'frames': frames,
        'peak_absolute_sample': peak,
        'above_threshold_frames': strong_frames,
        'active_100ms_windows': len(active),
        'virtual_sink_pcm_detected': has_signal,
        'physical_speaker_audio_verified': False,
        'arcade_audio_parity_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    options = parser.parse_args(argv)
    try:
        result = inspect(options.raw)
    except (OSError, ValueError, OverflowError):
        result = {
            'schema': 'dino-isolated-host-monitor-v1',
            'status': 'INCONCLUSIVE_CAPTURE_UNAVAILABLE',
            'virtual_sink_pcm_detected': False,
            'physical_speaker_audio_verified': False,
            'arcade_audio_parity_verified': False,
        }
    options.out.write_text(json.dumps(result, sort_keys=True) + '\n',
                           encoding='ascii')
    print(json.dumps(result, sort_keys=True))
    # Host monitor support is optional; never fail the real guest replay
    # or promote absence of host audio into fabricated evidence.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
