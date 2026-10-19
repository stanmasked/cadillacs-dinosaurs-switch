#!/usr/bin/env python3
"""Fixed-vocabulary, opt-in metadata-only summary after a failed local MAME run.

Never read ROM, frame pixels, OBJ bytes, manifests, logs or private SHA data.
Emit one bounded JSON object to stderr; do not create a success report.
"""
from pathlib import Path

try:
    from tools.mame_private_cli_errors import public_failure_report
    from tools.mame_private_capture_progress import private_capture_progress
except ModuleNotFoundError:
    from mame_private_cli_errors import public_failure_report
    from mame_private_capture_progress import private_capture_progress

ALLOWED_STATUSES = frozenset({
    'NO_PRIVATE_CAPTURE_DIRECTORY',
    'NO_EXPECTED_PRIVATE_CAPTURE_FILES',
    'INCOMPLETE_PRIVATE_CAPTURE_FILE_SET',
    'INVALID_PRIVATE_CAPTURE_FILE_SIZES',
    'UNEXPECTED_PRIVATE_CAPTURE_ENTRIES',
    'COMPLETE_FILE_SET_UNVERIFIED',
})
ALLOWED_ACTIONS = frozenset({
    'INSPECT_PRIVATE_MAME_STARTUP_LOG',
    'INSPECT_PRIVATE_MAME_CAPTURE_HOOKS',
    'INSPECT_PRIVATE_CAPTURE_EXTRA_FILES',
    'INSPECT_PRIVATE_CAPTURE_PARTIAL_WRITES',
    'RUN_FULL_PRIVATE_CAPTURE_INTEGRITY_AUDIT',
    'INSPECT_CPP_VIDEO_UPDATE_CAPTURE_HOOK',
    'INSPECT_LUA_FRAME_DONE_CAPTURE_HOOK',
    'COMPARE_LUA_CPP_NOMINAL_FRAME_COVERAGE',
    'INSPECT_LUA_CPP_NOMINAL_LABEL_COVERAGE_OFFSET',
    'REVIEW_SINGLE_LABEL_DROPOUT_SENSITIVITY',
})
EXPECTED_FRAMES = (900, 902, 904, 906, 908, 910)


def _checked_count(value, upper):
    if type(value) is not int or not 0 <= value <= upper:
        raise ValueError('Private capture metadata progress count invalid')
    return value


def safe_progress_projection(observed):
    """Project only pre-approved, bounded numeric values and fixed codes.

    Never echo arbitrary exception strings, unknown keys, private paths,
    original filenames, digests, freeform comments or capture file content.
    """
    if type(observed) is not dict:
        raise ValueError('Private capture metadata progress malformed')
    status = observed.get('status')
    action = observed.get('next_local_investigation_code')
    if status not in ALLOWED_STATUSES or action not in ALLOWED_ACTIONS:
        raise ValueError('Private capture metadata progress status malformed')
    frames = observed.get('frame_progress')
    if not isinstance(frames, list) or len(frames) != len(EXPECTED_FRAMES):
        raise ValueError('Private capture metadata frame list malformed')
    frame_rows = []
    for label, frame in zip(EXPECTED_FRAMES, frames):
        if type(frame) is not dict or frame.get('nominal_frame') != label:
            raise ValueError('Private capture metadata frame label mismatch')
        frame_rows.append({
            'nominal_frame': label,
            'lua_present_files': _checked_count(frame.get('lua_files_present'), 6),
            'cpp_present_files': _checked_count(frame.get('cpp_files_present'), 3),
            'lua_valid_sized_files': _checked_count(
                frame.get('lua_valid_sized_files'), 6),
            'cpp_valid_sized_files': _checked_count(
                frame.get('cpp_valid_sized_files'), 3),
        })

    expected = _checked_count(observed.get('expected_files'), 54)
    present = _checked_count(observed.get('present_files'), 54)
    missing = _checked_count(observed.get('missing_files'), 54)
    invalid = _checked_count(observed.get('invalid_size_files'), 54)
    extra = _checked_count(observed.get('unexpected_entry_count'), 256)
    complete = _checked_count(observed.get('complete_metadata_frames'), 6)
    if (expected != 54 or present + missing != expected or
            sum(row['lua_present_files'] + row['cpp_present_files']
                for row in frame_rows) != present or
            any(row['lua_valid_sized_files'] > row['lua_present_files'] or
                row['cpp_valid_sized_files'] > row['cpp_present_files']
                for row in frame_rows) or invalid > present or
            complete > min(
                sum(row['lua_valid_sized_files'] == 6 for row in frame_rows),
                sum(row['cpp_valid_sized_files'] == 3 for row in frame_rows))):
        raise ValueError('Private capture metadata counters disagree')
    return {
        'status': status,
        'diagnostic_only': True,
        'present_files': present,
        'missing_files': missing,
        'invalid_size_files': invalid,
        'unexpected_entry_count': extra,
        'complete_metadata_frames': complete,
        'source_frame_coverage': frame_rows,
        'next_local_investigation_code': action,
        'capture_contents_read': False,
        'gameplay_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }


def safe_capture_failure_report(error, workspace, *, include_progress=False):
    """Always return fixed safe error codes; progress is explicitly opt-in."""
    report = public_failure_report(error)
    if not include_progress:
        return report
    try:
        if workspace is None:
            raise ValueError('Private capture workspace not specified')
        observed = private_capture_progress(Path(workspace))
        report['capture_progress'] = safe_progress_projection(observed)
    except Exception:
        # Never forward private path errors, filesystem errors, filenames,
        # unpacked ROM contents, or raw capture descriptions.
        report['capture_progress'] = {
            'status': 'PRIVATE_CAPTURE_PROGRESS_REFUSED',
            'diagnostic_only': True,
            'capture_contents_read': False,
            'gameplay_verified': False,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        }
    return report
