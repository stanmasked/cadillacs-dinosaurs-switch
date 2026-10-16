#!/usr/bin/env python3
"""Local-only CPS-1 dino 68000 ROM mapping/inspection. Does not write ROM data."""
import argparse
import hashlib
import json
import struct
import zipfile

PROGRAM_ROMS = ('cde_23a.8f', 'cde_22a.7f', 'cde_21a.6f')
ROM_CHUNK_SIZE = 0x80000

def swap_16(data):
    if len(data) % 2:
        raise ValueError('16-bit word swap needs even data length')
    result = bytearray(len(data))
    result[0::2] = data[1::2]
    result[1::2] = data[0::2]
    return bytes(result)

def assemble_program(reader):
    regions = []
    for name in PROGRAM_ROMS:
        payload = reader(name)
        if len(payload) != ROM_CHUNK_SIZE:
            raise ValueError(f'{name}: wrong ROM size {len(payload)}')
        regions.append(swap_16(payload))
    return b''.join(regions)

def program_metadata(program):
    sp, pc = struct.unpack_from('>II', program)
    return {'program_bytes': len(program),
            'program_sha256': hashlib.sha256(program).hexdigest(),
            'initial_sp': f'0x{sp:08X}', 'reset_pc': f'0x{pc:08X}',
            'reset_pc_even': not bool(pc & 1),
            'reset_pc_inside_region': pc < len(program)}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('zip_path')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    with zipfile.ZipFile(args.zip_path) as archive:
        program = assemble_program(archive.read)
    meta = program_metadata(program)
    if args.json:
        print(json.dumps(meta, indent=2))
    else:
        for key, value in meta.items():
            print(f'{key}: {value}')
    return 0 if meta['reset_pc_even'] and meta['reset_pc_inside_region'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
