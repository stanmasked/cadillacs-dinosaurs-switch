#!/usr/bin/env python3
"""Verify an ordered, guest-written HID effect timeline from the ARM64 NRO.

The guest simulation tick counter is not synchronized with the host clock:
these tick gaps are *not* keyboard-to-screen or input/audio latency.
Synthetic CSV test fixtures never prove actual NeXium input delivery.
"""
import argparse
import csv
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_guest_controller as controller
else:
    # The NeXium shell runs this script by its path; in that case
    # Python puts tools/ (not its parent) on sys.path.
    import verify_nexium_guest_controller as controller

COLUMNS = ['event', 'tick', 'player_x', 'sparring', 'event_mask']
EVENTS = ['RESET', 'MOVE', 'ATTACK', 'JUMP', 'SPAR', 'DONE']
REQUIRED_MASKS = {'ATTACK': 8, 'JUMP': 2, 'SPAR': 1}


def verify(path, summary_path=None):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('guest HID timeline absent')
    if not 10 <= path.stat().st_size <= 1024:
        raise ValueError('guest HID timeline size invalid')
    try:
        with path.open('r', encoding='ascii', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != COLUMNS:
                raise ValueError('unrecognized HID timeline fields')
            rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise ValueError('invalid HID timeline encoding') from exc
    if len(rows) != len(EVENTS) or [r['event'] for r in rows] != EVENTS:
        raise ValueError('missing, duplicated or reordered HID events')
    data = []
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('ragged or unexpected HID columns')
        values = [row[field] for field in COLUMNS[1:]]
        if any(not value.isascii() or not value.isdecimal() or
               (len(value)>1 and value[0]=='0') for value in values):
            raise ValueError('non-canonical HID integer')
        parsed = [int(value) for value in values]
        tick, x, spar, mask = parsed
        if tick > 1800 or not 16 <= x <= 368 or spar not in (0, 1) or mask > 2047:
            raise ValueError('HID guest state outside fixed bounds')
        data.append(parsed)
    if data[0] != [0, 90, 0, 0]:
        raise ValueError('timeline did not start from guest reset')
    if not 90 < data[1][1] <= 368:
        raise ValueError('no rightward player movement')
    for index in range(1, 5):
        prev = data[index-1]
        current = data[index]
        if current[0] <= prev[0]:
            raise ValueError('guest action ticks did not advance')
        if current[1] < prev[1]:
            raise ValueError('player moved against rightward input')
        if current[2] != (1 if index == 4 else 0):
            raise ValueError('unexpected sparring state')
        required_mask = REQUIRED_MASKS.get(EVENTS[index], 0)
        if required_mask and not current[3] & required_mask:
            raise ValueError('required in-guest combat event missing')
    if data[5] != data[4]:
        raise ValueError('final row not bound to spar effect')
    if summary_path is not None:
        summary = controller.verify(summary_path)
        if summary['buttons_and_effects_mask'] != 31:
            raise ValueError('controller summary is incomplete')
        if summary['player_x_after_input'] != data[5][1]:
            raise ValueError('final guest controller and timeline disagree')
    return {
        'schema': 'dino-nexium-hid-timeline-v1',
        'status': 'GUEST_HID_ORDER_WITNESSED',
        'events': len(EVENTS),
        'last_guest_tick': data[4][0],
        'guest_tick_intervals': {
            'reset_to_move': data[1][0]-data[0][0],
            'move_to_attack': data[2][0]-data[1][0],
            'attack_to_jump': data[3][0]-data[2][0],
            'jump_to_spar': data[4][0]-data[3][0],
        },
        'final_player_x': data[5][1],
        'host_to_guest_latency_verified': False,
        'hardware_controller_verified': False,
        'physical_audio_latency_verified': False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--summary', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = verify(args.report, args.summary)
    except (ValueError, OSError, OverflowError):
        result = {
            'schema': 'dino-nexium-hid-timeline-v1',
            'status': 'INCONCLUSIVE_NO_ORDERED_GUEST_HID_TRACE',
            'host_to_guest_latency_verified': False,
            'hardware_controller_verified': False,
            'physical_audio_latency_verified': False,
        }
    args.out.write_text(json.dumps(result, sort_keys=True) + '\n',
                        encoding='ascii')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
