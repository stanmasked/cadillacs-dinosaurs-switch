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
    from tools.mame_private_coverage_shift import nominal_coverage_shift_hypotheses
except ModuleNotFoundError:
    from mame_private_capture_stability import EXPECTED_SIZES, VARIABLE_LENGTH
    from mame_private_coverage_shift import nominal_coverage_shift_hypotheses

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



def _with_stream_coverage(report):
    """Reconcile source-specific completeness using file *sizes* only.

    "Complete" here means each expected name has an ordinary file of
    exactly its expected size (or bounded manifest/sidecar size).
    It NEVER means the frame was authentic or these hooks synchronized.
    """
    frames = report['frame_progress']
    summary = {
        'lua_complete_size_only_frames': 0,
        'cpp_complete_size_only_frames': 0,
        'paired_complete_size_only_frames': 0,
        'lua_complete_cpp_incomplete_frames': 0,
        'cpp_complete_lua_incomplete_frames': 0,
        'neither_complete_size_only_frames': 0,
        'lua_manifest_with_incomplete_components_frames': 0,
        'cpp_latch_sidecar_with_incomplete_components_frames': 0,
    }
    for row in frames:
        lua = row['lua_valid_sized_files']
        cpp = row['cpp_valid_sized_files']
        lua_complete = lua == len(LUA_SUFFIXES)
        cpp_complete = cpp == len(CPP_SUFFIXES)
        row['lua_size_only_state'] = (
            'COMPLETE_SIZE_ONLY' if lua_complete else
            'ABSENT' if row['lua_files_present'] == 0 else 'INCOMPLETE_SIZE_ONLY')
        row['cpp_size_only_state'] = (
            'COMPLETE_SIZE_ONLY' if cpp_complete else
            'ABSENT' if row['cpp_files_present'] == 0 else 'INCOMPLETE_SIZE_ONLY')
        row['cross_stream_size_only_state'] = (
            'BOTH_COMPLETE_SIZE_ONLY' if lua_complete and cpp_complete else
            'LUA_COMPLETE_CPP_INCOMPLETE' if lua_complete else
            'CPP_COMPLETE_LUA_INCOMPLETE' if cpp_complete else
            'NEITHER_COMPLETE_SIZE_ONLY')
        summary['lua_complete_size_only_frames'] += lua_complete
        summary['cpp_complete_size_only_frames'] += cpp_complete
        summary['paired_complete_size_only_frames'] += lua_complete and cpp_complete
        summary['lua_complete_cpp_incomplete_frames'] += lua_complete and not cpp_complete
        summary['cpp_complete_lua_incomplete_frames'] += cpp_complete and not lua_complete
        summary['neither_complete_size_only_frames'] += not lua_complete and not cpp_complete
        summary['lua_manifest_with_incomplete_components_frames'] += (
            row['lua_manifest_present'] and not lua_complete)
        summary['cpp_latch_sidecar_with_incomplete_components_frames'] += (
            row['cpp_latch_sidecar_present'] and not cpp_complete)
    if (summary['paired_complete_size_only_frames'] != report['complete_metadata_frames'] or
            sum((
                summary['paired_complete_size_only_frames'],
                summary['lua_complete_cpp_incomplete_frames'],
                summary['cpp_complete_lua_incomplete_frames'],
                summary['neither_complete_size_only_frames'],
            )) != FRAME_COUNT):
        raise ValueError('Private stream coverage counters disagree')
    report['stream_coverage'] = summary
    report['nominal_coverage_shift_hypotheses'] = (
        nominal_coverage_shift_hypotheses(rows))
    if report['status'] == 'INCOMPLETE_PRIVATE_CAPTURE_FILE_SET':
        lua_present = sum(row['lua_valid_sized_files'] for row in frames)
        cpp_present = sum(row['cpp_valid_sized_files'] for row in frames)
        if lua_present and not cpp_present:
            report['next_local_investigation_code'] = 'INSPECT_CPP_VIDEO_UPDATE_CAPTURE_HOOK'
        elif cpp_present and not lua_present:
            report['next_local_investigation_code'] = 'INSPECT_LUA_FRAME_DONE_CAPTURE_HOOK'
        elif (summary['lua_complete_cpp_incomplete_frames'] or
              summary['cpp_complete_lua_incomplete_frames']):
            report['next_local_investigation_code'] = 'COMPARE_LUA_CPP_NOMINAL_FRAME_COVERAGE'
        # Other incomplete combinations retain the original conservative
        # generic hook code; missing data alone never identifies a culprit.
        if (report['nominal_coverage_shift_hypotheses']['status'] ==
                'OFF_LABEL_COVERAGE_HYPOTHESIS_ONLY'):
            report['next_local_investigation_code'] = (
                'INSPECT_LUA_CPP_NOMINAL_LABEL_COVERAGE_OFFSET')
    return report


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
         'lua_files_present': 0, 'cpp_files_present': 0,
         'lua_valid_sized_files': 0, 'cpp_valid_sized_files': 0,
         'lua_manifest_present': False, 'cpp_latch_sidecar_present': False}
        for frame in labels
    ]
    if not capture.exists():
        return _with_stream_coverage({
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
        })
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
            if suffix == 'manifest.json':
                frames[index]['lua_manifest_present'] = True
            elif suffix == 'obj-latch-count.txt':
                frames[index]['cpp_latch_sidecar_present'] = True
            if (0 < meta.st_size <= maximum and
                    (suffix in VARIABLE_LENGTH or meta.st_size == maximum)):
                frames[index]['valid_sized_files'] += 1
                if suffix in LUA_SUFFIXES:
                    frames[index]['lua_valid_sized_files'] += 1
                else:
                    frames[index]['cpp_valid_sized_files'] += 1
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
    return _with_stream_coverage({
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
    })


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
