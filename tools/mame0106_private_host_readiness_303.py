#!/usr/bin/env python3
"""Private execution-readiness audit for historical MAME 0.106 PE32.

Only reports capabilities. It does not launch a game, import original
ROM contents, publish paths or claim original dino gameplay.
"""
import argparse
import json
import os
import shutil
import stat
from pathlib import Path

SCHEMA = "dino-stage303-private-historical-mame-host-readiness-v1"
BLOCKED = "BLOCKED_NO_HISTORICAL_MAME_WINDOWS_EXECUTOR"
READY_WIN = "NATIVE_WINDOWS_MAME_EXECUTOR_CANDIDATE_UNTESTED"
READY_WINE = "WINE_MAME_EXECUTOR_CANDIDATE_UNTESTED"


def pe32_i386(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size < 512:
        raise ValueError("not an ordinary PE32 file")
    with p.open("rb") as f:
        hdr = f.read(64)
        if len(hdr) != 64 or hdr[:2] != b"MZ":
            raise ValueError("missing MZ signature")
        offset = int.from_bytes(hdr[60:64], "little")
        if not 64 <= offset <= 1024 * 1024:
            raise ValueError("invalid PE header offset")
        f.seek(offset)
        pe = f.read(26)
    if (len(pe) != 26 or pe[:4] != b"PE\x00\x00"
            or pe[4:6] != b"\x4c\x01"
            or pe[24:26] != b"\x0b\x01"):
        raise ValueError("not i386 PE32")
    return True


def readiness(mame, *, wine=None, windows=False):
    """Conservative summary; no subprocess or original game file touched."""
    report = {
        "schema": SCHEMA, "status": BLOCKED,
        "mame_pe32_i386_confirmed": False,
        "native_windows_host": bool(windows),
        "wine_binary_present": False,
        "wine_32bit_runtime_verified": False,
        "mame_executed": False,
        "dino_rom_loader_executed": False,
        "dino_gameplay_verified": False,
        "original_inp_wlf_replayed": False,
        "physical_nintendo_switch_tested": False,
        "private_paths_hashes_or_media_exported": False,
    }
    try:
        pe32_i386(mame)
        report["mame_pe32_i386_confirmed"] = True
        if windows:
            report["status"] = READY_WIN
        elif wine:
            candidate = Path(wine)
            if (candidate.is_symlink() or not candidate.is_file()
                    or not (candidate.stat().st_mode & 0o111)):
                return report
            report["wine_binary_present"] = True
            report["status"] = READY_WINE
    except (OSError, ValueError):
        return report
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mame", required=True, type=Path)
    parser.add_argument("--wine", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = readiness(args.mame, wine=args.wine, windows=(os.name == "nt"))
    except (OSError, ValueError):
        result = {"schema": SCHEMA, "status": BLOCKED}
    output = args.out
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise ValueError("expected fresh private report path")
    try:
        from . import wolfmame0106_private_binary_gate as gate
    except ImportError:
        import wolfmame0106_private_binary_gate as gate
    if not gate.outside_repo(output):
        raise ValueError("cannot write report into source repository")
    gate.write_private_receipt(output, result)
    print(result["status"])
    return 0 if result["status"] in (READY_WIN, READY_WINE) else 2


if __name__ == "__main__":
    raise SystemExit(main())
