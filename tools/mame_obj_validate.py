#!/usr/bin/env python3
"""Validate MAME dino's experimental 0x800-byte VBlank-latched OBJ dumps.

No claims of alignment to screen:pixels() are made: latch and screen update
can belong to different emulated frame phases.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

PATTERN = re.compile(r'dino_obj_latch_frame-([0-9]{8,20})\.be\.bin\Z')
EXPECTED_BYTES = 0x800


def inspect(path):
    path = Path(path)
    match = PATTERN.fullmatch(path.name)
    if match is None:
        raise ValueError('Unrecognized dino OBJ latch dump filename')
    content = path.read_bytes()
    if len(content) != EXPECTED_BYTES:
        raise ValueError(f'Expected 2048 byte latch dump, received {len(content)}')
    words = struct.unpack('>1024H', content)
    first_terminator = next((i // 4 for i in range(3, len(words), 4)
                             if words[i] & 0xff00 == 0xff00), None)
    populated_objects = (first_terminator if first_terminator is not None else 256)
    return {
        'source': path.name, 'game': 'dino',
        'latch_frame_number': int(match.group(1)),
        'buffer_kind': 'MAME_cps1_objram_latch_m_buffered_obj',
        'encoding': 'big_endian_16bit',
        'bytes': EXPECTED_BYTES,
        'sha256': hashlib.sha256(content).hexdigest(),
        'first_terminator_slot': first_terminator,
        'object_slots_before_marker': populated_objects,
        'framebuffer_synchronized': False,
        'pixel_parity_eligible': False,
        'note': 'CPS1 latch event frame number alone does not prove screen-frame alignment',
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('dump_file', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        report = inspect(args.dump_file)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
            f.write('\n')
        print('Verified latched OBJ bytes:', report['bytes'])
        print('Display frame alignment: NOT VERIFIED')
        return 0
    except (ValueError, OSError) as e:
        print('OBJ dump rejected:', e, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
