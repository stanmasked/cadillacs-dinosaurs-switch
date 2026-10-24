"""Stage380: deterministic ROM-free helper ZIP for an owner-private Windows host.

Build only from an explicit inventory of public Python source. Never ingest
the owner's ROM, historical MAME EXE, recordings, or extracted game data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import zipfile

SCHEMA = "cadillacs-stage380-owner-private-python-helper-romfree-v1"
MODULES = (
    "tools/mame0106_romfree_native_windows_probe.py",
    "tools/mame0106_private_rom_name_adapter.py",
    "tools/mame0106_private_verifyroms.py",
    "tools/mame0106_private_windows_capsule.py",
    "tools/mame0106_private_native_receipt.py",
    "tools/mame0106_private_evidence_gate.py",
    "tools/mame0106_private_execution_session.py",
    "tools/mame0106_private_session_audit.py",
    "tools/mame0106_private_helper_handoff.py",
)
INSTRUCTIONS = "STAGE380-PRIVATE-WINDOWS-RUNBOOK.txt"
MANIFEST = "STAGE380-SHA256-MANIFEST.json"
MAX_SOURCE_BYTES = 150_000
MAX_ARCHIVE_BYTES = 500_000
REVISION = re.compile(r"[a-f0-9]{40}\Z")
RUNBOOK = """Cadillacs and Dinosaurs Remake — Stage380 owner-private Windows helper
=====================================================================
This archive contains PUBLIC SOURCE CODE ONLY. No ROM, MAME executable,
original input recording, private frames or emulator captures.

Requirements: owner-controlled Windows 10/11 (64-bit) with Python 3.11+
and the original Stage369 private ZIP obtained separately from the
OWNER-ONLY Google Drive archive. Do not use a public GitHub-hosted runner.

1. Verify this ZIP SHA-256 against the archived owner's handoff manifest.
2. Extract this source-only ZIP into its own clean private helper directory.
3. In PowerShell, change to the extracted helper directory.
4. Independently verify the original *unextracted* ZIP using the bundled
   source-only verifier. Replace <ZIP-PATH> with the real local path:

python -m tools.mame0106_private_helper_handoff --verify "<ZIP-PATH>"

   Require status=romfree_helper_source_only, members=11 and exit code 0.
   If verification refuses or fails, do not execute the private runner.
5. Run genuine owner-private ROM verification (example only):

python -m tools.mame0106_private_execution_session --capsule "C:\\Private\\Stage369_MAME0106_Private_Windows_Verify_Capsule.zip" --session-dir "C:\\Private\\Stage380-first-session"

6. Independently audit its two JSON records:

python -m tools.mame0106_private_session_audit --session-dir "C:\\Private\\Stage380-first-session" --require-native-positive

The session folder must be new, outside this source directory. A positive
result is a LOCAL, UNAUTHENTICATED SELF-REPORT, NOT independent execution
attestation or proof of historical dino.inp playback/physical Switch.
The private original ZIP is NEVER a member of this helper archive.

