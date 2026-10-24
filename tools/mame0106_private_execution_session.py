"""Stage376 owner-private Windows MAME verification and sealed evidence session.

Never run on public CI. Only pinned private Stage369 capsule may be used; this
command does not play dino.inp and makes no physical Switch claims. Receipts
remain unauthenticated local self-reports, not externally proven executions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from tools import mame0106_private_native_receipt as native
from tools import mame0106_private_evidence_gate as gate
from tools.mame0106_private_windows_capsule import CapsuleError, REPO_ROOT

SCHEMA = 'cadillacs-stage376-private-windows-session-v1'
RECEIPT_NAME = 'stage376-native-receipt.json'
MANIFEST_NAME = 'stage376-session-manifest.json'
MAX_RECEIPT_BYTES = 4096


class SessionError(Exception):
    """Error codes are fixed; do not include private local paths or stdout."""


def _reparse(path: Path) -> bool:
    s = path.lstat()
    return (path.is_symlink() or
            bool(getattr(s, 'st_file_attributes', 0) &
                 getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)))


def _private_new_session_path(target: Path) -> None:
    if target.exists() or target.is_symlink() or not target.parent.is_dir():
        raise SessionError('session_must_be_new_private_directory')
    resolved = target.resolve(strict=False)
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise SessionError('public_repository_session_forbidden')
    if any(_reparse(parent) for parent in target.parents):
        raise SessionError('session_parent_reparse_refused')


def _exclusive_json_file(path: Path, document: dict[str, object]) -> bytes:
    data = (json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True)
            + '\n').encode('ascii')
    if not 0 < len(data) <= MAX_RECEIPT_BYTES:
        raise SessionError('manifest_size_refused')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if path.read_bytes() != data:
        raise SessionError('manifest_readback_mismatch')
    return data


def execute(capsule: Path, output_dir: Path) -> dict[str, object]:
    """Execute once on an owner-controlled Windows host, then seal local report.

    All output files are local, never published to GitHub or printed verbatim.
    On a failed or interrupted session, keep partial evidence privately and
    never upgrade it to a successful execution claim.
    """
    native._windows_owner_guard()
    _private_new_session_path(output_dir)
    output_dir.mkdir(mode=0o700)
    receipt_path = output_dir / RECEIPT_NAME
    outcome = native.run(capsule, receipt_path)
    grade = gate.audit(receipt_path)
    if grade not in ('native_positive_local_self_report',
                     'native_negative_local_self_report'):
        raise SessionError('native_receipt_missing_or_untrusted')
    if (outcome['status'] == 'native_verified') != (
            grade == 'native_positive_local_self_report'):
        raise SessionError('native_execution_evidence_disagrees')
    receipt = receipt_path.read_bytes()
    if not 0 < len(receipt) <= MAX_RECEIPT_BYTES:
        raise SessionError('receipt_size_refused')
    receipt_sha = hashlib.sha256(receipt).hexdigest()
    stamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    manifest = {
        'schema': SCHEMA,
        'stage': 'Stage376',
        'game': 'dino',
        'created_utc': stamp,
        'capsule_sha256': native.STAGE369_SHA256,
        'receipt_file': RECEIPT_NAME,
        'receipt_sha256': receipt_sha,
        'receipt_bytes': len(receipt),
        'evidence_grade': grade,
        'local_self_report_only': True,
        'native_rom_verification_positive': grade == 'native_positive_local_self_report',
        'wolfmame_inp_playback_executed': False,
        'physical_nintendo_switch_verified': False,
        'owner_only_archive_required': True,
    }
    _exclusive_json_file(output_dir / MANIFEST_NAME, manifest)
    if hashlib.sha256(receipt_path.read_bytes()).hexdigest() != receipt_sha:
        raise SessionError('receipt_readback_mismatch')
    return {'status': ('native_positive_local_self_report'
                       if manifest['native_rom_verification_positive']
                       else 'native_negative_local_self_report'),
            'receipt_sha256': receipt_sha,
            'owner_only_archive_required': True,
            'recording_playback': 'not_executed'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capsule', type=Path, required=True)
    parser.add_argument('--session-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        outcome = execute(args.capsule, args.session_dir)
        print('status=' + outcome['status'])
        print('owner_only_archive_required=True')
        print('independent_execution_attestation=False')
        print('recording_playback=not_executed')
        return 0 if outcome['status'] == 'native_positive_local_self_report' else 3
    except (SessionError, CapsuleError, native.ReceiptError,
            gate.EvidenceError, OSError, ValueError):
        print('status=private_session_refused')
        return 2


if __name__ == '__main__':
    sys.exit(main())
