#!/usr/bin/env python3
"""Stage322: verify/extract PUBLIC pinned NeXium Linux release, never game ROM.

Requires exact historical SHA256 and size from previous successful NeXium
CI runs; rejects any replacement of the mutable 'nightly' GitHub release.
Uses Python tarfile safe 'data' filter, not unchecked shell tar extraction.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile

try:
    from . import nexium_private_pinned_optical_launch_318 as pinned
except ImportError:
    import nexium_private_pinned_optical_launch_318 as pinned

SCHEMA = "dino-stage322-public-pinned-nexium-mesa-provisioning-v1"
PASS = "STAGE322_PUBLIC_NEXIUM_PIN_AND_SAFE_EXTRACT_CONFIRMED"
BLOCKED = "BLOCKED_STAGE322_PUBLIC_NEXIUM_RELEASE_CHANGED_OR_INVALID"


def verify_and_extract(archive, install_dir, *, size=None, digest=None):
    archive=Path(archive)
    install_dir=Path(install_dir)
    expected_size=pinned.NEXIUM_BYTES if size is None else size
    expected_digest=pinned.NEXIUM_SHA256 if digest is None else digest
    if (archive.is_symlink() or not archive.is_file() or
            install_dir.exists() or install_dir.is_symlink() or
            type(expected_size) is not int or expected_size<1024 or
            type(expected_digest) is not str or len(expected_digest)!=64 or
            archive.stat().st_size!=expected_size):
        raise ValueError("not exact pinned archive")
    checksum=hashlib.sha256()
    with archive.open("rb") as source:
        for chunk in iter(lambda:source.read(1024*1024),b""):
            checksum.update(chunk)
    if checksum.hexdigest()!=expected_digest:
        raise ValueError("pinned public release changed")
    if not hasattr(tarfile,"data_filter"):
        raise ValueError("safe tar filter unavailable")
    # No directory is created until size/SHA256 were verified.
    install_dir.mkdir(mode=0o700)
    with tarfile.open(archive,"r:gz") as source:
        pinned._safe_members(source)
        source.extractall(install_dir,filter="data")
    matches=[]
    for name in ("nexium-gui","nexium"):
        for candidate in install_dir.rglob(name):
            if candidate.is_file() and not candidate.is_symlink() and all(
                    not p.is_symlink() for p in candidate.parents):
                matches.append(candidate)
    if len(matches)!=1:
        raise ValueError("zero or multiple executable candidates")
    executable=matches[0]
    executable.chmod(executable.stat().st_mode|0o100)
    if not os.access(executable,os.X_OK):
        raise ValueError("public NeXium binary not executable")
    return {
        "schema":SCHEMA,
        "status":PASS,
        "release_archive_sha256_verified":True,
        "release_archive_bytes_verified":True,
        "source_archive_safely_extracted":True,
        "nexium_executable_found":True,
        "mesa_vulkan_driver_installed_on_host":False,
        "original_game_rom_or_graphics_used":False,
        "physical_nintendo_switch_display_verified":False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    parser.add_argument("--install-dir",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        result=verify_and_extract(args.archive,args.install_dir)
        code=0
    except Exception:
        result={
            "schema":SCHEMA,"status":BLOCKED,
            "release_archive_sha256_verified":False,
            "nexium_executable_found":False,
            "original_game_rom_or_graphics_used":False,
        }
        code=2
    args.out.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                        encoding="utf-8")
    print(result["status"])
    return code


if __name__=="__main__":
    raise SystemExit(main())
