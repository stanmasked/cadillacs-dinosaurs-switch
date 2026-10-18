#!/usr/bin/env python3
"""ROM-free NeXium X11 keyboard -> window pixel observation (diagnostic only).

This is a *sampled host-window response upper bound*, not physical
controller latency, true first-light onset, gameplay input processing
time, nor measured Switch hardware/display latency.

Uses no original game data and never saves host screenshots, raw input,
absolute host timestamps, audio, user-owned ROM bytes, or keys.
"""
import argparse
import json
import math
import re
import subprocess
import time
from pathlib import Path

# ROM-free training room: at player reset X=90, actor body covers (334,425).
# (361,425) is initially background, and becomes body-blue after movement.
BACKGROUND = (62, 83, 74)
PLAYER_BLUE = (62, 180, 208)
RESET_XY = (334, 425)
MOVE_XY = (361, 425)
RGB = re.compile(r'\((\d{1,3}),\s*(\d{1,3}),\s*(\d{1,3})(?:,|\))')
HEX = re.compile(r'#([0-9A-Fa-f]{6})(?:\b|$)')
MAX_POLLS = 80
MAX_BOUND_MS = 8000


def parse_color(output):
    """Parse the one-pixel ImageMagick txt:- output, rejecting ambiguity."""
    if '0,0:' not in output or output.count('0,0:') != 1:
        raise ValueError('capture had no unique 1x1 pixel')
    value = output.split('0,0:', 1)[1]
    hex_match = HEX.search(value)
    if hex_match:
        code = hex_match.group(1)
        return tuple(int(code[i:i+2], 16) for i in (0, 2, 4))
    rgb_match = RGB.search(value)
    if rgb_match:
        parts = tuple(map(int, rgb_match.groups()[:3]))
        if all(0 <= n <= 255 for n in parts):
            return parts
    raise ValueError('unrecognized X11 pixel notation')


def sample(window, xy):
    x, y = xy
    proc = subprocess.run(
        ['import', '-window', window, '-crop', f'1x1+{x}+{y}',
         '-depth', '8', 'txt:-'],
        capture_output=True, text=True, timeout=3, check=False,
    )
    if proc.returncode:
        raise RuntimeError('cannot sample X11 window')
    return parse_color(proc.stdout)


def press(key, duration=0.25):
    subprocess.run(['xdotool', 'keydown', key], check=True,
                   timeout=4, capture_output=True)
    try:
        time.sleep(duration)
    finally:
        subprocess.run(['xdotool', 'keyup', key], check=False,
                       timeout=4, capture_output=True)


def result(status, **extra):
    return {
        'schema': 'dino-nexium-host-pixel-bound-v1',
        'status': status,
        'measurement_type': 'host_keyboard_to_first_sampled_window_pixel',
        'host_screen_sample_upper_bound_only': True,
        'guest_hid_binding_verified': False,
        'physical_joycon_latency_verified': False,
        'physical_display_latency_verified': False,
        'audio_latency_verified': False,
        **extra,
    }


def probe(window):
    if not window.isdecimal() or not 0 < int(window) < 2**32:
        raise ValueError('bad X11 window id')
    subprocess.run(['xdotool', 'windowactivate', '--sync', window],
                   check=True, timeout=5, capture_output=True)
    subprocess.run(['xdotool', 'windowfocus', window],
                   check=True, timeout=5, capture_output=True)
    # Guest Y reset is required independently for the guest HID witness.
    press('z')
    reset_ok = False
    for _ in range(18):
        if sample(window, RESET_XY) == PLAYER_BLUE:
            reset_ok = True
            break
        time.sleep(0.1)
    if not reset_ok:
        raise ValueError('reset actor pixel not visible')
    if sample(window, MOVE_XY) != BACKGROUND:
        raise ValueError('pre-input target is not background')
    # Host and capture timestamps below use the same monotonic clock.
    start_ns = time.monotonic_ns()
    subprocess.run(['xdotool', 'keydown', 'Right'], check=True,
                   timeout=4, capture_output=True)
    bound = None
    count = 0
    release_after_ns = start_ns + 750_000_000
    deadline_ns = start_ns + MAX_BOUND_MS * 1_000_000
    held = True
    try:
        while count < MAX_POLLS and time.monotonic_ns() < deadline_ns:
            if held and time.monotonic_ns() >= release_after_ns:
                subprocess.run(['xdotool', 'keyup', 'Right'], check=False,
                               timeout=4, capture_output=True)
                held = False
            pixel = sample(window, MOVE_XY)
            end_ns = time.monotonic_ns()
            count += 1
            if pixel == PLAYER_BLUE:
                # Pixel exists by capture completion. This is a
                # conservative sampled observation bound, not an
                # instrumented GPU photon-onset timestamp.
                bound = math.ceil((end_ns - start_ns) / 1_000_000)
                break
            if pixel != BACKGROUND:
                raise ValueError('target pixel changed to unexpected color')
            time.sleep(0.03)
    finally:
        if held:
            wait_ns = release_after_ns - time.monotonic_ns()
            if wait_ns > 0:
                time.sleep(wait_ns / 1_000_000_000)
            subprocess.run(['xdotool', 'keyup', 'Right'], check=False,
                           timeout=4, capture_output=True)
    # Finish the original, already verified guest HID sequence.
    time.sleep(0.3)
    press('c')
    time.sleep(0.3)
    press('x')
    time.sleep(0.3)
    press('v')
    if bound is None:
        return result('INCONCLUSIVE_PIXEL_NOT_OBSERVED',
                      capture_probes=count)
    return result('HOST_PIXEL_CHANGE_OBSERVED_UNBOUND',
                  host_capture_upper_bound_ms=bound,
                  capture_probes=count,
                  baseline_reset_pixel_verified=True,
                  baseline_background_pixel_verified=True)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--window', required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        record = probe(args.window)
    except (ValueError, RuntimeError, subprocess.SubprocessError, OSError) as exc:
        # Emit only fixed, public diagnostic codes; never expose host
        # window titles, paths, subprocess stderr or user identifiers.
        safe_codes = {
            'bad X11 window id': 'INVALID_WINDOW',
            'reset actor pixel not visible': 'RESET_PIXEL_MISSING',
            'pre-input target is not background': 'BASELINE_MISMATCH',
            'target pixel changed to unexpected color': 'UNEXPECTED_PIXEL',
            'capture had no unique 1x1 pixel': 'INVALID_SAMPLE_SHAPE',
            'unrecognized X11 pixel notation': 'INVALID_SAMPLE_COLOR',
            'cannot sample X11 window': 'SCREEN_CAPTURE_UNAVAILABLE',
        }
        record = result('INCONCLUSIVE_HOST_PIXEL_CAPTURE_UNAVAILABLE',
                        diagnostic_code=safe_codes.get(str(exc), 'CAPTURE_OR_INPUT_FAILED'))
    args.out.write_text(json.dumps(record, sort_keys=True) + '\n',
                        encoding='ascii')
    print(json.dumps(record, sort_keys=True))
    # Never block validated native guest replay on optional host sampling.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
