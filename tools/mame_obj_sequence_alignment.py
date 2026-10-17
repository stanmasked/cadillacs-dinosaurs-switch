#!/usr/bin/env python3
"""Compare multi-frame CPS-1 register streams without certifying synchronization.

Requires local MAME Lua files with Stage 40 CRC32 manifests and Stage 42
private C++ render-register sidecars. No original game bytes are emitted.
A winning offset is a hypothesis, NEVER proven video/OBJ synchronization.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import zlib

try:
    from tools.mame_obj_transition_evidence import transition_diagnostic
    from tools.mame_obj_transition_stability import transition_leave_one_out
    from tools.mame_obj_diagnostic_verdict import diagnostic_verdict
except ModuleNotFoundError:
    from mame_obj_transition_evidence import transition_diagnostic
    from mame_obj_transition_stability import transition_leave_one_out
    from mame_obj_diagnostic_verdict import diagnostic_verdict

REG_A = 'cps-a-be.bin'
REG_B = 'cps-b-be.bin'
PROBE = 'render-regs-be.bin'
OBJ = 'buffered-obj-be.bin'
COMPONENTS = frozenset((
    'gfxram-be.bin', REG_A, REG_B, 'palette-rgb24.bin',
    'reference-rgb24.bin',
))
HEX_CRC = re.compile(r'[0-9a-f]{8}')
CAPTURE_SIZES = {
    'gfxram-be.bin': 0x30000,
    REG_A: 64,
    REG_B: 64,
    'palette-rgb24.bin': 3072 * 3,
    'reference-rgb24.bin': 384 * 224 * 3,
}
CAPTURE_SCHEMA = {
    'gfxram_bytes': 196608,
    'cps_a_bytes': 64,
    'cps_b_bytes': 64,
    'palette_bytes': 9216,
    'reference_width': 384,
    'reference_height': 224,
    'reference_rgb_bytes': 258048,
    'raw_word_endianness': 'big',
    'palette_source': 'MAME_effective_pen_color',
}


def _check_capture_component(path, declared_crc, expected_size, data=None):
    """Stream CRC32 and require the exact expected size for every Lua file.

    Avoid materializing large RGB and graphics-RAM blobs just to compare
    checksums. CRC32 detects accidental damage, NOT authentic game origin.
    """
    length = 0
    checksum = 0
    if data is not None:
        if type(data) is not bytes:
            raise ValueError(f'{path.name}: expected bytes')
        length = len(data)
        checksum = zlib.crc32(data)
    else:
        with path.open('rb') as source:
            while True:
                chunk = source.read(64 * 1024)
                if not chunk:
                    break
                length += len(chunk)
                if length > expected_size:
                    raise ValueError(f'{path.name}: exceeds expected size {expected_size}')
                checksum = zlib.crc32(chunk, checksum)
    if length != expected_size:
        raise ValueError(f'{path.name}: expected {expected_size} bytes, got {length}')
    if f'{checksum & 0xffffffff:08x}' != declared_crc:
        raise ValueError(f'{path.name}: CRC32 mismatch in MAME capture')


def _read_exact_small(path, expected_size):
    """Read at most the expected size plus one byte; reject oversized inputs."""
    with path.open('rb') as source:
        data = source.read(expected_size + 1)
    if len(data) != expected_size:
        raise ValueError(
            f'{path.name}: expected {expected_size} bytes, got at least {len(data)}')
    return data


def _read_manifest(path):
    """Cap untrusted JSON input before decoding or constructing its objects."""
    manifest_data = _read_exact_bounded_manifest(path)
    return json.loads(manifest_data.decode('utf-8'))


def _read_exact_bounded_manifest(path):
    with path.open('rb') as source:
        data = source.read(16 * 1024 + 1)
    if len(data) > 16 * 1024:
        raise ValueError(f'{path.name}: manifest exceeds 16384 bytes')
    return data


def read_frames(directory, first_frame, frame_count, frame_step):
    """Validate all five captured Lua binaries before scoring register shifts."""
    if (type(first_frame) is not int or first_frame < 0 or
            type(frame_count) is not int or not 4 <= frame_count <= 24 or
            type(frame_step) is not int or not 1 <= frame_step <= 120 or
            first_frame + (frame_count-1)*frame_step > 99999999):
        raise ValueError('Invalid or unbounded capture frame selection')
    directory = Path(directory)
    render, lua = [], []
    for index in range(frame_count):
        frame = first_frame + index * frame_step
        stem = f'frame-{frame:08d}'
        manifest = _read_manifest(directory / (stem + '.manifest.json'))
        if (not isinstance(manifest, dict) or
                type(manifest.get('frame')) is not int or
                manifest['frame'] != frame or
                manifest.get('game') != 'dino' or
                manifest.get('capture_hook') != 'frame_done' or
                manifest.get('pixel_parity_eligible') is not False or
                manifest.get('obj_latch') != 'NOT_CAPTURED'):
            raise ValueError(f'{stem}: invalid frame provenance')
        if any(type(manifest.get(key)) is not type(expected) or
               manifest[key] != expected
               for key, expected in CAPTURE_SCHEMA.items()):
            raise ValueError(f'{stem}: invalid dino capture schema')
        crc = manifest.get('file_crc32')
        if not isinstance(crc, dict) or set(crc) != COMPONENTS:
            raise ValueError(f'{stem}: missing complete file_crc32 manifest')
        if any(not isinstance(value, str) or HEX_CRC.fullmatch(value) is None
               for value in crc.values()):
            raise ValueError(f'{stem}: malformed file_crc32 digest')
        a = _read_exact_small(directory / (stem + '.' + REG_A), 64)
        b = _read_exact_small(directory / (stem + '.' + REG_B), 64)
        # The Stage 40 capture's five-file CRC32 map is a *whole-capture*
        # promise. Do not emit frame-alignment evidence when its RGB image,
        # palette, or graphics RAM is absent, swapped, short or corrupt.
        for name, size in CAPTURE_SIZES.items():
            component = directory / (stem + '.' + name)
            _check_capture_component(
                component, crc[name], size,
                a if name == REG_A else b if name == REG_B else None)
        r = _read_exact_small(directory / (stem + '.' + PROBE), 128)
        obj = _read_exact_small(directory / (stem + '.' + OBJ), 2048)
        render.append(r)
        lua.append(a + b)
    return render, lua


def audit_sequence(render, lua, frame_step, max_offset_steps=2):
    """Score raw 128-byte register equality at candidate frame-index offsets.

    Candidate offset k compares render sample i with Lua sample i+k;
    all samples must be present, and short edge overlaps are penalized
    by reporting coverage. Offset 0 means matching nominal frame labels.
    """
    if (not isinstance(render, (list, tuple)) or
            not isinstance(lua, (list, tuple)) or
            len(render) != len(lua) or not 4 <= len(render) <= 24 or
            type(frame_step) is not int or not 1 <= frame_step <= 120 or
            type(max_offset_steps) is not int or
            not 0 <= max_offset_steps <= min(4, len(render)-3)):
        raise ValueError('Invalid frame series or offset search bounds')
    for frames in (render, lua):
        if any(type(blob) is not bytes or len(blob) != 128 for blob in frames):
            raise ValueError('Each register frame must be exactly 128 bytes')
    n = len(render)
    candidates = []
    for offset in range(-max_offset_steps, max_offset_steps+1):
        pairs = [(render[i], lua[i+offset]) for i in range(n)
                 if 0 <= i+offset < n]
        exact = [a for a, b in pairs if a == b]
        # Each capture contains 64 big-endian 16-bit CPS-A/B words.
        # A partial register match is only a diagnostic hint, never
        # evidence that the same MAME frame was displayed.
        differing_words = sum(
            aa[i:i+2] != bb[i:i+2]
            for aa, bb in pairs for i in range(0, 128, 2))
        compared_words = len(pairs) * 64
        candidates.append({
            'offset_steps': offset,
            'offset_nominal_frames': offset * frame_step,
            'compared_pairs': len(pairs),
            'exact_equal_pairs': len(exact),
            'exact_equal_fraction': len(exact) / len(pairs),
            'distinct_equal_register_states': len(set(exact)),
            'different_register_words': differing_words,
            'compared_register_words': compared_words,
            'register_word_mismatch_fraction': differing_words / compared_words,
        })
    highest_ratio = max(row['exact_equal_fraction'] for row in candidates)
    tied = [row for row in candidates
            if row['exact_equal_fraction'] == highest_ratio]
    best = sorted(tied, key=lambda row: (
        -row['exact_equal_pairs'], abs(row['offset_steps']),
        row['offset_steps']))[0]
    probe_states = len(set(render))
    lua_states = len(set(lua))
    informative = (probe_states >= 2 and lua_states >= 2
                   and best['distinct_equal_register_states'] >= 2
                   and best['exact_equal_pairs'] >= 3
                   and len(tied) == 1)
    # Zero exact matching pairs carries no evidence for *any* offset.
    # Do not invent a best shift simply from the nominal frame labels.
    strong_best = best if best['exact_equal_pairs'] else None
    smallest_word_fraction = min(
        row['register_word_mismatch_fraction'] for row in candidates)
    word_tied = [row for row in candidates
                 if row['register_word_mismatch_fraction'] == smallest_word_fraction]
    word_best = sorted(word_tied, key=lambda row: (
        -row['compared_pairs'], abs(row['offset_steps']), row['offset_steps']))[0]
    # Only report a unique *closest* candidate if both streams changed and
    # some 16-bit words agreed. The result is weaker than exact frame parity.
    word_hypothesis = (
        word_best if probe_states >= 2 and lua_states >= 2 and
        len(word_tied) == 1 and smallest_word_fraction < 1.0 else None)
    return {
        'sample_count': n,
        'frame_step': frame_step,
        'render_distinct_register_states': probe_states,
        'lua_distinct_register_states': lua_states,
        'candidates': candidates,
        'best_offset_steps': strong_best['offset_steps'] if strong_best else None,
        'best_offset_nominal_frames': (
            strong_best['offset_nominal_frames'] if strong_best else None),
        'best_overlap_pairs': strong_best['compared_pairs'] if strong_best else None,
        'no_exact_register_pairs': strong_best is None,
        'offset_hypothesis_informative': informative,
        'ambiguous_best_offsets': [row['offset_steps'] for row in tied]
            if len(tied) > 1 else [],
        'closest_word_offset_steps': (
            word_hypothesis['offset_steps'] if word_hypothesis else None),
        'closest_word_offset_nominal_frames': (
            word_hypothesis['offset_nominal_frames'] if word_hypothesis else None),
        'closest_word_mismatch_fraction': smallest_word_fraction,
        'ambiguous_closest_word_offsets': (
            [row['offset_steps'] for row in word_tied] if len(word_tied) > 1 else []),
        'word_distance_diagnostic_only': True,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
        'warning': (
            'Register equality and frame indices never prove MAME frame timing. '
            'Word-distance guesses are weaker than exact matches. '
            'Flat sequences, edge overlap and repeated states can yield false offsets.'
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture_dir', type=Path,
                        help='Private directory containing both Lua and C++ frame captures')
    parser.add_argument('--first-frame', type=int, default=900)
    parser.add_argument('--frame-count', type=int, default=6)
    parser.add_argument('--frame-step', type=int, default=2)
    parser.add_argument('--max-offset-steps', type=int, default=2)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        render, lua = read_frames(args.capture_dir, args.first_frame,
                                  args.frame_count, args.frame_step)
        report = audit_sequence(render, lua, args.frame_step, args.max_offset_steps)
        transitions = transition_diagnostic(
            render, lua, args.frame_step, args.max_offset_steps)
        report['transition_analysis'] = transitions
        report['transition_stability'] = transition_leave_one_out(
            render, lua, args.frame_step, args.max_offset_steps)
        # Three diagnostics from the same register data, not independent
        # physical proof of video/OBJ/frame synchronization.
        if (report['offset_hypothesis_informative'] and
                transitions['transition_hypothesis_informative']):
            report['diagnostic_offset_metrics_agree'] = (
                report['best_offset_steps'] ==
                transitions['transition_best_offset_steps'])
        else:
            report['diagnostic_offset_metrics_agree'] = None
        report['diagnostic_verdict'] = diagnostic_verdict(
            report, transitions, report['transition_stability'])
        report['first_frame'] = args.first_frame
        report['probe_register_sha256'] = [
            hashlib.sha256(blob).hexdigest() for blob in render]
        # No raw register values or captured game data in output.
        with args.out.open('x', encoding='utf-8') as output:
            json.dump(report, output, indent=2)
        print('Wrote local multi-frame alignment hypotheses:', args.out)
        print('WARNING: no frame synchronization or pixel parity is verified')
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f'MAME alignment series refused: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
