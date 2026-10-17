#!/usr/bin/env python3
"""Explicit local ROM-payload CRC audit: no assets, hashes, or paths exported.

Unlike the Stage 104-105 ZIP-header-only check, this opt-in operation reads
game and QSound ZIP members on the owner's machine. Streaming is bounded and
all CRC32 values stay in process memory. A catalog match is NOT MAME's
-verifyroms verdict, independently authenticated original ROM provenance,
or observed game execution. Run genuine MAME -verifyroms separately.
"""
import argparse
import json
import os
from pathlib import Path
import stat
import sys
import zipfile
import zlib

try:
    from tools.verify_rom import EXPECTED
    from tools.mame_private_rom_blocker_triage import DEVICE_MEMBER, DEVICE_HEADER
except ModuleNotFoundError:
    from verify_rom import EXPECTED
    from mame_private_rom_blocker_triage import DEVICE_MEMBER, DEVICE_HEADER

MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ZIP_ENTRIES = 128
MAX_TOTAL_DECODED_BYTES = 32 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024
READ_CHUNK_SIZE = 65536


def _safe_metadata(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink,
            st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def _open_stable_private_zip(path):
    """Read one regular single-link file through a no-follow descriptor."""
    previous = path.lstat()
    if (not stat.S_ISREG(previous.st_mode) or previous.st_nlink != 1
            or not 0 < previous.st_size <= MAX_ARCHIVE_BYTES):
        raise ValueError('Private ROM archive metadata invalid')
    flags = os.O_RDONLY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    if hasattr(os, 'O_CLOEXEC'):
        flags |= os.O_CLOEXEC
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        if _safe_metadata(opened) != _safe_metadata(previous):
            raise ValueError('Private ROM archive changed during open')
        return os.fdopen(fd, 'rb'), _safe_metadata(opened)
    except BaseException:
        os.close(fd)
        raise


def _archive_pair_metadata(game, device):
    """Bind game and device ZIP identities across the entire local audit.

    File-specific descriptor checks alone cannot catch replacement of the
    first archive while the second one is still being inspected.
    """
    observations = []
    for path in (game, device):
        try:
            info = path.lstat()
        except FileNotFoundError:
            observations.append(None)
            continue
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 < info.st_size <= MAX_ARCHIVE_BYTES):
            raise ValueError('Private ROM archive pair entry unsafe')
        observations.append(_safe_metadata(info))
    return tuple(observations)


def _catalog_payload_check(path, catalog):
    """Return (verified, missing, mismatch, read_count) without leaking bytes."""
    stream, original = _open_stable_private_zip(path)
    verified = missing = mismatch = read_count = 0
    decoded_total = 0
    with stream:
        with zipfile.ZipFile(stream, 'r') as archive:
            infos = archive.infolist()
            if not 0 < len(infos) <= MAX_ZIP_ENTRIES:
                raise ValueError('Private ZIP directory count invalid')
            entries = {}
            for info in infos:
                name = info.filename
                if (not name or name in ('.', '..') or
                        '/' in name or '\\' in name or info.is_dir() or
                        info.file_size <= 0 or info.file_size > MAX_ARCHIVE_BYTES or
                        name in entries):
                    raise ValueError('Private ZIP member directory unsafe')
                entries[name] = info
            for name, (expected_size, expected_crc) in catalog.items():
                if not 0 < expected_size <= MAX_MEMBER_BYTES:
                    raise ValueError('Private expected ROM member size invalid')
                info = entries.get(name)
                if info is None:
                    missing += 1
                    continue
                if info.file_size != expected_size or info.CRC != expected_crc:
                    mismatch += 1
                    continue
                if decoded_total + expected_size > MAX_TOTAL_DECODED_BYTES:
                    raise ValueError('Private decoded ROM budget exceeded')
                decoded_total += expected_size
                digest = 0
                remaining = expected_size
                with archive.open(info, 'r') as payload:
                    while remaining:
                        block = payload.read(min(READ_CHUNK_SIZE, remaining))
                        if not block:
                            raise ValueError('Private ZIP member truncated')
                        remaining -= len(block)
                        digest = zlib.crc32(block, digest)
                    if payload.read(1):
                        raise ValueError('Private ZIP member exceeded expected size')
                read_count += 1
                if digest != expected_crc:
                    mismatch += 1
                else:
                    verified += 1
        if _safe_metadata(os.fstat(stream.fileno())) != original:
            raise ValueError('Private ZIP archive modified during scan')
    if _safe_metadata(path.lstat()) != original:
        raise ValueError('Private ZIP archive replaced during scan')
    return verified, missing, mismatch, read_count


