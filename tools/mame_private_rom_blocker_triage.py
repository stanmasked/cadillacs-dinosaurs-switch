#!/usr/bin/env python3
"""Local-only, metadata-level diagnostic for known MAME 0.289 dino blockers.

Read only ZIP central-directory metadata for the privately held World 930201
set and the separately installed qsound_hle device archive. No game member
payloads are opened, extracted, hashed or copied. Directory metadata CRCs
are *claims by the ZIP*, NOT independently verified payload CRCs. This is
neither MAME -verifyroms nor confirmation of any authentic game execution.

The CLI outputs fixed-vocabulary summary and aggregate counts only, never
private paths, filenames, ROM hashes, exception text, or raw game data.
"""
import argparse
import json
from pathlib import Path
import stat
import sys
import zipfile

try:
    from tools.verify_rom import EXPECTED
except ModuleNotFoundError:
    from verify_rom import EXPECTED

MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 128
DEVICE_MEMBER = 'dl-1425.bin'
# Verified against pinned MAME 0.289 src/devices/sound/qsoundhle.cpp:
# ROM_LOAD16_WORD 0x2000 + ROM_IGNORE 0x4000, full source length 0x6000.
# This public catalog CRC is ZIP *metadata* only, not a payload audit.
DEVICE_HEADER = (0x6000, 0xd6cf5ef5)
PLD_MEMBER = 'ioc1.ic1'


def _ordinary_archive(path):
    """Refuse unsafe local archive entries before opening ZIP metadata."""
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
            not 0 < info.st_size <= MAX_ARCHIVE_BYTES):
        raise ValueError('Private ROM archive entry type or size refused')
    return True


def _central_directory(path):
    """Read bounded ZIP member headers but NEVER individual ROM member data."""
    with zipfile.ZipFile(path, 'r') as archive:
        infos = archive.infolist()
    if not 0 < len(infos) <= MAX_ARCHIVE_ENTRIES:
        raise ValueError('Private ROM ZIP member count refused')
    by_name = {}
    for item in infos:
        name = item.filename
        if (not name or '/' in name or '\\' in name or name in ('.', '..') or
                item.is_dir() or item.file_size <= 0 or
                item.file_size > MAX_ARCHIVE_BYTES or name in by_name):
            raise ValueError('Private ROM ZIP member metadata refused')
        by_name[name] = (item.file_size, item.CRC)
    return by_name


def _fixed_base(status):
    return {
        'schema': 'PRIVATE_DINO_MAME_ROM_BLOCKER_TRIAGE_V1',
        'status': status,
        'diagnostic_only': True,
        'zip_central_directory_metadata_inspected': False,
        'individual_game_rom_payload_bytes_read': False,
        'rom_payload_crc_independently_verified': False,
        'mame_verifyroms_executed': False,
        'original_game_authenticity_verified': False,
        'gameplay_executed': False,
        'pixel_parity_eligible': False,
        'private_paths_names_and_digests_in_report': False,
    }


def triage_private_dino_rom_blockers(rom_directory):
    """Summarize *known* MAME blockers without exposing private ZIP content."""
    root = Path(rom_directory)
    meta = root.lstat()
    if not stat.S_ISDIR(meta.st_mode):
        raise ValueError('Private ROM directory is not an ordinary directory')

    game_path = root / 'dino.zip'
    device_path = root / 'qsound_hle.zip'
    has_game_zip = _ordinary_archive(game_path)
    has_device_zip = _ordinary_archive(device_path)
    if not has_game_zip:
        raise ValueError('Private dino ZIP entry unavailable')

    game = _central_directory(game_path)
    device = _central_directory(device_path) if has_device_zip else {}
    matching = sum(game.get(name) == expected
                   for name, expected in EXPECTED.items())
    missing = sum(name not in game for name in EXPECTED)
    mismatch = len(EXPECTED) - matching - missing
    pld_match = game.get(PLD_MEMBER) == EXPECTED[PLD_MEMBER]
    other_game_issue = any(game.get(name) != expected
                           for name, expected in EXPECTED.items()
                           if name != PLD_MEMBER)
    device_member_observed = DEVICE_MEMBER in device
    device_header_matches = device.get(DEVICE_MEMBER) == DEVICE_HEADER
    blocked = bool(not pld_match or other_game_issue or
                   not device_header_matches)

    if other_game_issue:
        next_step = 'REVIEW_PRIVATE_GAME_CATALOG_THEN_LOCAL_MAME_VERIFYROMS'
    elif not pld_match and not device_header_matches:
        next_step = 'REVIEW_PRIVATE_PLD_AND_QSOUND_DEPENDENCIES'
    elif not pld_match:
        next_step = 'REVIEW_PRIVATE_PLD_CATALOG_ENTRY'
    elif not device_member_observed:
        next_step = 'CHECK_PRIVATE_QSOUND_DEVICE_ARCHIVE'
    elif not device_header_matches:
        next_step = 'REVIEW_PRIVATE_QSOUND_DEVICE_CATALOG_HEADER'
    else:
        next_step = 'RUN_GENUINE_LOCAL_MAME_VERIFYROMS'

    result = _fixed_base(
        'PRIVATE_KNOWN_MAME_ROM_BLOCKERS_OBSERVED_METADATA_ONLY'
        if blocked else
        'PRIVATE_KNOWN_MAME_ROM_BLOCKERS_NOT_OBSERVED_METADATA_ONLY')
    result.update({
        'zip_central_directory_metadata_inspected': True,
        'game_catalog_expected_entries': len(EXPECTED),
        'game_catalog_matching_headers': matching,
        'game_catalog_missing_entries': missing,
        'game_catalog_mismatching_headers': mismatch,
        'pld_catalog_header_matches': pld_match,
        'other_game_catalog_issues_observed': other_game_issue,
        'separate_qsound_hle_archive_observed': has_device_zip,
        'qsound_hle_device_member_observed': device_member_observed,
        'qsound_hle_device_header_matches': device_header_matches,
        'known_dependency_layout_requires_attention': blocked,
        'next_local_action_code': next_step,
    })
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom-dir', type=Path, required=True,
                        help='Private MAME ROM directory, kept outside GitHub')
    args = parser.parse_args(argv)
    try:
        result = triage_private_dino_rom_blockers(args.rom_dir)
    except Exception:
        # File names, exceptions, archive CRCs and system paths are private.
        result = _fixed_base('PRIVATE_DINO_ROM_BLOCKER_TRIAGE_REFUSED')
        print(json.dumps(result, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
