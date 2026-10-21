#!/usr/bin/env python3
"""Stage282: private ZIP relabeling to match the original MAME 0.106 dino driver.

The sixteen SHA-1/CRC/length requirements are public metadata from
mamedev/historic-mame tag mame0106, src/drivers/cps1.c, ROM_START(dino).
ROM bytes are read ONLY from the user's private source archive, never
downloaded, altered, printed, committed, or sent to GitHub by this tool.
"""
import argparse
import hashlib
import os
import stat
import zipfile
from pathlib import Path

try:
    from . import wolfmame0106_private_binary_gate as gate
except ImportError:
    import wolfmame0106_private_binary_gate as gate

# Canonical name -> (byte length, CRC-32 hex, SHA-1 hex), historical MAME 0.106.
# This intentionally omits modern-era auxiliary PLDs/BIOS; it does not make
# assertions about a specific WolfMAME executable or its emulator behavior.
REQUIRED = {
    "cde_23a.rom": (524288, "8f4e585e", "55ecba3652066cdafad140c4524b1fc81228e69b"),
    "cde_22a.rom": (524288, "9278aa12", "58cbbd53a98abe640ccb233f8dbd8ca6d63475e7"),
    "cde_21a.rom": (524288, "66d23de2", "19b8a365f630411d524d055459020f4c8cf930f1"),
    "cd_gfx01.rom": (524288, "8da4f917", "4f7b2304b7d9b545d6707d7ec921d3e28200699d"),
    "cd_gfx03.rom": (524288, "6c40f603", "cdbd11dfcec08e87355d7e21e9fd39f7eacab016"),
    "cd_gfx02.rom": (524288, "09c8fc2d", "d0c0a1258ec5dd484ab6ec1c5663425431f929ee"),
    "cd_gfx04.rom": (524288, "637ff38f", "859926b33b9955b3ed67471c61faa442d42b9696"),
    "cd_gfx05.rom": (524288, "470befee", "a42e38319e9b7424381352512f11bd8edf0bbb96"),
    "cd_gfx07.rom": (524288, "22bfb7a3", "c44959bd3d42b9fc8ecb482dfaf63fbd469d2c3e"),
    "cd_gfx06.rom": (524288, "e7599ac4", "0e788a38547a8701115d01190ddeaca64388db4d"),
    "cd_gfx08.rom": (524288, "211b4b15", "374f6b185faa0f14f5c45b9b1d60d0772d93fb17"),
    "cd_q.rom": (131072, "605fdb0b", "9da90ddc6513aaaf2260f0c69719c6b0e585ba8c"),
    "cd_q1.rom": (524288, "60927775", "f8599bc84c38573ebbe8685822c58b6a38b50462"),
    "cd_q2.rom": (524288, "770f4c47", "fec8ef00a6669d4d5e37787ecc7b58ee46709326"),
    "cd_q3.rom": (524288, "2f273ffc", "f0de462f6c4d251911258e0ebd886152c14d1586"),
    "cd_q4.rom": (524288, "2c67821d", "6e2528d0b22508300a6a142a796dd3bf53a66946"),
}

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_UNPACKED = 64 * 1024 * 1024
MAX_MEMBERS = 128
MAX_MEMBER = 2 * 1024 * 1024


def validate_file(path, *, output=False):
    path = Path(path)
    if not gate.outside_repo(path):
        raise ValueError("ROM archive path must stay outside public repository")
    if path.is_symlink():
        raise ValueError("symlinks forbidden")
    if output:
        if path.name != "dino.zip" or not path.parent.is_dir():
            raise ValueError("private output must be an existing directory/dino.zip")
        if path.parent.is_symlink():
            raise ValueError("symlink parent forbidden")
        if path.exists():
            raise FileExistsError("will not replace an existing private archive")
    elif (not path.is_file() or not stat.S_ISREG(path.stat().st_mode) or
          not 1 <= path.stat().st_size <= MAX_ARCHIVE):
        raise ValueError("missing or oversized source archive")
    return path


def match_private_roms(source, expected=REQUIRED):
    """Validate *all* expected game content before any output file is created."""
    source = validate_file(source)
    if not expected or len(expected) > MAX_MEMBERS:
        raise ValueError("invalid expected private ROM manifest")
    payloads = {}
    with zipfile.ZipFile(source, "r") as archive:
        members = archive.infolist()
        if not 1 <= len(members) <= MAX_MEMBERS:
            raise ValueError("ZIP member count outside bound")
        if sum(m.file_size for m in members) > MAX_UNPACKED:
            raise ValueError("ZIP decompressed size outside bound")
        names = set()
        for item in members:
            if (item.filename in names or "/" in item.filename or
                "\\" in item.filename or item.is_dir() or item.flag_bits & 1 or
                not item.filename.isascii() or
                not 0 <= item.file_size <= MAX_MEMBER):
                raise ValueError("invalid or ambiguous ZIP entry")
            names.add(item.filename)
        for target, spec in expected.items():
            size, crc, sha1 = spec
            if (not target.isascii() or "/" in target or "\\" in target or
                not 1 <= size <= MAX_MEMBER):
                raise ValueError("invalid historical manifest entry")
            candidates = [
                m for m in members if m.file_size == size and
                f"{m.CRC:08x}" == crc
            ]
            if len(candidates) != 1:
                raise ValueError("historical ROM missing or ambiguous by CRC/size")
            body = archive.read(candidates[0])
            if len(body) != size or hashlib.sha1(body).hexdigest() != sha1:
                raise ValueError("historical ROM SHA-1 mismatch")
            payloads[target] = body
    return payloads


def build(source, destination, *, expected=REQUIRED):
    destination = validate_file(destination, output=True)
    if source is not None and Path(source).resolve() == destination.resolve():
        raise ValueError("private input/output paths must differ")
    verified = match_private_roms(source, expected=expected)
    fd = os.open(str(destination), os.O_WRONLY | os.O_EXCL | os.O_CREAT, 0o600)
    try:
        with os.fdopen(fd, "wb") as output:
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as new:
                for name, content in verified.items():
                    entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                    entry.compress_type = zipfile.ZIP_DEFLATED
                    entry.external_attr = (0o600 << 16)
                    new.writestr(entry, content, compress_type=zipfile.ZIP_DEFLATED,
                                 compresslevel=9)
        # Reopen and validate output bytes before declaring completion.
        match_private_roms(destination, expected=expected)
        return {
            "schema": "dino-private-historical-rom-alias-282-v1",
            "status": "HISTORICAL_0106_ROM_BYTES_MATCH_PRIVATE_ALIAS_READY",
            "expected_roms": len(expected),
            "verified_roms": len(verified),
            "source_bytes_preserved_for_matched_roms": True,
            "historical_mame0106_manifest_matched": expected is REQUIRED,
            "wolfmame_0106_executable_tested": False,
            "original_gameplay_replayed": False,
            "private_ROM_bytes_exported_to_GitHub": False,
        }
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = build(args.source, args.out)
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError, KeyError):
        print("BLOCKED_PRIVATE_HISTORICAL_ROM_ALIAS")
        return 2
    print(report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