def _base(status):
    return {
        'schema': 'PRIVATE_DINO_ROM_PAYLOAD_CRC_AUDIT_V1',
        'status': status,
        'diagnostic_only': True,
        'explicit_private_payload_read_authorized': False,
        'private_payload_bytes_read_locally': False,
        'private_payload_crc_matches_pinned_catalog': False,
        'mame_verifyroms_executed': False,
        'original_game_authenticity_verified': False,
        'gameplay_executed': False,
        'frame_sync_verified': False,
        'switch_gameplay_verified': False,
        'pixel_parity_eligible': False,
        'original_rom_bytes_or_digests_in_report': False,
        'private_paths_in_report': False,
    }


def audit_private_dino_rom_payloads(rom_directory, *, allow_private_reads=False):
    """Require explicit permission before reading owned ROM members locally."""
    if allow_private_reads is not True:
        raise ValueError('Explicit private payload read permission is required')
    root = Path(rom_directory)
    metadata = root.lstat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise ValueError('Private ROM root is not a real directory')
    game = root / 'dino.zip'
    device = root / 'qsound_hle.zip'
    pair_before = _archive_pair_metadata(game, device)
    if pair_before[0] is None:
        raise ValueError('Private game archive missing')
    game_verified, game_missing, game_wrong, game_read = _catalog_payload_check(
        game, EXPECTED)
    if pair_before[1] is not None:
        device_verified, device_missing, device_wrong, device_read = (
            _catalog_payload_check(device, {DEVICE_MEMBER: DEVICE_HEADER}))
    else:
        device_verified, device_missing, device_wrong, device_read = 0, 1, 0, 0
    if _archive_pair_metadata(game, device) != pair_before:
        raise ValueError('Private paired ROM archives changed during audit')
    all_verified = (game_verified == len(EXPECTED) and
                    device_verified == 1 and
                    game_missing == game_wrong == device_missing == device_wrong == 0)
    result = _base('PRIVATE_DINO_ROM_PAYLOAD_CRC_CATALOG_MATCH_ONLY'
                   if all_verified else 'PRIVATE_DINO_ROM_PAYLOAD_CRC_CATALOG_MISMATCH')
    result.update({
        'explicit_private_payload_read_authorized': True,
        'private_payload_bytes_read_locally': (game_read + device_read) > 0,
        'private_payload_crc_matches_pinned_catalog': all_verified,
        'expected_member_count': len(EXPECTED) + 1,
        'payload_catalog_verified_count': game_verified + device_verified,
        'missing_member_count': game_missing + device_missing,
        'mismatching_member_count': game_wrong + device_wrong,
        'pld_and_qsound_provenance_unconfirmed': True,
        'next_local_action_code': (
            'RUN_GENUINE_LOCAL_MAME_VERIFYROMS'
            if all_verified else 'REVIEW_PRIVATE_ROM_CONTENT_AND_DEPENDENCIES'),
    })
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom-dir', type=Path, required=True)
    parser.add_argument('--verify-private-payloads', action='store_true',
                        help='Explicitly read and CRC-check private owned ROM data locally')
    args = parser.parse_args(argv)
    try:
        out = audit_private_dino_rom_payloads(
            args.rom_dir, allow_private_reads=args.verify_private_payloads)
    except Exception:
        out = _base('PRIVATE_DINO_ROM_PAYLOAD_CRC_AUDIT_REFUSED')
        print(json.dumps(out, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
