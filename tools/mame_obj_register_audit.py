#!/usr/bin/env python3
"""Compare a MAME 0.289 OBJ video-update probe with a Lua frame_done capture.

Equal frame labels and equal CPS-A/CPS-B registers are useful necessary
checks, not proof of matching video frames or correct VBlank-latched timing.
This tool NEVER grants pixel-parity eligibility or exports a native scene.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import struct
import sys
import zlib

try:
    from tools.mame_obj_probe_import import attach_probe, PROBE_SUFFIX
except ModuleNotFoundError:
    from mame_obj_probe_import import attach_probe, PROBE_SUFFIX

REG_SUFFIX = '.render-regs-be.bin'
REG_BYTES = 128
A_SUFFIX = '.cps-a-be.bin'
B_SUFFIX = '.cps-b-be.bin'
_CAPTURE_NAMES = frozenset((
    'gfxram-be.bin', 'cps-a-be.bin', 'cps-b-be.bin',
    'palette-rgb24.bin', 'reference-rgb24.bin',
))
_CRC_FORMAT = re.compile(r'[0-9a-f]{8}\Z')


def _register_crc_evidence(snapshot, cps_a, cps_b):
    """Bind Lua register bytes to a capture manifest, when one is present.

    This audit reads only two of the five MAME capture binaries.
    A valid checksum is evidence of file consistency, not proof of frame
    timing, origin, cryptographic authenticity or complete capture integrity.
    """
    declared = snapshot.get('capture_file_crc32')
    if 'capture_file_crc32' not in snapshot:
        return {
            'status': 'NO_CRC32_IN_PARTIAL_SNAPSHOT',
            'verified_register_files': 0,
            'register_crc32_match': False,
        }
    if not isinstance(declared, dict) or set(declared) != _CAPTURE_NAMES:
        raise ValueError('Partial snapshot must declare five capture_file_crc32 values')
    for name, digest in declared.items():
        if not isinstance(digest, str) or _CRC_FORMAT.fullmatch(digest) is None:
            raise ValueError(f'{name}: malformed capture_file_crc32')
    for name, blob in (('cps-a-be.bin', cps_a), ('cps-b-be.bin', cps_b)):
        actual = f'{zlib.crc32(blob) & 0xffffffff:08x}'
        if actual != declared[name]:
            raise ValueError(f'{name}: Lua register CRC32 disagrees with snapshot')
    return {
        'status': 'TWO_REGISTER_FILES_MATCH_DECLARED_CRC32',
        'verified_register_files': 2,
        'register_crc32_match': True,
    }



def _word_mismatches(first, second):
    """Compare 32 unsigned big-endian 16-bit words without guessing meaning."""
    old = struct.unpack('>32H', first)
    new = struct.unpack('>32H', second)
    differences = [i for i in range(32) if old[i] != new[i]]
    return {
        'matching_words': 32 - len(differences),
        'mismatching_words': len(differences),
        'first_mismatched_word_indices': differences[:8],
    }


def audit_registers(snapshot, obj_name, obj_bytes,
                    reg_name, reg_bytes, a_name, a_bytes, b_name, b_bytes):
    """Produce a *diagnostic* report; reject missing, malformed or cross-frame inputs."""
    candidate = attach_probe(snapshot, obj_name, obj_bytes)
    frame = candidate['reference_frame']
    if (reg_name != frame + REG_SUFFIX or
            a_name != frame + A_SUFFIX or b_name != frame + B_SUFFIX):
        raise ValueError('Register probe and Lua captures must have identical frame labels')
    for label, blob, expected_size in (
            ('CPS register probe', reg_bytes, REG_BYTES),
            ('Lua CPS-A', a_bytes, 64),
            ('Lua CPS-B', b_bytes, 64)):
        if not isinstance(blob, bytes) or len(blob) != expected_size:
            raise ValueError(f'{label}: expected exactly {expected_size} bytes')
    integrity = _register_crc_evidence(snapshot, a_bytes, b_bytes)
    a = _word_mismatches(reg_bytes[:64], a_bytes)
    b = _word_mismatches(reg_bytes[64:], b_bytes)
    return {
        'reference_frame': frame,
        'source': 'MAME_0289_VIDEO_UPDATE_VS_LUA_FRAME_DONE',
        'obj_probe_sha256': candidate['obj_probe_sha256'],
        'register_probe_sha256': hashlib.sha256(reg_bytes).hexdigest(),
        'obj_first_end_marker_slot': candidate['obj_probe_first_end_marker_slot'],
        'cps_a': a,
        'cps_b': b,
        'lua_register_integrity': integrity,
        'cross_hook_register_evidence_with_crc': (
            integrity['register_crc32_match'] and
            a['mismatching_words'] == 0 and b['mismatching_words'] == 0),
        'registers_match_exactly': (a['mismatching_words'] == 0
                                    and b['mismatching_words'] == 0),
        'frame_number_labels_match': True,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
        'interpretation': (
            'Matching labels/registers are not timing proof. '
            'Compare VBlank age, raster effects and actual MAME frame pixels.'
        )
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('partial_snapshot', type=Path)
    parser.add_argument('obj_probe', type=Path)
    parser.add_argument('render_regs_probe', type=Path)
    parser.add_argument('lua_cps_a', type=Path)
    parser.add_argument('lua_cps_b', type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--require-register-crc', action='store_true',
                        help='Reject legacy snapshots lacking a five-file CRC32 manifest')
    args = parser.parse_args(argv)
    try:
        destination = args.out.resolve()
        sources = [args.partial_snapshot, args.obj_probe,
                   args.render_regs_probe, args.lua_cps_a, args.lua_cps_b]
        if any(path.resolve() == destination for path in sources):
            raise ValueError('Refusing to overwrite an original capture')
        snapshot = json.loads(args.partial_snapshot.read_text(encoding='utf-8'))
        report = audit_registers(
            snapshot,
            args.obj_probe.name, args.obj_probe.read_bytes(),
            args.render_regs_probe.name, args.render_regs_probe.read_bytes(),
            args.lua_cps_a.name, args.lua_cps_a.read_bytes(),
            args.lua_cps_b.name, args.lua_cps_b.read_bytes())
        if args.require_register_crc and not report['lua_register_integrity']['register_crc32_match']:
            raise ValueError('Cannot audit without verified Lua CPS-A/B register CRC32')
        with args.out.open('x', encoding='utf-8') as out:
            json.dump(report, out, indent=2)
        print('Wrote private register alignment diagnostic:', args.out)
        print('WARNING: exact register equality is not frame synchronization proof')
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f'Register alignment audit refused: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
