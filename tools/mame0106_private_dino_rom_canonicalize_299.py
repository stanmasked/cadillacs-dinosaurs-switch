#!/usr/bin/env python3
"""Stage299: verify and privately normalize dino ROM ZIP by source MAME hashes.

Reference ROM checksums are PUBLIC metadata from the historical MAME 0.106
cps1.c driver (ROM_START(dino)), not redistributed original ROM bytes.
Actual private input/output archives must never be put in GitHub, Actions,
PR attachments or a publicly downloadable artifact.

The tool does NOT run MAME, authenticate WolfMAME or verify gameplay.
It reports counts/booleans only, without file paths or content digests.
"""
import argparse
import hashlib
import os
import re
import stat
import zipfile
from pathlib import Path

try:
    from . import wolfmame0106_private_binary_gate as gate
except ImportError:
    import wolfmame0106_private_binary_gate as gate

SCHEMA = "dino-private-mame0106-rom-hash-canonicalization-v1"
MATCH = "PRIVATE_DINO_ROM_HASHES_MATCH_UPSTREAM_MAME0106"
WRITTEN = "PRIVATE_DINO_ROM_CANONICAL_ZIP_READY_UNAUTHENTICATED"
BLOCKED = "BLOCKED_PRIVATE_DINO_ROM_HASH_VALIDATION"
# filename, uncompressed length, CRC32, SHA1 of bytes: exact historical
# mamedev/historic-mame mame0106 src/drivers/cps1.c ROM_START(dino).
MANIFEST = (
    ("cde_23a.rom", 0x80000, "8f4e585e", "55ecba3652066cdafad140c4524b1fc81228e69b"),
    ("cde_22a.rom", 0x80000, "9278aa12", "58cbbd53a98abe640ccb233f8dbd8ca6d63475e7"),
    ("cde_21a.rom", 0x80000, "66d23de2", "19b8a365f630411d524d055459020f4c8cf930f1"),
    ("cd_gfx01.rom", 0x80000, "8da4f917", "4f7b2304b7d9b545d6707d7ec921d3e28200699d"),
    ("cd_gfx03.rom", 0x80000, "6c40f603", "cdbd11dfcec08e87355d7e21e9fd39f7eacab016"),
    ("cd_gfx02.rom", 0x80000, "09c8fc2d", "d0c0a1258ec5dd484ab6ec1c5663425431f929ee"),
    ("cd_gfx04.rom", 0x80000, "637ff38f", "859926b33b9955b3ed67471c61faa442d42b9696"),
    ("cd_gfx05.rom", 0x80000, "470befee", "a42e38319e9b7424381352512f11bd8edf0bbb96"),
    ("cd_gfx07.rom", 0x80000, "22bfb7a3", "c44959bd3d42b9fc8ecb482dfaf63fbd469d2c3e"),
    ("cd_gfx06.rom", 0x80000, "e7599ac4", "0e788a38547a8701115d01190ddeaca64388db4d"),
    ("cd_gfx08.rom", 0x80000, "211b4b15", "374f6b185faa0f14f5c45b9b1d60d0772d93fb17"),
    ("cd_q.rom",     0x20000, "605fdb0b", "9da90ddc6513aaaf2260f0c69719c6b0e585ba8c"),
    ("cd_q1.rom",    0x80000, "60927775", "f8599bc84c38573ebbe8685822c58b6a38b50462"),
    ("cd_q2.rom",    0x80000, "770f4c47", "fec8ef00a6669d4d5e37787ecc7b58ee46709326"),
    ("cd_q3.rom",    0x80000, "2f273ffc", "f0de462f6c4d251911258e0ebd886152c14d1586"),
    ("cd_q4.rom",    0x80000, "2c67821d", "6e2528d0b22508300a6a142a796dd3bf53a66946"),
)
MAX_ZIP_BYTES = 32 * 1024 * 1024
MAX_MEMBERS = 96
MAX_MEMBER_BYTES = 1024 * 1024
MAX_EXPANDED_BYTES = 24 * 1024 * 1024
PLAIN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def _private_regular(path, maximum):
    path = Path(path)
    if (not gate.outside_repo(path) or not gate.is_regular(path)
            or any(p.is_symlink() for p in path.parents)
            or not 0 < path.stat().st_size <= maximum):
        raise ValueError("unsafe or overbudget private ROM archive")
    return path


def _safe_target(path):
    path = Path(path)
    if (not gate.outside_repo(path) or path.is_symlink() or path.exists()
            or not path.parent.is_dir() or path.parent.is_symlink()
            or any(a.is_symlink() for a in path.parent.parents)
            or not gate.outside_repo(path.parent)):
        raise ValueError("private canonical ZIP needs a fresh external path")
    return path


