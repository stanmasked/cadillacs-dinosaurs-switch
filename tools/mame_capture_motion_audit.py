#!/usr/bin/env python3
"""Audit captured CPS-1 frame-series motion; NEVER assert original gameplay.

Only reads private, already captured same-render-pass files. Report contains
pixel counts and SHA-256 hashes, not pixel data or other protected assets.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

RGB_WIDTH, RGB_HEIGHT = 384, 224
RGB_LENGTH = RGB_WIDTH * RGB_HEIGHT * 3
STREAMS = {'reference-rgb24.bin': RGB_LENGTH, 'buffered-obj-be.bin': 2048,
           'gfxram-be.bin': 196608, 'palette-rgb24.bin': 9216,
           'cps-a-be.bin': 64, 'cps-b-be.bin': 64}


def _load(root, index, suffix, expected):
    path = root / f'frame-{index:08d}.{suffix}'
    data = path.read_bytes()
    if len(data) != expected:
        raise ValueError(f'{path.name}: expected {expected} bytes, got {len(data)}')
    return data


def _frame(root, index):
    if type(index) is not int or index < 0 or index > 99999999:
        raise ValueError('MAME frame number must be an eight-digit nonnegative integer')
    manifest = root / f'frame-{index:08d}.manifest.json'
    meta = json.loads(manifest.read_text(encoding='utf-8'))
    check = {'game': 'dino', 'frame': index,
             'capture_hook': 'screen_update_cps1_complete',
             'full_cliprect': True, 'buffered_obj_same_render_pass': True,
             'reference_pixel_encoding': 'rgb24_palette_resolved',
             'raw_word_endianness': 'big',
             'palette_source': 'MAME_effective_pen_color',
             'reference_width': RGB_WIDTH, 'reference_height': RGB_HEIGHT,
             'pixel_parity_verified': False}
    for key, expected in check.items():
        if type(meta.get(key)) is not type(expected) or meta[key] != expected:
            raise ValueError(f'{manifest.name}: incompatible {key}')
    size_fields = {
        'reference-rgb24.bin':'reference_rgb_bytes',
        'buffered-obj-be.bin':'buffered_obj_bytes',
        'gfxram-be.bin':'gfxram_bytes',
        'palette-rgb24.bin':'palette_bytes',
        'cps-a-be.bin':'cps_a_bytes',
        'cps-b-be.bin':'cps_b_bytes',
    }
    for name, size in STREAMS.items():
        value = meta.get(size_fields[name])
        if type(value) is not int or value != size:
            raise ValueError(f'{manifest.name}: invalid {size_fields[name]}')
    return {name: _load(root, index, name, count) for name, count in STREAMS.items()}


def _rgb_difference(a, b):
    """Independent RGB24 diagnostic, not a fidelity judgment."""
    differing_pixels = 0
    channels_changed = [0, 0, 0]
    absolute_errors = [0, 0, 0]
    first_xy = None
    bbox = [RGB_WIDTH, RGB_HEIGHT, -1, -1]
    for offset in range(0, RGB_LENGTH, 3):
        diffs = [abs(a[offset+c] - b[offset+c]) for c in range(3)]
        if diffs[0] or diffs[1] or diffs[2]:
            pix = offset // 3
            x, y = pix % RGB_WIDTH, pix // RGB_WIDTH
            if first_xy is None:
                first_xy = [x, y]
            bbox = [min(bbox[0], x), min(bbox[1], y),
                    max(bbox[2], x), max(bbox[3], y)]
            differing_pixels += 1
        for c in range(3):
            if diffs[c]:
                channels_changed[c] += 1
                absolute_errors[c] += diffs[c]
    return {'different_pixels': differing_pixels,
            'changed_channel_counts_rgb': channels_changed,
            'total_absolute_channel_error_rgb': absolute_errors,
            'first_changed_pixel_xy': first_xy,
            'changed_bbox_xyxy_inclusive': bbox if first_xy else None}


def audit_sequence(directory, first, count, stride=1):
    if (type(first) is not int or type(count) is not int or
            type(stride) is not int or first < 0 or not 1 <= count <= 120 or
            not 1 <= stride <= 120 or first + (count-1)*stride > 99999999):
        raise ValueError('Frame window: first>=0, count 1..120, stride 1..120')
    directory = Path(directory)
    frames = []
    prev = None
    consecutive_identical = 0
    max_still_transition_run = 0
    prev_still_run = 0
    all_hashes = {k: set() for k in STREAMS}
    for i in range(count):
        number = first+i*stride
        current = _frame(directory, number)
        hashes = {name: hashlib.sha256(data).hexdigest()
                  for name, data in current.items()}
        for name, digest in hashes.items():
            all_hashes[name].add(digest)
        entry = {'mame_frame': number, 'stream_sha256': hashes}
        if prev is not None:
            comparison = _rgb_difference(prev['reference-rgb24.bin'],
                                         current['reference-rgb24.bin'])
            entry['rgb_since_previous'] = comparison
            entry['streams_changed_since_previous'] = [
                name for name in STREAMS if prev[name] != current[name]]
            if comparison['different_pixels'] == 0:
                consecutive_identical += 1
                prev_still_run += 1
            else:
                max_still_transition_run = max(max_still_transition_run,
                                               prev_still_run)
                prev_still_run = 0
        frames.append(entry)
        prev = current
    max_still_transition_run = max(max_still_transition_run, prev_still_run)
    unchanged = len(all_hashes['reference-rgb24.bin']) == 1
    return {
        'format': 'cps1_capture_motion_diagnostic_v1',
        'game': 'dino', 'frame_count': count, 'first_frame': first,
        'stride': stride, 'viewport': [RGB_WIDTH, RGB_HEIGHT],
        'unique_stream_hash_counts': {name: len(value)
                                      for name, value in all_hashes.items()},
        'unchanged_reference_transitions': consecutive_identical,
        'longest_unchanged_reference_transition_run': max_still_transition_run,
        'reference_all_frames_identical': unchanged,
        'warnings': (['All reference RGB frames are identical; inspect capture window']
                     if count > 1 and unchanged else []),
        'first_level_verified': False,
        'input_replay_synchronized': False,
        'mame_pixel_parity_verified': False,
        'physical_switch_tested': False,
        'note': ('Changing pixels do not establish a gameplay scene: attract '
                 'screens, camera pans and animations can all change RGB.'),
        'frames': frames,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture_dir', type=Path)
    parser.add_argument('--first', type=int, required=True)
    parser.add_argument('--count', type=int, required=True)
    parser.add_argument('--stride', type=int, default=1)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.report.exists():
            raise FileExistsError('Refusing to overwrite an existing report')
        result = audit_sequence(args.capture_dir, args.first,
                                args.count, args.stride)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        print(f"{result['frame_count']} format-valid frames; "
              f"{result['unchanged_reference_transitions']} identical RGB transitions")
        print('Original first-level gameplay has NOT been verified')
        return 0
    except (OSError, ValueError, TypeError, KeyError,
            json.JSONDecodeError) as exc:
        print('CPS-1 motion audit refused:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
