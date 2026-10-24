"""Verify and optionally restore a pinned, ROM-free MAME 0.106 technical ZIP.

Offline-only: no network, ROMs, input replays, raw captures, or GitHub upload.
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import tempfile
import zipfile

try:
    from tools.mame0106_romfree_native_windows_probe import EXE_SHA, FILES, SOURCE_PIN, verify_bundle
except ModuleNotFoundError:
    from mame0106_romfree_native_windows_probe import EXE_SHA, FILES, SOURCE_PIN, verify_bundle

ARCHIVE_SHA256 = "5a495bdcbe832dbe1261fc935ef0f8db2f36c7eb21ad3c0be19385d87da5781a"
AUXILIARY = frozenset(("SHA256SUMS.txt", "source-pin.txt", "runtime-status.txt", "MAME-0106-LICENSE.txt"))
CONTENTS = FILES | AUXILIARY
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_SINGLE_BYTES = 128 * 1024 * 1024
MAX_UNPACKED_BYTES = 256 * 1024 * 1024


class ArchiveError(Exception):
    """Fail-closed error with no filename, filesystem path, or private data."""


def hash_stream(stream) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = stream.read(1024 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def audit(path: Path, *, archive_sha: str = ARCHIVE_SHA256,
          exe_sha: str = EXE_SHA, max_unpacked: int = MAX_UNPACKED_BYTES) -> dict[str, str | int]:
    """Read every ZIP member, verify CRC and manifest without unpacking to disk."""
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ArchiveError("invalid_archive_file")
    with path.open("rb") as stream:
        digest, size = hash_stream(stream)
    if digest != archive_sha:
        raise ArchiveError("archive_digest_mismatch")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            entries = archive.infolist()
            names = [e.filename for e in entries]
            if len(entries) != len(CONTENTS) or set(names) != CONTENTS:
                raise ArchiveError("unexpected_inventory")
            total = 0
            for entry in entries:
                if (not re.fullmatch(r"[A-Za-z0-9_.-]+", entry.filename)
                        or entry.is_dir() or (entry.flag_bits & 0x1)
                        or stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK):
                    raise ArchiveError("unsafe_archive_member")
                if entry.file_size > MAX_SINGLE_BYTES or entry.file_size < 0:
                    raise ArchiveError("oversized_member")
                total += entry.file_size
                if total > max_unpacked:
                    raise ArchiveError("oversized_archive_contents")
            with archive.open("SHA256SUMS.txt") as manifest_stream:
                manifest_text = manifest_stream.read(65536).decode("utf-8")
            manifest: dict[str, str] = {}
            for line in manifest_text.splitlines():
                match = re.fullmatch(r"([a-fA-F0-9]{64}) [ *]([A-Za-z0-9_.-]+)", line)
                if not match:
                    raise ArchiveError("bad_manifest")
                sha, name = match.groups()
                if name in manifest:
                    raise ArchiveError("duplicate_manifest_entry")
                manifest[name] = sha.lower()
            if set(manifest) != FILES or manifest.get("mame0106.exe") != exe_sha:
                raise ArchiveError("unpinned_manifest")
            with archive.open("source-pin.txt") as pin_stream:
                if SOURCE_PIN not in pin_stream.read(65536).decode("utf-8").splitlines():
                    raise ArchiveError("source_pin_mismatch")
            for name in sorted(CONTENTS):
                with archive.open(name) as stream:
                    checksum, member_size = hash_stream(stream)
                if member_size != archive.getinfo(name).file_size:
                    raise ArchiveError("size_mismatch")
                if name in manifest and checksum != manifest[name]:
                    raise ArchiveError("member_digest_mismatch")
            with archive.open("mame0106.exe") as binary:
                header = binary.read(4096)
            if len(header) < 0x40 or header[:2] != b"MZ":
                raise ArchiveError("bad_executable_header")
            offset = struct.unpack_from("<I", header, 0x3C)[0]
            if offset + 6 > len(header) or header[offset:offset + 6] != b"PE\x00\x00\x4c\x01":
                raise ArchiveError("wrong_executable_architecture")
    except (zipfile.BadZipFile, RuntimeError, OSError, UnicodeError, ValueError, EOFError) as exc:
        raise ArchiveError("unreadable_archive") from exc
    return {"archive_bytes": size, "members_verified": len(CONTENTS),
            "technical_hashes_verified": len(FILES), "unpacked_bytes": total}


def restore(path: Path, destination: Path, *, archive_sha: str = ARCHIVE_SHA256,
            exe_sha: str = EXE_SHA) -> None:
    """Extract into an isolated temporary directory, then publish atomically."""
    if destination.exists() or destination.is_symlink():
        raise ArchiveError("destination_already_exists")
    parent = destination.parent.resolve(strict=True)
    if not parent.is_dir():
        raise ArchiveError("invalid_destination_parent")
    audit(path, archive_sha=archive_sha, exe_sha=exe_sha)
    with tempfile.TemporaryDirectory(prefix=".mame0106-restore-", dir=parent) as temp:
        staged = Path(temp) / "bundle"
        staged.mkdir()
        try:
            with zipfile.ZipFile(path) as archive:
                for name in sorted(CONTENTS):
                    with archive.open(name) as src, (staged / name).open("xb") as dst:
                        shutil.copyfileobj(src, dst, length=1024 * 1024)
            verify_bundle(staged, expected_exe_sha=exe_sha)
            os.replace(staged, destination)
        except (OSError, zipfile.BadZipFile, RuntimeError, EOFError) as exc:
            raise ArchiveError("failed_to_restore") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--extract-to", type=Path,
                        help="Optional, must be a new directory under an existing parent")
    args = parser.parse_args(argv)
    try:
        result = audit(args.archive)
        if args.extract_to is not None:
            restore(args.archive, args.extract_to)
        print("schema=mame0106-romfree-archive-restore-v1")
        print("private_data_used=no")
        for key, value in result.items():
            print(f"{key}={value}")
        print("extracted=" + ("yes" if args.extract_to else "no"))
        print("result=pass")
        return 0
    except ArchiveError as exc:
        print("schema=mame0106-romfree-archive-restore-v1")
        print("result=fail")
        print(f"failure_type={exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
