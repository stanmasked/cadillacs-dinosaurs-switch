#!/usr/bin/env python3
"""Conservative correlation of a Lua auto-exit *message* with post-run files.

This is not proof of real emulator callback order or a reason for
physical process termination. No private paths, logs, ROM, frame bytes,
hashes, or unknown fields are returned. Only bounded categorical data.
"""

READY = 'LOCAL_LUA_REPORTED_SIZE_READY_EXIT'
GRACE = 'LOCAL_LUA_REPORTED_GRACE_LIMIT_EXIT'
VALID_MARKERS = frozenset((READY, GRACE))
COMPLETE = 'COMPLETE_FILE_SET_UNVERIFIED'
INCOMPLETE = frozenset((
    'NO_PRIVATE_CAPTURE_DIRECTORY',
    'NO_EXPECTED_PRIVATE_CAPTURE_FILES',
    'INCOMPLETE_PRIVATE_CAPTURE_FILE_SET',
    'INVALID_PRIVATE_CAPTURE_FILE_SIZES',
    'UNEXPECTED_PRIVATE_CAPTURE_ENTRIES',
))
EXPECTED_FRAMES = (900, 902, 904, 906, 908, 910)


def _safe_status(code, strict_audit):
    return {
        'status': code,
        'diagnostic_only': True,
        'strict_structural_capture_audit_passed': strict_audit,
        'auto_exit_marker_is_independent_evidence': False,
        'actual_process_exit_cause_verified': False,
        'capture_file_bytes_read_by_reconciliation': False,
        'rom_bytes_read_by_reconciliation': False,
        'original_game_authenticity_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }


def _validated_progress_state(progress):
    """Return COMPLETE / INCOMPLETE / NONE; reject even plausible forgeries."""
    if not isinstance(progress, dict):
        return None
    status = progress.get('status')
    if status not in INCOMPLETE and status != COMPLETE:
        return None
    rows = progress.get('source_frame_coverage')
    if not isinstance(rows, list) or len(rows) != 6:
        return None
    total = 0
    valid_full = 0
    for label, row in zip(EXPECTED_FRAMES, rows):
        if not isinstance(row, dict) or type(row.get('nominal_frame')) is not int:
            return None
        if row['nominal_frame'] != label:
            return None
        fields = (
            ('lua_present_files', 6), ('cpp_present_files', 3),
            ('lua_valid_sized_files', 6), ('cpp_valid_sized_files', 3),
        )
        values = []
        for field, upper in fields:
            value = row.get(field)
            if type(value) is not int or not 0 <= value <= upper:
                return None
            values.append(value)
        lp, cp, lv, cv = values
        if lv > lp or cv > cp:
            return None
        total += lp + cp
        valid_full += lv == 6 and cv == 3
    fields = (
        ('present_files', 54), ('missing_files', 54),
        ('invalid_size_files', 54), ('unexpected_entry_count', 256),
        ('complete_metadata_frames', 6),
    )
    numeric = {}
    for key, upper in fields:
        value = progress.get(key)
        if type(value) is not int or not 0 <= value <= upper:
            return None
        numeric[key] = value
    if (numeric['present_files'] + numeric['missing_files'] != 54 or
            numeric['present_files'] != total or
            numeric['complete_metadata_frames'] != valid_full or
            numeric['invalid_size_files'] > numeric['present_files']):
        return None
    all_complete = (
        numeric['present_files'] == 54 and
        numeric['missing_files'] == 0 and
        numeric['invalid_size_files'] == 0 and
        numeric['unexpected_entry_count'] == 0 and valid_full == 6
    )
    # Status must agree with the core completeness outcome.
    if (status == COMPLETE) != all_complete:
        return None
    return 'COMPLETE' if all_complete else 'INCOMPLETE'


def reconcile_auto_exit_with_capture(marker, *, strict_audit_passed=False,
                                     failure_progress=None):
    """Use exclusively fixed status fields and strict full-capture evidence.

    The successful path calls with strict_audit_passed=True only after
    CRC/FNV/session checks succeeded. Error path requires a validated
    size-only progress projection; do not infer anything from the log alone.
    """
    if type(strict_audit_passed) is not bool:
        return _safe_status('AUTO_EXIT_RECONCILIATION_UNAVAILABLE', False)
    if not isinstance(marker, dict):
        return _safe_status('AUTO_EXIT_RECONCILIATION_UNAVAILABLE', False)
    label = marker.get('status')
    if label not in VALID_MARKERS or marker.get('marker_observed') is not True:
        return _safe_status('AUTO_EXIT_MARKER_NOT_USABLE', strict_audit_passed)
    if strict_audit_passed:
        state = 'COMPLETE'
    else:
        state = _validated_progress_state(failure_progress)
    if state is None:
        return _safe_status('AUTO_EXIT_PROGRESS_NOT_USABLE', strict_audit_passed)
    if label == READY:
        code = ('READY_MESSAGE_AGREES_WITH_SIZE_ONLY_FILES'
                if state == 'COMPLETE' else
                'READY_MESSAGE_CONTRADICTS_POST_RUN_FILES')
    else:
        code = ('GRACE_MESSAGE_CONTRADICTS_POST_RUN_FILES'
                if state == 'COMPLETE' else
                'GRACE_MESSAGE_AGREES_WITH_INCOMPLETE_FILES')
    return _safe_status(code, strict_audit_passed)
