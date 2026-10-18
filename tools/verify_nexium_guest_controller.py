#!/usr/bin/env python3
"""Optional, fail-closed verification of real guest HID input evidence.

The special ARM64 diagnostic NRO reports only verified arena effects
from the external libnx pad API, after its independent replay completes.
Host-sent keys by themselves NEVER count as a successful test.
"""
import argparse
import csv
import json
from pathlib import Path

COLUMNS = ['event', 'flags', 'player_x', 'sparring']


def verify(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('no guest controller witness')
    if path.stat().st_size > 512:
        raise ValueError('guest controller report too large')
    try:
        with path.open('r', encoding='ascii', newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != COLUMNS:
                raise ValueError('unknown controller report schema')
            rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise ValueError('invalid controller CSV') from exc
    if len(rows) != 2:
        raise ValueError('controller actions incomplete')
    if [row['event'] for row in rows] != ['RESET', 'INPUT_DONE']:
        raise ValueError('controller events out of order')
    if any(None in row or any(value is None for value in row.values())
           for row in rows):
        raise ValueError('unexpected controller columns')
    try:
        start = [int(rows[0][k]) for k in COLUMNS[1:]]
        final = [int(rows[1][k]) for k in COLUMNS[1:]]
    except ValueError as exc:
        raise ValueError('invalid controller counters') from exc
    if start != [1, 90, 0] or final[0] != 31 or not 90 < final[1] <= 368             or final[2] != 1:
        raise ValueError('required real HID effects missing')
    return {
        'schema': 'dino-nexium-real-hid-v1',
        'status': 'GUEST_HID_EFFECTS_WITNESSED',
        'guest_reset_seen': True,
        'movement_effect_seen': True,
        'attack_effect_seen': True,
        'jump_effect_seen': True,
        'spar_mode_effect_seen': True,
        'buttons_and_effects_mask': 31,
        'player_x_after_input': final[1],
        'physical_controller_hardware_verified': False,
        'host_to_guest_latency_verified': False,
        'original_game_controls_verified': False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = verify(args.report)
    except (OSError, ValueError):
        result = {
            'schema': 'dino-nexium-real-hid-v1',
            'status': 'INCONCLUSIVE_NO_GUEST_HID_EFFECTS',
            'physical_controller_hardware_verified': False,
            'host_to_guest_latency_verified': False,
            'original_game_controls_verified': False,
        }
    args.out.write_text(json.dumps(result, sort_keys=True) + '\n',
                        encoding='ascii')
    print(json.dumps(result, sort_keys=True))
    # Optional HID support does not undermine independently valid
    # NRO guest gameplay, visual or virtual audio evidence.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
