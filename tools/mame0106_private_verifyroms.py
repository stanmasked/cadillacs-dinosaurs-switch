"""Fail-closed private MAME 0.106 ROM audit and optional genuine native verification.

On non-Windows systems, reports offline content integrity ONLY. Does not
misrepresent checksum equivalence as MAME execution. No private bytes/logs are
printed, recorded in public artifacts, or submitted to GitHub Actions.
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
import subprocess
import sys
import tempfile
import zipfile

from tools.mame0106_private_rom_name_adapter import (
    HEX_SHA256, expected_roms, require_source, AdapterError,
    MAX_MEMBERS, MAX_MEMBER_BYTES, MAX_UNPACKED_BYTES,
)
from tools.mame0106_romfree_native_windows_probe import EXE_SHA

PINNED_ROM_SHA256 = '66fb8ad8e1f419b40bdfdaa250e86c865939178e7e732d49327854cb6ccdc8dd'
PINNED_XML_SHA256 = 'b6a89430b5e982ad533ea96faa53084506b4ca62f0f63ea6cdedd74324dda4c8'
MAX_MAME_OUTPUT_BYTES = 128 * 1024
POSITIVE_ROMSET = re.compile(rb'(?im)^romset dino is good\s*$')
POSITIVE_SUMMARY = re.compile(rb'(?im)^1 romsets found, 1 were OK\.\s*$')


class PrivateProbeError(Exception):
    """Safe fixed identifier, never contains ROM paths or tool output."""


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def guard_public_runner() -> None:
    if os.getenv('GITHUB_ACTIONS', '').lower() == 'true':
        raise PrivateProbeError('public_runner_forbidden')


def offline_audit(rom_zip: Path, driver_xml: Path, *, rom_sha: str = PINNED_ROM_SHA256,
                  xml_sha: str = PINNED_XML_SHA256) -> dict[str, int | str]:
    """Independently check original expected names + data, without MAME execution."""
    guard_public_runner()
    try:
        rom_bytes = require_source(rom_zip, rom_sha)
        require_source(driver_xml, xml_sha)
        expected = expected_roms(driver_xml, 'dino')
    except (AdapterError, OSError, ValueError) as exc:
        raise PrivateProbeError('untrusted_input_or_driver') from exc
    if len(expected) == 0 or len(expected) > MAX_MEMBERS:
        raise PrivateProbeError('unexpected_driver_inventory')
    try:
        with zipfile.ZipFile(rom_zip, 'r') as z:
            entries = z.infolist()
            wanted = {name: (size, crc, sha1) for name, size, crc, sha1 in expected}
            if len(entries) != len(expected) or {e.filename for e in entries} != set(wanted):
                raise PrivateProbeError('rom_inventory_mismatch')
            total = 0
            for entry in entries:
                if (entry.is_dir() or (entry.flag_bits & 1) or
                        stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK or
                        entry.file_size <= 0 or entry.file_size > MAX_MEMBER_BYTES):
                    raise PrivateProbeError('unsafe_rom_member')
                size, crc, sha1 = wanted[entry.filename]
                if entry.file_size != size:
                    raise PrivateProbeError('rom_size_mismatch')
                total += size
                if total > MAX_UNPACKED_BYTES:
                    raise PrivateProbeError('rom_unpacked_limit')
                with z.open(entry) as f:
                    payload = f.read(MAX_MEMBER_BYTES + 1)
                if len(payload) != size or len(payload) > MAX_MEMBER_BYTES:
                    raise PrivateProbeError('rom_data_size_mismatch')
                checksum = f'{zipfile.crc32(payload) & 0xffffffff:08x}'
                if checksum != crc or hashlib.sha1(payload).hexdigest() != sha1:
                    raise PrivateProbeError('rom_data_digest_mismatch')
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise PrivateProbeError('corrupt_rom_zip') from exc
    return {'offline_audit': 'pass', 'expected_roms': len(expected),
            'verified_roms': len(entries), 'rom_archive_bytes': rom_bytes,
            'verified_rom_payload_bytes': total}


def verify_executable(path: Path, expected_sha: str = EXE_SHA) -> None:
    if (not path.is_file() or path.is_symlink() or not HEX_SHA256.fullmatch(expected_sha)
            or digest(path) != expected_sha.lower()):
        raise PrivateProbeError('executable_digest_mismatch')
    with path.open('rb') as f:
        header = f.read(4096)
    if len(header) < 0x40 or header[:2] != b'MZ':
        raise PrivateProbeError('executable_not_pe')
    offset = struct.unpack_from('<I', header, 0x3c)[0]
    if offset + 6 > len(header) or header[offset:offset + 6] != b'PE\0\0\x4c\x01':
        raise PrivateProbeError('wrong_pe_architecture')


def classify_native_output(stdout: bytes, stderr: bytes, returncode: int) -> str:
    """Require both success markers from historical source src/windows/fronthlp.c."""
    if returncode != 0:
        return 'native_exit_nonzero'
    if not POSITIVE_ROMSET.search(stdout) or not POSITIVE_SUMMARY.search(stdout):
        return 'native_positive_evidence_missing'
    if (b'is bad' in stdout.lower() or b'not found' in stdout.lower()
            or b'not supported' in stdout.lower()):
        return 'native_negative_evidence_present'
    return 'native_verified'


def native_verify(rom_zip: Path, exe: Path, *, timeout: int = 90,
                  scratch_parent: Path | None = None,
                  expected_exe_sha: str = EXE_SHA) -> str:
    """Windows-only MAME execution with all private data in throwaway scratch."""
    guard_public_runner()
    if os.name != 'nt':
        return 'not_run_no_native_windows_runtime'
    verify_executable(exe, expected_sha=expected_exe_sha)
    if timeout < 1 or timeout > 180:
        raise PrivateProbeError('invalid_timeout')
    # Scratch must never be a synced Drive folder or the public source tree.
    parent = None if scratch_parent is None else scratch_parent.resolve(strict=True)
    if parent is not None and not parent.is_dir():
        raise PrivateProbeError('invalid_scratch')
    with tempfile.TemporaryDirectory(prefix='mame0106-private-verify-', dir=parent) as tmp:
        scratch = Path(tmp)
        roms = scratch / 'roms'
        roms.mkdir()
        private_copy = roms / 'dino.zip'
        shutil.copyfile(rom_zip, private_copy)
        if digest(private_copy) != digest(rom_zip):
            raise PrivateProbeError('private_copy_changed')
        outfile, errfile = scratch / 'stdout.bin', scratch / 'stderr.bin'
        try:
            with outfile.open('wb') as stdout, errfile.open('wb') as stderr:
                proc = subprocess.run(
                    (str(exe), 'dino', '-verifyroms', '-rompath', str(roms), '-noreadconfig'),
                    cwd=str(scratch), stdout=stdout, stderr=stderr,
                    stdin=subprocess.DEVNULL, timeout=timeout, check=False,
                )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise PrivateProbeError('native_start_or_timeout') from exc
        if outfile.stat().st_size > MAX_MAME_OUTPUT_BYTES or errfile.stat().st_size > MAX_MAME_OUTPUT_BYTES:
            raise PrivateProbeError('native_output_limit')
        status = classify_native_output(outfile.read_bytes(), errfile.read_bytes(), proc.returncode)
        if status != 'native_verified':
            raise PrivateProbeError(status)
        return status


def run(args: argparse.Namespace) -> dict[str, str | int]:
    summary: dict[str, str | int] = {
        'schema': 'mame0106-private-verifyroms-v1',
        'private_data_used': 'yes', 'github_actions_allowed': 'no',
        'rom_execution': 'not_run', 'recording_playback': 'not_run',
    }
    summary.update(offline_audit(args.rom_zip, args.driver_xml,
                                 rom_sha=args.rom_sha256, xml_sha=args.xml_sha256))
    if args.mame_exe is None:
        summary['rom_execution'] = 'not_run_no_executable_selected'
    else:
        summary['rom_execution'] = native_verify(args.rom_zip, args.mame_exe,
                                                  timeout=args.timeout,
                                                  scratch_parent=args.scratch_parent)
    summary['result'] = 'pass' if summary['rom_execution'] == 'native_verified' else 'offline_only'
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom-zip', type=Path, required=True)
    parser.add_argument('--driver-xml', type=Path, required=True)
    parser.add_argument('--rom-sha256', default=PINNED_ROM_SHA256)
    parser.add_argument('--xml-sha256', default=PINNED_XML_SHA256)
    parser.add_argument('--mame-exe', type=Path)
    parser.add_argument('--scratch-parent', type=Path)
    parser.add_argument('--timeout', type=int, default=90)
    args = parser.parse_args(argv)
    try:
        outcome = run(args)
        for key, value in outcome.items():
            print(f'{key}={value}')
        return 0 if outcome['result'] == 'pass' else 2
    except (PrivateProbeError, OSError) as exc:
        print('schema=mame0106-private-verifyroms-v1')
        print('result=fail')
        print('failure_class=' + type(exc).__name__)
        return 1


if __name__ == '__main__':
    sys.exit(main())