Archive the local JSON receipt and manifest and their SHA-256 checksums
in the owner-only Project Evidence Archive / 03_Aggregate_Reports on
Google Drive, verify permission and exact download SHA-256 first, and
only then consider clearing temporary local copies. Keep original ZIP
and extracted game data entirely private. Do not upload to public CI.
"""


class HandoffError(Exception):
    """Stable, non-private refusal identifier only."""


def _entry(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100644 << 16
    return info


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _safe_source(path: Path) -> bytes:
    if not path.is_file() or path.is_symlink():
        raise HandoffError("missing_or_linked_source")
    metadata = path.stat(follow_symlinks=False)
    if (not stat.S_ISREG(metadata.st_mode) or
            bool(getattr(metadata, "st_file_attributes", 0) &
                 getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)) or
            not 0 < metadata.st_size <= MAX_SOURCE_BYTES):
        raise HandoffError("unsafe_source_metadata")
    raw = path.read_bytes()
    if len(raw) != metadata.st_size:
        raise HandoffError("source_changed_during_read")
    if b"\x00" in raw:
        raise HandoffError("binary_source_forbidden")
    return raw


def build(root: Path, out: Path, source_revision: str) -> dict[str, object]:
    """Deterministic, exclusive ZIP; never walk directories or include glob data."""
    if not REVISION.fullmatch(source_revision):
        raise HandoffError("invalid_source_revision")
    if out.exists() or out.is_symlink() or not out.parent.is_dir():
        raise HandoffError("output_must_be_new")
    root = root.resolve(strict=True)
    sources: dict[str, bytes] = {}
    for name in MODULES:
        sources[name] = _safe_source(root / name)
    sources[INSTRUCTIONS] = RUNBOOK.encode("utf-8")
    metadata = {
        "schema": SCHEMA,
        "stage": "Stage380",
        "source_revision": source_revision,
        "game_private_inputs_included": False,
        "mame_executable_included": False,
        "historical_inp_playback_executed": False,
        "files": {
            name: {"sha256": _digest(data), "bytes": len(data)}
            for name, data in sorted(sources.items())
        },
    }
    sources[MANIFEST] = (json.dumps(metadata, sort_keys=True, indent=2) + "\n").encode()
    with zipfile.ZipFile(out, "x", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=9) as archive:
        for name, data in sorted(sources.items()):
            archive.writestr(_entry(name), data)
    try:
        checked = verify(out, expected_revision=source_revision)
    except HandoffError:
        # Preserve failed output rather than overwriting/disguising it.
        raise
    if checked["size"] > MAX_ARCHIVE_BYTES:
        raise HandoffError("helper_archive_oversized")
    return checked


def verify(archive_path: Path, *, expected_revision: str | None = None) -> dict[str, object]:
    """Validate inventory, CRC, source hashes and ROM-free-only assertions."""
    if not archive_path.is_file() or archive_path.is_symlink():
        raise HandoffError("missing_or_linked_archive")
    archive_size = archive_path.stat().st_size
    if not 0 < archive_size <= MAX_ARCHIVE_BYTES:
        raise HandoffError("unsafe_archive_size")
    try:
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            inventory = set(MODULES) | {INSTRUCTIONS, MANIFEST}
            if len(infos) != len(inventory) or {i.filename for i in infos} != inventory:
                raise HandoffError("archive_inventory_mismatch")
            if any(i.flag_bits & 1 or i.is_dir() or
                   stat.S_IFMT(i.external_attr >> 16) != stat.S_IFREG or
                   i.file_size <= 0 or i.file_size > MAX_SOURCE_BYTES
                   for i in infos):
                raise HandoffError("unsafe_archive_member")
            if archive.testzip() is not None:
                raise HandoffError("archive_crc_mismatch")
            raw_manifest = archive.read(MANIFEST)
            if len(raw_manifest) > 8192:
                raise HandoffError("manifest_oversized")
            manifest = json.loads(raw_manifest.decode("utf-8"))
            if (type(manifest) is not dict or set(manifest) != {
                    "schema", "stage", "source_revision",
                    "game_private_inputs_included", "mame_executable_included",
                    "historical_inp_playback_executed", "files"} or
                    manifest["schema"] != SCHEMA or manifest["stage"] != "Stage380" or
                    manifest["game_private_inputs_included"] is not False or
                    manifest["mame_executable_included"] is not False or
                    manifest["historical_inp_playback_executed"] is not False or
                    type(manifest["source_revision"]) is not str or
                    not REVISION.fullmatch(manifest["source_revision"]) or
                    (expected_revision is not None and
                     manifest["source_revision"] != expected_revision) or
                    type(manifest["files"]) is not dict or
                    set(manifest["files"]) != (inventory - {MANIFEST})):
                raise HandoffError("invalid_helper_manifest")
            for name in sorted(inventory - {MANIFEST}):
                row = manifest["files"][name]
                data = archive.read(name)
                if (type(row) is not dict or set(row) != {"sha256", "bytes"} or
                        type(row["sha256"]) is not str or
                        type(row["bytes"]) is not int or
                        row["sha256"] != _digest(data) or row["bytes"] != len(data)):
                    raise HandoffError("helper_member_digest_mismatch")
    except (OSError, zipfile.BadZipFile, UnicodeError, ValueError,
            KeyError, TypeError, RuntimeError) as exc:
        raise HandoffError("invalid_helper_archive") from exc
    return {
        "status": "romfree_helper_source_only",
        "sha256": _digest(archive_path.read_bytes()),
        "size": archive_size,
        "members": len(inventory),
        "source_revision": manifest["source_revision"],
        "private_game_execution": "not_executed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--output", type=Path)
    actions.add_argument("--verify", type=Path)
    parser.add_argument("--source-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-revision", default="0"*40)
    parser.add_argument("--expected-revision")
    args = parser.parse_args(argv)
    try:
        if args.output is not None and args.expected_revision is not None:
            raise HandoffError("expected_revision_for_verify_only")
        result = (build(args.source_root, args.output, args.source_revision)
                  if args.output is not None
                  else verify(args.verify, expected_revision=args.expected_revision))
        for key, value in result.items():
            print(f"{key}={value}")
        return 0
    except (HandoffError, OSError, ValueError):
        print("status=helper_archive_refused")
        return 2


if __name__ == "__main__":
    sys.exit(main())
