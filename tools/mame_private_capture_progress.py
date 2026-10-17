#!/usr/bin/env python3
"""Metadata-only assessment of an unfinished private six-frame MAME capture.

Run this separately after a failed/aborted *local* dino session. No ROM,
framebuffer, OBJ, log, JSON or other game content is read. File names
are matched against a fixed schema but never copied into output.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import sys

try:
    from tools.mame_private_capture_stability import (
        EXPECTED_SIZES, VARIABLE_LENGTH,
    )
except ModuleNotFoundError:
    from mame_private_capture_stability import EXPECTED_SIZES, VARIABLE_LENGTH

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_DIR_NAME = 'cps1-captures'
FRAME_FIRST = 900
FRAME_STEP = 2
FRAME_COUNT = 6
MAX_SCAN_ENTRIES = 256
LUA_SUFFIXES = frozenset((
    'gfxram-be.bin', 'cps-a-be.bin', 'cps-b-be.bin',
    'palette-rgb24.bin', 'reference-rgb24.bin', 'manifest.json',
))
CPP_SUFFIXES = frozenset((
    'render-regs-be.bin', 'buffered-obj-be.bin', 'obj-latch-count.txt',
))
assert set(EXPECTED_SIZES) == LUA_SUFFIXES | CPP_SUFFIXES


def _validate_workspace(workspace):
    raw = Path(workspace).expanduser()
    if raw.is_symlink():
        raise ValueError('Private progress workspace must not be a symlink')
    root = raw.resolve()
    if not root.is_dir():
        raise ValueError('Private progress workspace is missing')
    if (root == PROJECT_ROOT or root.is_relative_to(PROJECT_ROOT) or
            PROJECT_ROOT.is_relative_to(root)):
        raise ValueError('Private progress workspace must stay outside the project')
    if os.name == 'posix' and (root.stat().st_mode & 0o077):
        raise ValueError('Private progress workspace permissions are too broad')
    return root


def private_capture_progress(workspace):
    """Count safely named local capture entries without opening their bytes.

    A complete metadata set is not a valid capture: CRC/FNV/session and
    provenance still require the ordinary launcher audit.
    """
    root = _validate_workspace(workspace)
    capture = root / CAPTURE_DIR_NAME
    labels = [FRAME_FIRST + i * FRAME_STEP for i in range(FRAME_COUNT)]
    if capture.is_symlink():
        raise ValueError('Private progress capture directory is a symlink')

    expected = {
        f'frame-{frame:08d}.{suffix}': (i, suffix, size)
        for i, frame in enumerate(labels)
        for suffix, size in EXPECTED_SIZES.items()
    }
    frames = [
        {'nominal_frame': frame, 'present_files': 0, 'valid_sized_files': 0,
         'lua_files_present': 0, 'cpp_files_present': 0}
        for frame in labels
    ]
    if not capture.exists():
        return {
            'status': 'NO_PRIVATE_CAPTURE_DIRECTORY',
            'diagnostic_only': True,
            'nominal_frame_labels': labels,
            'expected_files': len(expected),
            'present_files': 0,
            'valid_sized_files': 0,
            'missing_files': len(expected),
            'invalid_size_files': 0,
            'unexpected_entry_count': 0,
            'complete_metadata_frames': 0,
            'frame_progress': frames,
            'next_local_investigation_code': 'INSPECT_PRIVATE_MAME_STARTUP_LOG',
            'rom_bytes_read': False,
            'capture_file_bytes_read': False,
            'capture_validated': False,
            'original_game_authenticity_verified': False,
            'active_gameplay_verified': False,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        }
    if not capture.is_dir():
        raise ValueError('Private progress capture path is not a directory')

    seen = set()
    invalid_size = unexpected = 0
    with os.scandir(capture) as listing:
        for scanned, entry in enumerate(listing, start=1):
            if scanned > MAX_SCAN_ENTRIES:
                raise ValueError('Private progress capture directory exceeds bounded scan')
            meta = entry.stat(follow_symlinks=False)
            if (not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1):
                raise ValueError('Private progress capture has unsafe or linked entries')
            spec = expected.get(entry.name)
            if spec is None:
                unexpected += 1
                continue
            index, suffix, maximum = spec
            seen.add(entry.name)
            frames[index]['present_files'] += 1
            if suffix in LUA_SUFFIXES:
                frames[index]['lua_files_present'] += 1
            else:
                frames[index]['cpp_files_present'] += 1
            if (0 < meta.st_size <= maximum and
                    (suffix in VARIABLE_LENGTH or meta.st_size == maximum)):
                frames[index]['valid_sized_files'] += 1
            else:
                invalid_size += 1

    present = len(seen)
    complete = sum(row['valid_sized_files'] == len(EXPECTED_SIZES) for row in frames)
    if unexpected:
        status = 'UNEXPECTED_PRIVATE_CAPTURE_ENTRIES'
        action = 'INSPECT_PRIVATE_CAPTURE_EXTRA_FILES'
    elif invalid_size:
        status = 'INVALID_PRIVATE_CAPTURE_FILE_SIZES'
        action = 'INSPECT_PRIVATE_CAPTURE_PARTIAL_WRITES'
    elif present == 0:
        status = 'NO_EXPECTED_PRIVATE_CAPTURE_FILES'
        action = 'INSPECT_PRIVATE_MAME_CAPTURE_HOOKS'
    elif present != len(expected):
        status = 'INCOMPLETE_PRIVATE_CAPTURE_FILE_SET'
        action = 'INSPECT_PRIVATE_MAME_CAPTURE_HOOKS'
    else:
        status = 'COMPLETE_FILE_SET_UNVERIFIED'
        action = 'RUN_FULL_PRIVATE_CAPTURE_INTEGRITY_AUDIT'
    return {
        'status': status,
        'diagnostic_only': True,
        'nominal_frame_labels': labels,
        'expected_files': len(expected),
        'present_files': present,
        'valid_sized_files': present - invalid_size,
        'missing_files': len(expected) - present,
        'invalid_size_files': invalid_size,
        'unexpected_entry_count': unexpected,
        'complete_metadata_frames': complete,
        'frame_progress': frames,
        'next_local_investigation_code': action,
        'rom_bytes_read': False,
        'capture_file_bytes_read': False,
        'capture_validated': False,
        'original_game_authenticity_verified': False,
        'active_gameplay_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(private_capture_progress(args.workspace), indent=2))
        return 0
    except Exception:
        # Never echo untrusted exceptions, paths, private filenames or logs.
        print(json.dumps({
            'status': 'PRIVATE_CAPTURE_PROGRESS_REFUSED',
            'diagnostic_only': True,
            'capture_validated': False,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        }), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
