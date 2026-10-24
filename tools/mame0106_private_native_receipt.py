"""Owner-only Stage369 Windows launch, bounded outcome and local evidence receipt.

No ROM, INP or actual stdout is sent to GitHub Actions, console, or public
artifacts. A receipt is a *local self-report*, not cryptographic attestation.
This script refuses real invocation on public CI and on non-Windows platforms.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
import zipfile

from tools.mame0106_private_verifyroms import EXE_SHA, PINNED_ROM_SHA256, PINNED_XML_SHA256
from tools.mame0106_private_windows_capsule import (
    POWERSHELL, REPO_ROOT, CapsuleError, guard_private, hashfile,
    require_private_file, validate_capsule,
)

# This hash identifies the exact Stage369 owner-only capsule that underwent
# ZIP roundtrip and owner-only Drive readback verification.
STAGE369_SHA256 = 'fa6ff589b109db70c8231bf7713ec50cf5b9a15b58e43bb3b6705bc25e4bd19d'
POWERSHELL_SHA256 = hashlib.sha256(POWERSHELL.encode('utf-8')).hexdigest()
SCHEMA = 'cadillacs-stage371-private-windows-local-observation-v1'
ATTESTATION = 'local_self_report_not_cryptographically_authenticated'
EXPECTED_LINES = ('status=native_verified', 'game=dino', 'recording_playback=not_executed')
FIXED_FILES = ('mame0106.exe', 'roms/dino.zip', 'verifyroms.ps1', 'capsule.json')
MAX_SCRIPT_OUTPUT = 8192


class ReceiptError(Exception):
    """Errors contain a fixed identifier, never untrusted or private paths."""


def _windows_owner_guard() -> None:
    guard_private()
    if os.name != 'nt':
        raise ReceiptError('private_windows_host_required')


def _safe_receipt_path(path: Path) -> None:
    if (path.exists() or path.is_symlink() or not path.parent.is_dir() or
            path.parent.is_symlink() or path.name in ('', '.', '..')):
        raise ReceiptError('unsafe_receipt_destination')
    parent = path.parent.resolve()
    if parent == REPO_ROOT or REPO_ROOT in parent.parents:
        raise ReceiptError('public_repository_destination_forbidden')


def _validate_stage369_capsule(archive: Path) -> dict[str, object]:
    guard_private()
    require_private_file(archive, 55 * 1024 * 1024)
    verified = validate_capsule(
        archive,
        archive_sha=STAGE369_SHA256,
        rom_sha=PINNED_ROM_SHA256,
        exe_sha=EXE_SHA,
        xml_sha=PINNED_XML_SHA256,
    )
    if verified.get('status') != 'offline_capsule_integrity_pass':
        raise ReceiptError('capsule_not_validated')
    return verified


def _observed_lines(raw: bytes) -> tuple[str, ...]:
    if len(raw) > MAX_SCRIPT_OUTPUT:
        raise ReceiptError('untrusted_script_output_size')
    try:
        text = raw.decode('utf-8-sig', errors='strict')
    except UnicodeError as exc:
        raise ReceiptError('untrusted_script_output_encoding') from exc
    text = text.replace('\r\n', '\n')
    if text.endswith('\n'):
        text = text[:-1]
    return tuple(text.split('\n'))


def _observed_result(exit_code: int, stdout: bytes, stderr: bytes) -> dict[str, object]:
    if type(exit_code) is not int or not -65535 <= exit_code <= 65535:
        raise ReceiptError('untrusted_process_return_code')
    if stderr or len(stdout) > MAX_SCRIPT_OUTPUT:
        return {'status': 'not_verified', 'process_exit_code': exit_code,
                'exact_status_lines': False}
    matches = _observed_lines(stdout) == EXPECTED_LINES
    return {'status': 'native_verified' if exit_code == 0 and matches else 'not_verified',
            'process_exit_code': exit_code, 'exact_status_lines': matches}


def _build_receipt(observation: dict[str, object], *,
                   nonce: str | None = None, when: str | None = None) -> dict[str, object]:
    if observation.get('status') not in ('native_verified', 'not_verified'):
        raise ReceiptError('untrusted_observation')
    code = observation.get('process_exit_code')
    if type(code) is not int or not -65535 <= code <= 65535:
        raise ReceiptError('untrusted_return_code')
    match = observation.get('exact_status_lines')
    if type(match) is not bool or (observation['status'] == 'native_verified') != (code == 0 and match):
        raise ReceiptError('inconsistent_observation')
    nonce = nonce or secrets.token_hex(16)
    when = when or datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    return {
        'schema': SCHEMA,
        'evidence_type': ATTESTATION,
        'game': 'dino',
        'emulator': 'source-pinned-MAME-0.106-Windows',
        'capsule_sha256': STAGE369_SHA256,
        'mame_executable_sha256': EXE_SHA,
        'private_rom_sha256': PINNED_ROM_SHA256,
        'windows_script_sha256': POWERSHELL_SHA256,
        'local_session_nonce': nonce,
        'completed_utc': when,
        'local_windows_powershell_invoked': True,
        'local_process_exited': True,
        'native_rom_verification_status': observation['status'],
        'powershell_process_exit_code': code,
        'exact_three_line_result': match,
        'wolfmame_inp_playback_executed': False,
        'physical_nintendo_switch_verified': False,
        'no_original_rom_or_raw_output_embedded': True,
    }


def validate_receipt_object(receipt: object) -> bool:
    """Validate the local receipt schema; this cannot prove a host is honest."""
    if type(receipt) is not dict:
        raise ReceiptError('invalid_receipt_document')
    expected = _build_receipt({'status': 'not_verified', 'process_exit_code': 2,
                               'exact_status_lines': False},
                              nonce='0'*32, when='2026-10-24T00:00:00Z')
    if set(receipt) != set(expected):
        raise ReceiptError('receipt_schema_mismatch')
    for key in ('schema', 'evidence_type', 'game', 'emulator', 'capsule_sha256',
                'mame_executable_sha256', 'private_rom_sha256', 'windows_script_sha256'):
        if type(receipt[key]) is not str or receipt[key] != expected[key]:
            raise ReceiptError('receipt_provenance_mismatch')
    for field in ('local_windows_powershell_invoked', 'local_process_exited',
                  'no_original_rom_or_raw_output_embedded'):
        if receipt[field] is not True:
            raise ReceiptError('receipt_missing_observation')
    for field in ('wolfmame_inp_playback_executed', 'physical_nintendo_switch_verified'):
        if receipt[field] is not False:
            raise ReceiptError('receipt_unsupported_claim')
    if (type(receipt['local_session_nonce']) is not str or
            re.fullmatch(r'[0-9a-f]{32}', receipt['local_session_nonce']) is None):
        raise ReceiptError('receipt_bad_nonce')
    stamp = receipt['completed_utc']
    if (type(stamp) is not str or len(stamp) > 40 or
            re.fullmatch(r'20\d\d-[01]\d-[0-3]\dT[0-2]\d:[0-5]\d:[0-5]\d(?:\.\d{1,6})?Z', stamp) is None):
        raise ReceiptError('receipt_bad_timestamp')
    if type(receipt['exact_three_line_result']) is not bool:
        raise ReceiptError('receipt_bad_result_type')
    if type(receipt['powershell_process_exit_code']) is not int:
        raise ReceiptError('receipt_bad_exit_code')
    obs = {'status': receipt['native_rom_verification_status'],
           'process_exit_code': receipt['powershell_process_exit_code'],
           'exact_status_lines': receipt['exact_three_line_result']}
    _build_receipt(obs, nonce=receipt['local_session_nonce'], when=stamp)
    return True


def _write_receipt(path: Path, receipt: dict[str, object]) -> None:
    _safe_receipt_path(path)
    validate_receipt_object(receipt)
    payload = (json.dumps(receipt, sort_keys=True, indent=2, ensure_ascii=True) + '\n').encode('ascii')
    if len(payload) > 4096:
        raise ReceiptError('receipt_too_large')
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
    except FileExistsError as exc:
        raise ReceiptError('receipt_already_exists') from exc


def _snapshot_private_capsule(archive: Path, snapshot: Path) -> None:
    """Copy into a unique private staging file, pinning the bytes actually read.

    A source file replaced after the earlier preflight must not be executed.
    The source file itself is never modified or published.
    """
    guard_private()
    require_private_file(archive, 55 * 1024 * 1024)
    digest = hashlib.sha256()
    total = 0
    with archive.open('rb') as source, snapshot.open('xb') as target:
        while True:
            block = source.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > 55 * 1024 * 1024:
                raise ReceiptError('private_snapshot_oversized')
            digest.update(block)
            target.write(block)
        target.flush()
        os.fsync(target.fileno())
    if total == 0 or digest.hexdigest() != STAGE369_SHA256:
        raise ReceiptError('private_snapshot_digest_mismatch')
    # Read back the staged copy; do not trust a just-computed stream digest
    # as proof that the destination persisted exactly the same bytes.
    recorded_sha, recorded_bytes = hashfile(snapshot)
    if recorded_bytes != total or recorded_sha != STAGE369_SHA256:
        raise ReceiptError('private_snapshot_readback_mismatch')


def _stage_and_execute(archive: Path) -> dict[str, object]:
    # Owner-private execution. Bind a fresh copy to the actual tested digest,
    # then unpack ONLY that copy. Never unzip an unchecked mutable source.
    guard_private()
    with tempfile.TemporaryDirectory(prefix='cadillacs-stage377-private-') as tmp:
        root = Path(tmp)
        snapshot = root / 'validated-stage369-source.zip'
        _snapshot_private_capsule(archive, snapshot)
        _validate_stage369_capsule(snapshot)
        with zipfile.ZipFile(snapshot) as z:
            for member in FIXED_FILES:
                path = root / member
                path.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as src, path.open('xb') as dest:
                    while chunk := src.read(1024*1024):
                        dest.write(chunk)
        # Detect changes to the immutable staging ZIP even during extraction.
        if hashfile(snapshot)[0] != STAGE369_SHA256:
            raise ReceiptError('private_snapshot_changed_during_extraction')
        try:
            process = subprocess.run(
                ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
                 '-File', str(root / 'verifyroms.ps1')],
                cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=135, check=False,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ReceiptError('private_powershell_execution_not_completed') from exc
        return _observed_result(process.returncode, process.stdout, process.stderr)


def run(archive: Path, receipt_path: Path) -> dict[str, object]:
    _windows_owner_guard()
    _safe_receipt_path(receipt_path)
    _validate_stage369_capsule(archive)
    observation = _stage_and_execute(archive)
    receipt = _build_receipt(observation)
    _write_receipt(receipt_path, receipt)
    return {'status': observation['status'], 'receipt_written': True,
            'recording_playback': 'not_executed'}


def verify_only(archive: Path) -> dict[str, object]:
    """Offline source integrity only; DOES NOT create a native success claim."""
    _validate_stage369_capsule(archive)
    return {'status': 'offline_integrity_pass_execution_not_attempted',
            'capsule_sha256': STAGE369_SHA256,
            'native_mame_verification_executed': False}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capsule', type=Path, required=True)
    p.add_argument('--receipt', type=Path)
    p.add_argument('--verify-only', action='store_true')
    args = p.parse_args(argv)
    try:
        if args.verify_only:
            if args.receipt:
                raise ReceiptError('receipt_not_allowed_for_offline_audit')
            info = verify_only(args.capsule)
        else:
            if args.receipt is None:
                raise ReceiptError('private_receipt_destination_required')
            info = run(args.capsule, args.receipt)
        for k, v in info.items():
            print(f'{k}={v}')
        return 0 if info['status'] != 'not_verified' else 2
    except (ReceiptError, CapsuleError, OSError, ValueError, zipfile.BadZipFile):
        print('status=private_execution_or_audit_refused')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
