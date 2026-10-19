#!/usr/bin/env python3
"""Bind a sampled X11 response bound to an independent NRO-created HID trace.

Passing says only that a computer keyboard event preceded a sampled
change in the emulator window on the SAME host monotonic clock.
It is not physical console/controller latency or actual first-light
display response.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_hid_timeline as timeline
else:
    import verify_nexium_hid_timeline as timeline

SCHEMA = 'dino-nexium-host-pixel-bound-v1'
MAX_SIZE = 2048


def verify(host_path, guest_timeline, guest_summary):
    host_path = Path(host_path)
    if host_path.is_symlink() or not host_path.is_file():
        raise ValueError('no host pixel measurement')
    if not 2 <= host_path.stat().st_size <= MAX_SIZE:
        raise ValueError('invalid host measurement size')
    with host_path.open('r', encoding='ascii') as stream:
        h = json.load(stream)
    if not isinstance(h, dict) or h.get('schema') != SCHEMA:
        raise ValueError('invalid measurement schema')
    if h.get('status') != 'HOST_PIXEL_CHANGE_OBSERVED_UNBOUND':
        raise ValueError('no sampled X11 response')
    if (h.get('measurement_type') !=
            'host_keyboard_to_first_sampled_window_pixel' or
            h.get('host_screen_sample_upper_bound_only') is not True or
            h.get('guest_hid_binding_verified') is not False or
            h.get('physical_joycon_latency_verified') is not False or
            h.get('physical_display_latency_verified') is not False or
            h.get('audio_latency_verified') is not False or
            h.get('baseline_reset_pixel_verified') is not True or
            h.get('baseline_background_pixel_verified') is not True):
        raise ValueError('inconsistent limits or baseline evidence')
    bound = h.get('host_capture_upper_bound_ms')
    count = h.get('capture_probes')
    if (type(bound) is not int or not 1 <= bound <= 8000 or
            type(count) is not int or not 1 <= count <= 80):
        raise ValueError('invalid host sample count or bound')
    # Guest-produced report independently establishes that the *same
    # NeXium guest test run* handled Y reset + Right + A/B/X in order.
    guest = timeline.verify(guest_timeline, guest_summary)
    if guest['status'] != 'GUEST_HID_ORDER_WITNESSED':
        raise ValueError('missing independent guest HID witness')
    return {
        'schema': 'dino-nexium-host-pixel-evidence-v1',
        'status': 'HOST_KEY_TO_SAMPLED_WINDOW_PIXEL_BOUND_WITNESSED',
        'host_window_upper_bound_ms': bound,
        'host_sample_count': count,
        'guest_action_order_verified': True,
        'guest_last_simulation_tick': guest['last_guest_tick'],
        'bound_includes_host_capture_overhead': True,
        'physical_joycon_latency_verified': False,
        'physical_display_latency_verified': False,
        'audio_latency_verified': False,
        'hardware_input_to_photons_verified': False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', type=Path, required=True)
    p.add_argument('--timeline', type=Path, required=True)
    p.add_argument('--controller', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = verify(args.host, args.timeline, args.controller)
    except (OSError, ValueError, TypeError, OverflowError, UnicodeError,
            json.JSONDecodeError):
        result = {
            'schema': 'dino-nexium-host-pixel-evidence-v1',
            'status': 'INCONCLUSIVE_NO_BOUND_AND_GUEST_HID_BINDING',
            'physical_joycon_latency_verified': False,
            'physical_display_latency_verified': False,
            'audio_latency_verified': False,
            'hardware_input_to_photons_verified': False,
        }
    args.out.write_text(json.dumps(result, sort_keys=True) + '\n',
                        encoding='ascii')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
