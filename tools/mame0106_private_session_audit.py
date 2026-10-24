"""Stage379: offline audit of a completed owner-private Stage376 MAME session.

Reads two small JSON files only. Does not launch MAME, read the original ROM,
or prove that a Windows process really ran. A valid positive receipt remains
a *local, unauthenticated self-report*, never independent attestation.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

from tools import mame0106_private_evidence_gate as gate
from tools import mame0106_private_execution_session as session
from tools import mame0106_private_native_receipt as native
from tools.mame0106_private_windows_capsule import REPO_ROOT, CapsuleError, guard_private

MANIFEST_FIELDS = frozenset({
    "schema", "stage", "game", "created_utc", "capsule_sha256",
    "receipt_file", "receipt_sha256", "receipt_bytes", "evidence_grade",
    "local_self_report_only", "native_rom_verification_positive",
    "wolfmame_inp_playback_executed", "physical_nintendo_switch_verified",
    "owner_only_archive_required",
})
EXPECTED_FILES = frozenset((session.RECEIPT_NAME, session.MANIFEST_NAME))
MAX_JSON_BYTES = 4096


class SessionAuditError(Exception):
    """Fixed error identifiers; never place private filenames or data in errors."""


def _identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return metadata.st_dev, metadata.st_ino, metadata.st_size


def _link_or_reparse(path: Path) -> bool:
    metadata = path.lstat()
    return (stat.S_ISLNK(metadata.st_mode) or
            bool(getattr(metadata, "st_file_attributes", 0) &
                 getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)))


def _safe_directory(folder: Path) -> None:
    guard_private()
    if not folder.is_dir() or _link_or_reparse(folder):
        raise SessionAuditError("unsafe_session_directory")
    if any(_link_or_reparse(parent) for parent in folder.parents):
        raise SessionAuditError("unsafe_session_ancestor")
    real = folder.resolve()
    if real == REPO_ROOT or REPO_ROOT in real.parents:
        raise SessionAuditError("session_within_public_repository")
    if {child.name for child in folder.iterdir()} != EXPECTED_FILES:
        raise SessionAuditError("unexpected_session_inventory")


def _read_small_private_file(file: Path) -> bytes:
    if _link_or_reparse(file):
        raise SessionAuditError("session_member_link_forbidden")
    before = file.stat(follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_JSON_BYTES:
        raise SessionAuditError("invalid_session_member_size")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(file, flags)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        after = file.stat(follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or _link_or_reparse(file) or
                _identity(before) != _identity(opened) or
                _identity(opened) != _identity(after)):
            raise SessionAuditError("session_member_swapped")
        data = stream.read(MAX_JSON_BYTES + 1)
        if _identity(opened) != _identity(os.fstat(stream.fileno())):
            raise SessionAuditError("session_member_changed")
    if len(data) != before.st_size:
        raise SessionAuditError("session_member_length_changed")
    return data


def _parse_exact_json(payload: bytes) -> dict[str, object]:
    try:
        parsed = json.loads(
            payload.decode("utf-8"), object_pairs_hook=gate._unique_object,
            parse_constant=lambda _token: gate._reject_nonfinite_json(),
        )
    except (UnicodeError, json.JSONDecodeError, gate.EvidenceError) as exc:
        raise SessionAuditError("invalid_session_json") from exc
    if type(parsed) is not dict:
        raise SessionAuditError("session_json_must_be_object")
    return parsed


def audit(folder: Path) -> str:
    """Check the saved evidence consistently; NEVER claim independent execution."""
    _safe_directory(folder)
    receipt_bytes = _read_small_private_file(folder / session.RECEIPT_NAME)
    manifest_bytes = _read_small_private_file(folder / session.MANIFEST_NAME)
    receipt = _parse_exact_json(receipt_bytes)
    manifest = _parse_exact_json(manifest_bytes)
    if set(manifest) != MANIFEST_FIELDS:
        raise SessionAuditError("session_manifest_schema_mismatch")
    expected = {
        "schema": session.SCHEMA,
        "stage": "Stage376",
        "game": "dino",
        "capsule_sha256": native.STAGE369_SHA256,
        "receipt_file": session.RECEIPT_NAME,
        "local_self_report_only": True,
        "wolfmame_inp_playback_executed": False,
        "physical_nintendo_switch_verified": False,
        "owner_only_archive_required": True,
    }
    if any(type(manifest[k]) is not type(v) or manifest[k] != v
           for k, v in expected.items()):
        raise SessionAuditError("session_manifest_provenance_mismatch")
    if (type(manifest["receipt_sha256"]) is not str or
            manifest["receipt_sha256"] != hashlib.sha256(receipt_bytes).hexdigest() or
            type(manifest["receipt_bytes"]) is not int or
            manifest["receipt_bytes"] != len(receipt_bytes)):
        raise SessionAuditError("session_receipt_checksum_mismatch")
    if (type(manifest["created_utc"]) is not str or
            not gate._valid_utc_timestamp(manifest["created_utc"])):
        raise SessionAuditError("session_timestamp_invalid")
    try:
        receipt_grade = gate.classify_evidence(receipt)
    except gate.EvidenceError as exc:
        raise SessionAuditError("invalid_private_runtime_receipt") from exc
    if receipt_grade not in (
            "native_positive_local_self_report", "native_negative_local_self_report"):
        raise SessionAuditError("session_requires_runtime_receipt")
    if (type(manifest["evidence_grade"]) is not str or
            manifest["evidence_grade"] != receipt_grade or
            type(manifest["native_rom_verification_positive"]) is not bool or
            manifest["native_rom_verification_positive"] !=
            (receipt_grade == "native_positive_local_self_report")):
        raise SessionAuditError("session_grade_conflict")
    # Both timestamps come from the self-reporting local host, not trusted time.
    if (datetime.fromisoformat(manifest["created_utc"].replace("Z", "+00:00")) <
            datetime.fromisoformat(receipt["completed_utc"].replace("Z", "+00:00"))):
        raise SessionAuditError("session_manifest_predates_receipt")
    return receipt_grade


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir", type=Path, required=True)
    parser.add_argument("--require-native-positive", action="store_true")
    args = parser.parse_args(argv)
    try:
        grade = audit(args.session_dir)
        print("evidence_grade=" + grade)
        print("independent_execution_attestation=False")
        print("wolfmame_inp_playback_executed=False")
        if args.require_native_positive and grade != "native_positive_local_self_report":
            print("status=private_session_positive_gate_blocked")
            return 3
        print("status=session_integrity_pass_local_self_report_only")
        return 0
    except (SessionAuditError, CapsuleError, OSError, ValueError):
        print("status=private_session_audit_refused")
        return 2


if __name__ == "__main__":
    sys.exit(main())