def _scan(archive, manifest=MANIFEST):
    """Return private matches and count. Neither strings nor bytes are logged."""
    if not manifest or len(manifest) > MAX_MEMBERS:
        raise ValueError("invalid expected ROM reference")
    expected = {}
    for name, size, crc, sha1 in manifest:
        if (name in expected or PLAIN_NAME.fullmatch(name) is None or
                type(size) is not int or not 0 < size <= MAX_MEMBER_BYTES or
                type(crc) is not str or len(crc) != 8 or
                type(sha1) is not str or len(sha1) != 40):
            raise ValueError("malformed expected ROM manifest")
        expected[name] = (size, crc.lower(), sha1.lower())
    infos = archive.infolist()
    if not 1 <= len(infos) <= MAX_MEMBERS:
        raise ValueError("unsafe ROM ZIP member count")
    if sum(i.file_size for i in infos) > MAX_EXPANDED_BYTES:
        raise ValueError("ROM ZIP extraction budget exceeded")
    seen = set()
    matched = {}
    for info in infos:
        name = info.filename
        mode = info.external_attr >> 16
        if (PLAIN_NAME.fullmatch(name) is None
                or name.casefold() in seen
                or info.is_dir() or stat.S_ISLNK(mode)
                or info.flag_bits & 0x1
                or not 0 < info.file_size <= MAX_MEMBER_BYTES
                or not 0 < info.compress_size <= MAX_ZIP_BYTES):
            raise ValueError("unsafe, duplicate or encrypted ROM ZIP member")
        seen.add(name.casefold())
        # Accept mislabeled archive members by content identity; the
        # canonical MAME filenames are the names from the public driver.
        candidates = [
            wanted for wanted, (size, crc, _sha) in expected.items()
            if info.file_size == size and f"{info.CRC:08x}" == crc
        ]
        if not candidates:
            continue  # Extras are ignored, never copied to canonical ZIP.
        if len(candidates) > 1:
            raise ValueError("ambiguous expected ROM metadata")
        wanted = candidates[0]
        with archive.open(info, "r") as member:
            data = member.read(MAX_MEMBER_BYTES + 1)
        if len(data) != info.file_size:
            raise ValueError("truncated or overlong ROM ZIP member")
        if hashlib.sha1(data).hexdigest() != expected[wanted][2]:
            raise ValueError("source ROM SHA1 mismatch")
        if wanted in matched:
            raise ValueError("duplicate source payload for one required ROM")
        matched[wanted] = info
    if set(matched) != set(expected):
        raise ValueError("missing expected historical dino ROM payloads")
    return matched, len(infos) - len(matched)


def verify_archive(source, *, manifest=MANIFEST):
    source = _private_regular(source, MAX_ZIP_BYTES)
    with zipfile.ZipFile(source, "r") as archive:
        matched, ignored = _scan(archive, manifest)
    return {
        "schema": SCHEMA,
        "status": MATCH,
        "required_rom_members_matched_by_crc32_sha1": len(matched),
        "extra_source_archive_members_ignored": ignored,
        "original_archive_integrity_checked": True,
        "canonical_mame_zip_written": False,
        "all_original_payload_bytes_kept_private": True,
        "source_mame_driver_hashes_are_public_reference_only": True,
        "actual_historical_mame_rom_loader_verified": False,
        "original_dino_gameplay_verified": False,
        "wolfmame_inp_replay_verified": False,
        "physical_nintendo_switch_tested": False,
        "private_paths_raw_rom_and_archive_hashes_exported": False,
    }


def canonicalize(source, output, *, manifest=MANIFEST):
    """Write a private *new* ZIP with only canonical MAME filenames."""
    source = _private_regular(source, MAX_ZIP_BYTES)
    output = _safe_target(output)
    # Always finish all source hash checks before creating any output.
    result = verify_archive(source, manifest=manifest)
    fd = None
    try:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(output, flags, 0o600)
        with os.fdopen(fd, "wb") as handle:
            fd = None
            with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6) as dst:
                with zipfile.ZipFile(source, "r") as original:
                    entries, _ignored = _scan(original, manifest)
                    for name, size, crc, sha1 in manifest:
                        raw = original.read(entries[name])
                        if len(raw) != size or hashlib.sha1(raw).hexdigest() != sha1:
                            raise ValueError("original source changed before private output")
                        member = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                        member.compress_type = zipfile.ZIP_DEFLATED
                        dst.writestr(member, raw, compress_type=zipfile.ZIP_DEFLATED)
        # Independently validate the newly created canonical ZIP.
        with zipfile.ZipFile(output, "r") as again:
            rechecked, extras = _scan(again, manifest)
            if extras or {i.filename for i in rechecked.values()} != set(rechecked):
                raise ValueError("canonical output unexpectedly contains extra or wrong names")
        result["status"] = WRITTEN
        result["canonical_mame_zip_written"] = True
        return result
    except Exception:
        if fd is not None:
            os.close(fd)
        output.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path,
                        help="private input archive outside GitHub repository")
    parser.add_argument("--output", type=Path,
                        help="fresh private dino.zip path; omit for read-only inspection")
    parser.add_argument("--report", type=Path,
                        help="fresh optional PRIVATE aggregate-only receipt path")
    args = parser.parse_args(argv)
    try:
        result = (canonicalize(args.source, args.output)
                  if args.output is not None else verify_archive(args.source))
    except (OSError, ValueError, TypeError, UnicodeError, zipfile.BadZipFile):
        result = {
            "schema": SCHEMA, "status": BLOCKED,
            "required_rom_members_matched_by_crc32_sha1": 0,
            "canonical_mame_zip_written": False,
            "actual_historical_mame_rom_loader_verified": False,
            "original_dino_gameplay_verified": False,
            "wolfmame_inp_replay_verified": False,
            "private_paths_raw_rom_and_archive_hashes_exported": False,
        }
    if args.report is not None:
        gate.write_private_receipt(args.report, result)
    print(result["status"])
    return 0 if result["status"] in (MATCH, WRITTEN) else 2


if __name__ == "__main__":
    raise SystemExit(main())
