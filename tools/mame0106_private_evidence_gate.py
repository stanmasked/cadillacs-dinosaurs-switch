"""Stage372: classify owner-only MAME evidence without promoting preflight to execution.

This utility reads only small JSON reports outside the public Git tree.
It neither reads ROM bytes nor executes MAME. A local runtime receipt remains
an unauthenticated self-report even when its schema passes validation.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import re
import stat
from pathlib import Path
import sys

from tools.mame0106_private_native_receipt import (
    SCHEMA as RUNTIME_SCHEMA, STAGE369_SHA256, ReceiptError,
    validate_receipt_object,
)
from tools.mame0106_private_windows_capsule import (
    CapsuleError, REPO_ROOT, guard_private,
)

PREFLIGHT_SCHEMA = 'cadillacs-stage371-private-capsule-offline-preflight-v1'
PREFLIGHT_FIELDS = frozenset({
    'schema', 'stage', 'checked_utc', 'archive_bytes', 'archive_sha256',
    'source_archive_basename', 'offline_capsule_integrity',
    'receipt_generation_script', 'synthetic_test_cases_passed',
    'owner_only_storage_required', 'mame_verifyroms_dino_executed',
    'windows_process_started', 'wolfmame_inp_playback_executed',
    'physical_switch_tested', 'note',
})
ARCHIVE_NAME = 'Stage369_MAME0106_Private_Windows_Verify_Capsule.zip'
NOTE = ('Archive checksum verified and source-only receipt wrapper tested; '
        'real native execution not attempted.')
MAX_REPORT_BYTES = 4096
STAGE371_ARCHIVE_BYTES = 29169673
STAGE371_SYNTHETIC_TESTS = 19


class EvidenceError(Exception):
    """Fixed error class. Never print private paths or source text."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError('duplicate_json_key')
        result[key] = value
    return result


def _is_link_or_reparse(path: Path) -> bool:
    # On Windows, junctions are reparse points even where is_symlink() is
    # false. Avoid comparing resolve() text to the original path: drive case
    # and 8.3/long path aliases may legitimately differ.
    attrs = getattr(path.lstat(), 'st_file_attributes', 0)
    return path.is_symlink() or bool(
        attrs & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)
    )


def _file_identity(s: os.stat_result) -> tuple[int, int, int]:
    return (s.st_dev, s.st_ino, s.st_size)


def _read_private_report(path: Path) -> object:
    guard_private()
    if (not path.is_file() or _is_link_or_reparse(path) or
            any(_is_link_or_reparse(parent) for parent in path.parents)):
        raise EvidenceError('unsafe_report_path')
    target = path.resolve()
    if target == REPO_ROOT or REPO_ROOT in target.parents:
        raise EvidenceError('unsafe_report_path')
    before = path.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_REPORT_BYTES:
        raise EvidenceError('invalid_report_length')

    # Keep the descriptor attached to the file that was inspected. On Linux,
    # O_NOFOLLOW rejects a last-moment symlink swap; on Windows the reparse
    # check and file identity comparisons must provide the equivalent guard.
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        after = path.stat(follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or _is_link_or_reparse(path) or
                _file_identity(before) != _file_identity(opened) or
                _file_identity(opened) != _file_identity(after)):
            raise EvidenceError('report_changed_during_open')
        payload = stream.read(MAX_REPORT_BYTES + 1)
        final = os.fstat(stream.fileno())
        if _file_identity(opened) != _file_identity(final):
            raise EvidenceError('report_changed_during_read')
    if not 0 < len(payload) <= MAX_REPORT_BYTES or len(payload) != before.st_size:
        raise EvidenceError('invalid_report_length')
    try:
        return json.loads(
            payload.decode('utf-8'), object_pairs_hook=_unique_object,
            parse_constant=lambda _value: _reject_nonfinite_json()
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError('invalid_report_json') from exc


def _reject_nonfinite_json() -> None:
    raise EvidenceError('nonfinite_json_constant')


def _valid_utc_timestamp(value: object) -> bool:
    if type(value) is not str or len(value) > 40:
        return False
    if re.fullmatch(r'20\d\d-[01]\d-[0-3]\dT[0-2]\d:[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|\+00:00)', value) is None:
        return False
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return False
    return date.tzinfo is not None and date.utcoffset().total_seconds() == 0


def classify_evidence(data: object) -> str:
    """Return a fixed grade, never a claim of independently proven execution."""
    if type(data) is not dict:
        raise EvidenceError('invalid_report_structure')
    schema = data.get('schema')
    if schema == PREFLIGHT_SCHEMA:
        if set(data) != PREFLIGHT_FIELDS:
            raise EvidenceError('preflight_schema_mismatch')
        expected = {
            'schema': PREFLIGHT_SCHEMA,
            'stage': 'Stage371',
            'archive_sha256': STAGE369_SHA256,
            'source_archive_basename': ARCHIVE_NAME,
            'offline_capsule_integrity': 'passed',
            'receipt_generation_script': 'tools/mame0106_private_native_receipt.py',
            'owner_only_storage_required': True,
            'mame_verifyroms_dino_executed': False,
            'windows_process_started': False,
            'wolfmame_inp_playback_executed': False,
            'physical_switch_tested': False,
            'note': NOTE,
        }
        if any(type(data[key]) is not type(value) or data[key] != value
               for key, value in expected.items()):
            raise EvidenceError('preflight_provenance_mismatch')
        if (type(data['archive_bytes']) is not int or
                data['archive_bytes'] != STAGE371_ARCHIVE_BYTES or
                type(data['synthetic_test_cases_passed']) is not int or
                data['synthetic_test_cases_passed'] != STAGE371_SYNTHETIC_TESTS or
                not _valid_utc_timestamp(data['checked_utc'])):
            raise EvidenceError('invalid_preflight_observation')
        return 'offline_preflight_only'
    if schema == RUNTIME_SCHEMA:
        try:
            validate_receipt_object(data)
        except ReceiptError as exc:
            raise EvidenceError('invalid_runtime_receipt') from exc
        if data['native_rom_verification_status'] == 'native_verified':
            return 'native_positive_local_self_report'
        return 'native_negative_local_self_report'
    raise EvidenceError('unknown_evidence_schema')


def audit(report: Path) -> str:
    return classify_evidence(_read_private_report(report))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--require-native-positive', action='store_true')
    args = parser.parse_args(argv)
    try:
        grade = audit(args.report)
        print('evidence_grade=' + grade)
        print('independent_execution_attestation=False')
        if args.require_native_positive and grade != 'native_positive_local_self_report':
            print('status=private_native_gate_blocked')
            return 3
        print('status=private_evidence_schema_valid')
        return 0
    except (EvidenceError, CapsuleError, OSError, ValueError):
        print('status=private_evidence_refused')
        return 2


if __name__ == '__main__':
    sys.exit(main())
