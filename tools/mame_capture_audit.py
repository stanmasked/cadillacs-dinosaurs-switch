#!/usr/bin/env python3
"""Audit local MAME CPS-1 captures without claiming pixel-exact scene parity.

Checks manifest provenance, exact byte sizes, SHA-256 and adjacent frame
differences. No ROM files are used or uploaded.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

FILES = {
    'gfxram-be.bin': 0x30000,
    'cps-a-be.bin': 0x40,
    'cps-b-be.bin': 0x40,
    'palette-rgb24.bin': 3072 * 3,
    'reference-rgb24.bin': 384 * 224 * 3,
}
STEM = re.compile(r'frame-([0-9]{8})\Z')


def read_frame(directory, name):
    matched = STEM.fullmatch(name)
    if matched is None:
        raise ValueError('Invalid frame stem: expected frame-XXXXXXXX')
    directory = Path(directory)
    manifest = json.loads((directory / (name + '.manifest.json')).read_text('utf-8'))
    expected = {
        'game': 'dino', 'frame': int(matched.group(1)),
        'gfxram_bytes': FILES['gfxram-be.bin'],
        'cps_a_bytes': FILES['cps-a-be.bin'],
        'cps_b_bytes': FILES['cps-b-be.bin'],
        'palette_bytes': FILES['palette-rgb24.bin'],
        'reference_width': 384, 'reference_height': 224,
        'reference_rgb_bytes': FILES['reference-rgb24.bin'],
        'raw_word_endianness': 'big',
        'reference_pixel_encoding': 'rgb32_resolved',
        'palette_source': 'MAME_effective_pen_color',
        'obj_latch': 'NOT_CAPTURED',
        'pixel_parity_eligible': False,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise ValueError(f'{name}: {field} mismatch: {manifest.get(field)!r} != {value!r}')
    if manifest.get('reference_source_format') not in ('indexed_bitmap', 'rgb_bitmap'):
        raise ValueError(f'{name}: unknown source framebuffer type')
    output = {
        'frame': int(matched.group(1)),
        'reference_source_format': manifest['reference_source_format'],
        'complete_sprite_buffer': False,
        'pixel_parity_eligible': False,
    }
    data = {}
    for suffix, expected_len in FILES.items():
        payload = (directory / (name + '.' + suffix)).read_bytes()
        if len(payload) != expected_len:
            raise ValueError(f'{name}.{suffix}: expected {expected_len} bytes, got {len(payload)}')
        data[suffix] = payload
        output[suffix] = {'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}
    rgb = data['reference-rgb24.bin']
    colors = set(rgb[i:i+3] for i in range(0, len(rgb), 3))
    output['reference_unique_rgb_colors'] = len(colors)
    output['reference_is_uniform_color'] = len(colors) == 1
    return output, data


def audit_capture(directory, stems):
    if not isinstance(stems, (list, tuple)) or not 1 <= len(stems) <= 120:
        raise ValueError('Supply 1..120 frame stems')
    if len(set(stems)) != len(stems):
        raise ValueError('Duplicate capture frame stems')
    audited = []
    previous = None
    for stem in sorted(stems):
        result, data = read_frame(directory, stem)
        if audited and result['frame'] <= audited[-1]['frame']:
            raise ValueError('Capture frame numbers must be strictly increasing')
        if previous is not None:
            prior = previous['reference-rgb24.bin']
            current = data['reference-rgb24.bin']
            delta = sum(prior[p:p+3] != current[p:p+3] for p in range(0, len(current), 3))
            before = previous['palette-rgb24.bin']
            after = data['palette-rgb24.bin']
            palette_delta = sum(before[p:p+3] != after[p:p+3]
                                for p in range(0, len(after), 3))
            result['change_from_previous'] = {
                'rgb_pixels_changed': delta,
                'palette_entries_changed': palette_delta,
                'gfxram_changed': data['gfxram-be.bin'] != previous['gfxram-be.bin'],
                'cps_a_changed': data['cps-a-be.bin'] != previous['cps-a-be.bin'],
                'cps_b_changed': data['cps-b-be.bin'] != previous['cps-b-be.bin'],
                'frame_gap': result['frame'] - audited[-1]['frame'],
            }
        audited.append(result)
        previous = data
    return {
        'tool': 'cps1_mame_capture_audit', 'format': 1, 'game': 'dino',
        'frame_count': len(audited),
        'authenticity_claim': 'unverified_mame_runtime',
        'latched_obj_available': False,
        'pixel_parity_eligible': False,
        'frames': audited,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        frames = sorted(p.name[:-len('.manifest.json')]
                        for p in args.directory.glob('frame-*.manifest.json'))
        report = audit_capture(args.directory, frames)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x', encoding='utf-8') as file:
            json.dump(report, file, indent=2)
            file.write('\n')
        print('Audited', report['frame_count'], 'CPS-1 reference captures:', args.output)
        print('Full pixel parity: NOT ELIGIBLE (buffered OBJ not captured)')
        return 0
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        print('Capture audit failed:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
