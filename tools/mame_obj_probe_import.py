#!/usr/bin/env python3
"""Attach a private MAME 0.289 buffered OBJ probe to a *partial* snapshot.

This helper does not authenticate synchronization between the MAME frame
update and its Lua frame_done callback. It deliberately leaves
pixel_parity_eligible=False so incomplete captures cannot silently be
exported as authoritative Nintendo Switch scenes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import sys

STEM_RE = re.compile(r'frame-[0-9]{8}\Z')
PROBE_SUFFIX = '.buffered-obj-be.bin'
OBJ_WORD_COUNT = 1024
OBJ_BYTES = OBJ_WORD_COUNT * 2


def decode_probe(blob):
    if not isinstance(blob, bytes) or len(blob) != OBJ_BYTES:
        raise ValueError('Buffered OBJ probe must be exactly 2048 bytes')
    words = list(struct.unpack('>1024H', blob))
    first_marker = next(
        (index // 4 for index in range(0, len(words), 4)
         if (words[index+3] & 0xff00) == 0xff00), None)
    return words, first_marker


def attach_probe(snapshot, probe_name, data):
    if not isinstance(snapshot, dict):
        raise ValueError('Expected partial MAME snapshot object')
    frame = snapshot.get('reference_frame')
    if not isinstance(frame, str) or not STEM_RE.fullmatch(frame):
        raise ValueError('Partial snapshot requires canonical reference_frame')
    if probe_name != frame + PROBE_SUFFIX:
        raise ValueError('OBJ probe filename must match reference frame')
    if (snapshot.get('pixel_parity_eligible') is not False or
            snapshot.get('buffered_obj_source') != 'UNAVAILABLE_MAME_LUA'):
        raise ValueError('Only unverified partial MAME Lua captures are supported')
    words, marker = decode_probe(data)
    result = dict(snapshot)
    result['buffered_obj_words'] = words
    result['buffered_obj_source'] = 'MAME_0289_CPP_OBJ_PROBE_UNSYNCED'
    result['obj_probe_frame'] = frame
    result['obj_probe_sha256'] = hashlib.sha256(data).hexdigest()
    result['obj_probe_first_end_marker_slot'] = marker
    result['obj_probe_frame_alignment'] = 'NOT_INDEPENDENTLY_VERIFIED'
    result['pixel_parity_eligible'] = False
    result['note'] = ('Buffered OBJ copied from the private MAME source probe, '
                      'but frame synchronization and screenshot parity are unverified')
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('partial_snapshot', type=Path)
    p.add_argument('obj_probe', type=Path)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.out.resolve() in (args.partial_snapshot.resolve(), args.obj_probe.resolve()):
            raise ValueError('Refusing to overwrite an input capture')
        snapshot = json.loads(args.partial_snapshot.read_text(encoding='utf-8'))
        result = attach_probe(snapshot, args.obj_probe.name, args.obj_probe.read_bytes())
        with args.out.open('x', encoding='utf-8') as file:
            json.dump(result, file, separators=(',', ':'))
        print('Wrote private unsynchronized OBJ diagnostic:', args.out)
        print('WARNING: pixel_parity_eligible=false; NOT a verified MAME frame')
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f'OBJ probe import refused: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
