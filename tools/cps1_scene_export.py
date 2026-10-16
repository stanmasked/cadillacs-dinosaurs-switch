#!/usr/bin/env python3
"""Export a ROM-free one-frame CPS-1 snapshot for the native Switch renderer.

Format CPS1SCN1: 8-byte magic + little-endian payload length/CRC32 + payload.
This file contains captured game state and optionally copyrighted game-state
content, so it MUST stay local. It does not contain the original GFX ROM.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import zlib

MAGIC = b'CPS1SCN1'
SCROLL_WORDS = 8192
OBJ_WORDS = 1024
ROW_WORDS = 1024
PALETTE_ENTRIES = 3072
PAYLOAD_BYTES = 62494
FILE_BYTES = PAYLOAD_BYTES + 16

def u16(value, name, signed=False):
    if type(value) is not int or not ((-32768 <= value <= 65535) if signed else (0 <= value <= 65535)):
        raise ValueError(f'{name} must be a 16-bit integer')
    return value & 0xffff

def pack_words(values, size, label):
    if not isinstance(values, list) or len(values) != size:
        raise ValueError(f'{label} must have exactly {size} words')
    return struct.pack('<' + str(size) + 'H',
                       *(u16(v, f'{label}[{i}]') for i, v in enumerate(values)))

def pack_scene(snapshot):
    if not isinstance(snapshot, dict):
        raise ValueError('Snapshot must be an object')
    palette = snapshot.get('palette_rgb')
    if not isinstance(palette, list) or len(palette) != PALETTE_ENTRIES:
        raise ValueError('Require 3072 RGB colors from EFFECTIVE palette RAM (palette_rgb)')
    palette_bytes = bytearray()
    for index, color in enumerate(palette):
        if (not isinstance(color, (tuple, list)) or len(color) != 3 or
                any(type(c) is not int or c < 0 or c > 255 for c in color)):
            raise ValueError(f'palette_rgb[{index}] must contain RGB channels 0..255')
        palette_bytes.extend(color)

    payload = bytearray()
    payload += struct.pack('<HH', u16(snapshot['layer_control'], 'layer_control'),
                           u16(snapshot.get('video_control', 0), 'video_control'))
    layers = [snapshot.get('scroll1'), snapshot.get('scroll2'), snapshot.get('scroll3')]
    for axis in ('scrollx', 'scrolly'):
        payload += struct.pack('<3H', *(u16(l.get(axis, 0) if l else 0, axis, signed=True) for l in layers))
    payload.extend(int(bool(l.get('enabled', True))) if l else 0 for l in layers)
    payload.append(0)
    masks = snapshot.get('priority_masks', [0]*4)
    payload += pack_words(masks, 4, 'priority_masks')
    payload += struct.pack('<H', u16(snapshot.get('rowscroll_offset', 0), 'rowscroll_offset'))
    payload += palette_bytes
    for name, layer in zip(('scroll1', 'scroll2', 'scroll3'), layers):
        payload += pack_words(layer['words'] if layer else [0]*SCROLL_WORDS, SCROLL_WORDS, name)

    obj = snapshot.get('buffered_obj_words', [])
    if not isinstance(obj, list) or len(obj) > OBJ_WORDS or len(obj)%4:
        raise ValueError('buffered_obj_words must be a list of up to 1024 words in groups of four')
    # Marker must be inserted before padding, never treat empty slot as sprite.
    if len(obj) < OBJ_WORDS:
        obj = obj + [0, 0, 0, 0xff00]
        obj = obj + [0]*(OBJ_WORDS-len(obj))
    payload += pack_words(obj, OBJ_WORDS, 'buffered_obj_words')
    rowscroll = snapshot.get('rowscroll', [0]*ROW_WORDS)
    payload += pack_words(rowscroll, ROW_WORDS, 'rowscroll')
    if len(payload) != PAYLOAD_BYTES:
        raise AssertionError(f'Internal binary layout bug: {len(payload)} != {PAYLOAD_BYTES}')
    return MAGIC + struct.pack('<II', len(payload), zlib.crc32(payload)) + payload

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot_json', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args=parser.parse_args(argv)
    try:
        snapshot=json.loads(args.snapshot_json.read_text(encoding='utf-8'))
        content=pack_scene(snapshot)
        with args.out.open('xb') as stream:
            stream.write(content)
        print(f'Exported local CPS-1 scene: {args.out}, {len(content)} bytes (no ROM included)')
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
