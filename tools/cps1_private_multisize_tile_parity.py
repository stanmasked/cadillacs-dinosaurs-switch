#!/usr/bin/env python3
"""Private, original-CPS-1 graphics parity across Scroll1/2/3 layouts.

Only reads eight locally owned 512-KiB graphics ROM lanes. No raw ROM
bytes, tiles, private source filenames, hashes, or absolute paths are
printed, persisted, uploaded, or included in the safe JSON result.
The result is decoder consistency, NOT a real original game frame.
"""
import argparse
import ctypes
import json
from pathlib import Path
import random
import sys
import tempfile

try:
    from tools.cps1_private_native_tile_parity import (
        read_private_gfx, compile_native_decoder,
    )
    from tools.cps1_tiles import decode_tile
except ModuleNotFoundError:
    from cps1_private_native_tile_parity import (
        read_private_gfx, compile_native_decoder,
    )
    from cps1_tiles import decode_tile

LAYOUTS = (
    ('scroll1-left', '8x8-left', 8, 0, 65536),
    ('scroll1-right', '8x8-right', 8, 32, 65536),
    ('scroll2', '16x16', 16, 0, 32768),
    ('scroll3', '32x32', 32, 0, 8192),
)
SEED = 0xC0A099
GFX_BYTES = 0x400000


def sampled_codes(limit, *, seed=SEED):
    """Reproducible beginning/end, evenly spaced and random bank coverage."""
    rng = random.Random(seed + limit)
    selected = set(range(min(32, limit)))
    selected.update(range(max(0, limit - 32), limit))
    selected.update((limit // 2 - 1, limit // 2))
    selected.update(range(0, limit, max(1, limit // 160)))
    selected.update(rng.randrange(limit) for _ in range(160))
    return tuple(sorted(selected))


def _base(status):
    return {
        'schema': 'PRIVATE_DINO_MULTISIZE_TILE_PARITY_V1',
        'status': status,
        'diagnostic_only': True,
        'source_rom_or_gfx_bytes_persisted': False,
        'private_rom_paths_or_hashes_in_report': False,
        'authentic_gameplay_observed': False,
        'runtime_palette_verified': False,
        'original_sprite_latch_verified': False,
        'mame_vblank_synchronization_verified': False,
        'nintendo_switch_screen_parity_verified': False,
    }


def private_multisize_tile_parity(archive):
    region = read_private_gfx(archive)
    if len(region) != GFX_BYTES:
        raise ValueError('CPS-1 private graphics region length invalid')
    report = _base('PRIVATE_MULTISIZE_TILE_DECODE_MISMATCH')
    with tempfile.TemporaryDirectory(prefix='cps1-rom-free-native-layers-') as td:
        shared = Path(td) / 'native_tiles.so'
        compile_native_decoder(shared)
        c = ctypes.CDLL(str(shared))
        buffer = (ctypes.c_uint8 * len(region)).from_buffer_copy(region)
        c8 = c.cps1_decode_tile8
        c8.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
                       ctypes.c_uint, ctypes.c_void_p)
        c8.restype = ctypes.c_bool
        c16 = c.cps1_decode_tile16
        c16.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
                        ctypes.c_void_p)
        c16.restype = ctypes.c_bool
        c32 = c.cps1_decode_tile32
        c32.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
                        ctypes.c_void_p)
        c32.restype = ctypes.c_bool
        decoder = {8: c8, 16: c16, 32: c32}
        results = []
        total_tiles = total_pixels = errors = 0
        for layer, layout, side, tilemap_index, max_codes in LAYOUTS:
            codes = sampled_codes(max_codes)
            dest = (ctypes.c_uint8 * (side * side))()
            mismatches = 0
            palette_values = set()
            for code in codes:
                if side == 8:
                    valid = decoder[side](
                        buffer, len(region), code, tilemap_index, dest)
                else:
                    valid = decoder[side](
                        buffer, len(region), code, dest)
                if not valid:
                    raise ValueError('Native CPS-1 layer tile decoder failed')
                raw = bytes(dest)
                reference = decode_tile(region, layout, code)
                mismatches += raw != reference
                palette_values.update(raw)
            total_tiles += len(codes)
            total_pixels += len(codes) * side * side
            errors += mismatches
            results.append({
                'layer': layer,
                'tile_size': side,
                'sampled_tiles': len(codes),
                'compared_pen_indices': len(codes) * side * side,
                'mismatching_tiles': mismatches,
                'distinct_4bit_pens_seen': len(palette_values),
            })
        # Fail-closed bounds checks for 8x8,16x16,32x32.
        dest8 = (ctypes.c_uint8 * 64)()
        dest16 = (ctypes.c_uint8 * 256)()
        dest32 = (ctypes.c_uint8 * 1024)()
        bounds_rejected = (
            not c8(buffer, len(region), 65536, 0, dest8) and
            not c16(buffer, len(region), 32768, dest16) and
            not c32(buffer, len(region), 8192, dest32) and
            not c8(buffer, 63, 0, 0, dest8) and
            not c32(buffer, 511, 0, dest32))
    report['status'] = (
        'PRIVATE_MULTISIZE_TILE_PARITY_PASSED'
        if errors == 0 and bounds_rejected else
        'PRIVATE_MULTISIZE_TILE_DECODE_MISMATCH')
    report.update({
        'assembled_graphics_region_bytes': len(region),
        'layouts_checked': len(LAYOUTS),
        'sampled_tiles_total': total_tiles,
        'compared_pen_indices_total': total_pixels,
        'mismatching_tiles_total': errors,
        'invalid_native_codes_rejected': bool(bounds_rejected),
        'layer_results': results,
    })
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_owned_dino_zip', type=Path)
    args = parser.parse_args(argv)
    try:
        out = private_multisize_tile_parity(args.private_owned_dino_zip)
    except Exception:
        # No private absolute paths, ROM member names, raw tile data,
        # original CRC digests or compiler stdout/stderr may escape.
        out = _base('PRIVATE_MULTISIZE_TILE_INPUT_OR_BUILD_REFUSED')
    print(json.dumps(out, sort_keys=True))
    return 0 if out['status'] == 'PRIVATE_MULTISIZE_TILE_PARITY_PASSED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
