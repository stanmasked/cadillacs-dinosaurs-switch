#!/usr/bin/env python3
"""Accept only a host Pulse monitor observation bound to actual guest spar.

Does not establish DAC, loudspeaker, physical Switch or QSound latency.
Both the host stream and the guest HID stream must be valid and co-occur
in the same emulator CI job, without publishing raw monitor PCM.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_hid_timeline as timeline
else:
    import verify_nexium_hid_timeline as timeline

SCHEMA = 'dino-nexium-spar-host-audio-v1'
EXPECTED = 'host_spar_key_to_first_sampled_pulse_monitor_pcm'
MAX_BYTES = 2048


def verify(raw_audio, guest_timeline, guest_controller):
    p = Path(raw_audio)
    if p.is_symlink() or not p.is_file() or not 10 <= p.stat().st_size <= MAX_BYTES:
        raise ValueError('absent or invalid Pulse monitor report')
    with p.open('r', encoding='ascii') as f:
        h = json.load(f)
    if not isinstance(h, dict) or h.get('schema') != SCHEMA:
        raise ValueError('monitor schema mismatch')
    if (h.get('status') != 'HOST_SPAR_530HZ_PCM_OBSERVED_UNBOUND' or
            h.get('measurement_type') != EXPECTED or
            h.get('audio_upper_bound_only') is not True or
            h.get('true_pcm_onset_verified') is not False or
            h.get('physical_speaker_latency_verified') is not False or
            h.get('physical_switch_audio_latency_verified') is not False or
            h.get('original_arcade_audio_verified') is not False or
            h.get('baseline_quiet') is not True or
            h.get('tone_reference_hz') != 530 or
            h.get('format') != 's16le-stereo-48000'):
        raise ValueError('missing a trustworthy isolated monitor baseline')
    elapsed = h.get('host_monitor_read_upper_bound_ms')
    reads = h.get('monitor_read_chunks')
    coherence = h.get('tone_coherence_milli')
    windows = h.get('tone_windows_scanned')
    if (type(elapsed) is not int or not 1 <= elapsed <= 4000 or
            type(reads) is not int or not 1 <= reads <= 512 or
            type(coherence) is not int or not 600 <= coherence <= 1000 or
            type(windows) is not int or not 1 <= windows <= 32):
        raise ValueError('monitor response or tone is outside bounded contract')
    g = timeline.verify(guest_timeline, guest_controller)
    if g.get('status') != 'GUEST_HID_ORDER_WITNESSED':
        raise ValueError('no independent native spar HID witness')
    return {
        'schema': 'dino-nexium-spar-audio-evidence-v1',
        'status': 'GUEST_SPAR_AND_530HZ_MONITOR_TONE_OBSERVED',
        'host_monitor_read_upper_bound_ms': elapsed,
        'host_monitor_read_chunks': reads,
        'spar_tone_reference_hz': 530,
        'spar_tone_coherence_milli': coherence,
        'tone_windows_scanned': windows,
        'quiet_baseline_verified': True,
        'ordered_guest_spar_event_verified': True,
        'host_read_and_pipe_overhead_included': True,
        'physical_switch_audio_latency_verified': False,
        'physical_speaker_latency_verified': False,
        'audible_sound_verified': False,
        'original_arcade_audio_verified': False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', type=Path, required=True)
    p.add_argument('--timeline', type=Path, required=True)
    p.add_argument('--controller', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(argv)
    try:
        value = verify(a.host, a.timeline, a.controller)
    except (OSError, ValueError, TypeError, UnicodeError, OverflowError):
        value = {
            'schema': 'dino-nexium-spar-audio-evidence-v1',
            'status': 'INCONCLUSIVE_NO_BOUND_SPAR_MONITOR_RESPONSE',
            'physical_switch_audio_latency_verified': False,
            'physical_speaker_latency_verified': False,
            'audible_sound_verified': False,
            'original_arcade_audio_verified': False,
        }
    a.out.write_text(json.dumps(value, sort_keys=True) + '\n', encoding='ascii')
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
