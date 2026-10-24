"""Private-only, SHA-pinned native C/Python parity on restored CPS-1 gfx.bin.

Source content and source layout are NOT a runtime scene; tests are synthetic.
Private original GFX, pixel data, hashes and paths never appear in reports.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile

GFX_BYTES = 0x400000
SHA = re.compile(r'[0-9a-f]{64}\Z')
SEED = 0x365C0A
LAYOUTS = (
    ('scroll1-left', 8, 0, 64, 65536),
    ('scroll1-right', 8, 32, 64, 65536),
    ('scroll2', 16, 0, 128, 32768),
    ('scroll3', 32, 0, 512, 8192),
)
REPO_ROOT = Path(__file__).resolve().parents[1]


class PrivateParityError(Exception):
    """Fixed error categories only; never expose private source paths."""


def guard_private():
    if os.environ.get('GITHUB_ACTIONS', '').lower() == 'true':
        raise PrivateParityError('public_runner_forbidden')


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as inp:
        for part in iter(lambda: inp.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def verify_gfx(path: Path, expected_sha: str) -> bytes:
    guard_private()
    if not isinstance(expected_sha, str) or SHA.fullmatch(expected_sha) is None:
        raise PrivateParityError('invalid_gfx_pin')
    if path.is_symlink() or not path.is_file():
        raise PrivateParityError('invalid_gfx_source')
    resolved = path.resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise PrivateParityError('private_gfx_in_public_tree')
    if path.stat().st_size != GFX_BYTES:
        raise PrivateParityError('wrong_gfx_length')
    if sha_file(path) != expected_sha:
        raise PrivateParityError('gfx_digest_mismatch')
    data = path.read_bytes()
    if len(data) != GFX_BYTES or hashlib.sha256(data).hexdigest() != expected_sha:
        raise PrivateParityError('gfx_changed_during_read')
    return data


def verify_native_sources(source: Path, header: Path, source_sha: str, header_sha: str) -> None:
    if any(not isinstance(x, str) or SHA.fullmatch(x) is None
           for x in (source_sha, header_sha)):
        raise PrivateParityError('invalid_native_source_pin')
    if any(p.is_symlink() or not p.is_file() for p in (source, header)):
        raise PrivateParityError('invalid_native_source')
    if source.name != 'cps1_tile.c' or header.name != 'cps1_tile.h' or source.parent != header.parent:
        raise PrivateParityError('wrong_native_source_pair')
    if sha_file(source) != source_sha or sha_file(header) != header_sha:
        raise PrivateParityError('native_source_digest_mismatch')


def sample_codes(max_codes: int, *, seed: int = SEED, count: int = 1024) -> tuple[int, ...]:
    if type(max_codes) is not int or not 1 <= max_codes <= 65536 or not 1 <= count <= 4096:
        raise PrivateParityError('invalid_sample_count')
    points = {0, max_codes - 1, max_codes // 2, max_codes // 2 - 1}
    points |= set(range(min(32, max_codes)))
    points |= set(range(max(0, max_codes - 32), max_codes))
    points |= set(range(0, max_codes, max(1, max_codes // 256)))
    for edge in (max_codes // 2, max_codes // 4, max_codes * 3 // 4):
        points |= {x for x in (edge - 1, edge, edge + 1) if 0 <= x < max_codes}
    rng = random.Random(seed + max_codes)
    while len(points) < min(count, max_codes):
        points.add(rng.randrange(max_codes))
    # Honor count strictly, while preserving all boundary sentinels.
    if len(points) > count:
        boundaries = {x for x in (0, 1, max_codes - 2, max_codes - 1,
                                   max_codes // 2 - 1, max_codes // 2) if 0 <= x < max_codes}
        points = boundaries | set(sorted(points - boundaries)[:max(0, count - len(boundaries))])
    return tuple(sorted(points))


def reference(region: bytes, side: int, code: int, tile_index: int) -> bytes:
    if not isinstance(region, bytes) or side not in (8, 16, 32):
        raise PrivateParityError('invalid_reference_layout')
    stride = 64 if side == 8 else side * side // 2
    if not 0 <= code < len(region) // stride or len(region) % stride:
        raise PrivateParityError('invalid_reference_code')
    row_stride = 8 if side == 8 else side // 2
    half = 4 if side == 8 and (tile_index & 32) else 0
    result = bytearray(side * side)
    base = code * stride
    for y in range(side):
        for x in range(side):
            k = base + y * row_stride + half + (x // 8) * 4
            bit = 7 - (x % 8)
            result[y * side + x] = sum(((region[k + plane] >> bit) & 1) << (3 - plane)
                                       for plane in range(4))
    return bytes(result)


def parity(region: bytes, source: Path, header: Path, *, samples: int = 1024) -> dict:
    """Compile same C file used by NRO in host shared library; compare four layouts."""
    guard_private()
    if len(region) != GFX_BYTES or type(samples) is not int or not 16 <= samples <= 4096:
        raise PrivateParityError('invalid_parity_input')
    with tempfile.TemporaryDirectory(prefix='cps1-stage365-native-') as td:
        shared = Path(td) / 'cps1.so'
        try:
            subprocess.run(['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            '-fPIC', '-shared', str(source), '-o', str(shared)],
                           check=True, capture_output=True, timeout=60)
            c = ctypes.CDLL(str(shared))
        except (OSError, subprocess.SubprocessError) as exc:
            raise PrivateParityError('native_compile_failed') from exc
        funcs = {}
        for side in (8, 16, 32):
            f = getattr(c, f'cps1_decode_tile{side}')
            f.argtypes = ([ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
                           ctypes.c_uint, ctypes.c_void_p] if side == 8 else
                          [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
                           ctypes.c_void_p])
            f.restype = ctypes.c_bool
            funcs[side] = f
        memory = (ctypes.c_uint8 * GFX_BYTES).from_buffer_copy(region)
        totals = []
        tiles = pixels = mismatches = 0
        for name, side, tile_index, _, limit in LAYOUTS:
            output = (ctypes.c_uint8 * (side * side))()
            mismatched = 0
            codes = sample_codes(limit, count=samples)
            pen_values = set()
            for code in codes:
                args = (memory, len(region), code)
                ok = (funcs[side](*args, tile_index, output) if side == 8 else
                      funcs[side](*args, output))
                if not ok:
                    raise PrivateParityError('native_decoder_rejected_valid_tile')
                result = bytes(output)
                if result != reference(region, side, code, tile_index):
                    mismatched += 1
                pen_values.update(result)
            tiles += len(codes)
            pixels += len(codes) * side * side
            mismatches += mismatched
            totals.append({'layout': name, 'tiles_compared': len(codes),
                           'pixel_indices_compared': len(codes) * side * side,
                           'mismatching_tiles': mismatched,
                           'distinct_4bit_indices': len(pen_values)})
        invalid = True
        for side, limit in ((8, 65536), (16, 32768), (32, 8192)):
            output = (ctypes.c_uint8 * (side * side))()
            args = (memory, len(region), limit)
            ok = (funcs[side](*args, 0, output) if side == 8 else
                  funcs[side](*args, output))
            invalid = invalid and not ok
        return {
            'schema': 'cadillacs-stage365-restored-gfx-native-parity-v1',
            'status': 'pass' if mismatches == 0 and invalid else 'fail',
            'evidence': 'restored_gfx_native_vs_independent_python_indices_only',
            'gameplay_frames_captured': False,
            'authentic_palette_verified': False,
            'mame_verifyroms_executed': False,
            'inp_playback_executed': False,
            'physical_switch_verified': False,
            'layouts_checked': len(LAYOUTS), 'tiles_compared': tiles,
            'pixel_indices_compared': pixels, 'mismatching_tiles': mismatches,
            'invalid_native_codes_rejected': invalid, 'layout_results': totals,
        }


def run(gfx_path: Path, source: Path, header: Path, gfx_sha: str,
        source_sha: str, header_sha: str, samples: int = 1024) -> dict:
    region = verify_gfx(gfx_path, gfx_sha)
    verify_native_sources(source, header, source_sha, header_sha)
    return parity(region, source, header, samples=samples)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gfx', type=Path, required=True)
    p.add_argument('--gfx-sha256', required=True)
    p.add_argument('--native-source', type=Path, default=REPO_ROOT/'source'/'cps1_tile.c')
    p.add_argument('--native-header', type=Path, default=REPO_ROOT/'source'/'cps1_tile.h')
    p.add_argument('--native-sha256', required=True)
    p.add_argument('--native-header-sha256', required=True)
    p.add_argument('--samples', type=int, default=1024)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(argv)
    try:
        report = run(a.gfx, a.native_source, a.native_header, a.gfx_sha256,
                     a.native_sha256, a.native_header_sha256, a.samples)
        if (not a.out.parent.is_dir() or a.out.is_symlink() or
                a.out.resolve() == REPO_ROOT or REPO_ROOT in a.out.resolve().parents):
            raise PrivateParityError('private_output_required')
        with a.out.open('x', encoding='utf-8') as f:
            json.dump(report, f, indent=2, sort_keys=True)
            f.write('\n')
        print(report['status'])
        return 0 if report['status'] == 'pass' else 2
    except (PrivateParityError, OSError, ValueError, AttributeError):
        print('stage365_private_parity_refused')
        return 2

if __name__ == '__main__':
    raise SystemExit(main())