#!/usr/bin/env python3
"""Offline ROM readiness audit for MAME CPS-1 dino (World 930201).

No ROM extraction, redistribution, emulation, or network access. The output
contains only public expected metadata, diagnostics and counts.
"""
import argparse
import json
from pathlib import Path
import sys
import zipfile

# MAME dino parent-game ROM CRC32s; main CPU, graphics, QSound CPU/samples.
# Reference: MAME src/mame/capcom/cps1.cpp ROM_START(dino). Compare the
# installed emulator's -listxml output if MAME uses a different romset.
CORE = {
    'cde_23a.8f': (524288, 0x8f4e585e),
    'cde_22a.7f': (524288, 0x9278aa12),
    'cde_21a.6f': (524288, 0x66d23de2),
    'cd-1m.3a': (524288, 0x8da4f917),
    'cd-2m.4a': (524288, 0x09c8fc2d),
    'cd-3m.5a': (524288, 0x6c40f603),
    'cd-4m.6a': (524288, 0x637ff38f),
    'cd-5m.7a': (524288, 0x470befee),
    'cd-6m.8a': (524288, 0xe7599ac4),
    'cd-7m.9a': (524288, 0x22bfb7a3),
    'cd-8m.10a': (524288, 0x211b4b15),
    'cd-q1.1k': (524288, 0x60927775),
    'cd-q2.2k': (524288, 0x770f4c47),
    'cd-q3.3k': (524288, 0x2f273ffc),
    'cd-q4.4k': (524288, 0x2c67821d),
    'cd_q.5k': (131072, 0x605fdb0b),
}
# Programmable-logic archival dumps, separate from emulated CPU/GFX/sound.
ARCHIVAL_PLD = {
    'bprg1.11d': (279, 0x31793da7),
    'buf1': (279, 0xeb122de7),
    'cd63b.1a': (279, 0xef72e902),
    'd10f1.10f': (279, 0x6619c494),
    'd7l1.7l': (279, 0x27b7410d),
    'd8l1.8l': (279, 0x539fc7da),
    'd9k2.9k': (279, 0xcd85a156),
    'ioa1': (279, 0x59c7ee3b),
    'iob1.12d': (279, 0x3abc0700),
    'ioc1.ic1': (260, 0xa399772d),
    'prg2': (279, 0x4386879a),
    'rom1': (279, 0x41dc73b9),
}
# MAME src/devices/sound/qsoundhle.cpp, required separately for device HLE.
# Another known ioc1.ic1 archive revision appears in older MAME romsets.
KNOWN_ARCHIVAL_ALTERNATIVES = {'ioc1.ic1': [(279, 0x0d182081)]}
QSOUND_HLE = {'dl-1425.bin': (8192, 0xd6cf5ef5)}
MAX_ZIP_UNCOMPRESSED = 32 * 1024 * 1024
MAX_ZIP_MEMBERS = 100


def audit_zip(path, expected, *, known_alternatives=None):
    """Read and CRC-check all ZIP members without extracting or returning bytes."""
    members = {}
    total = 0
    with zipfile.ZipFile(Path(path)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_ZIP_MEMBERS:
            raise ValueError('Excessive ZIP entry count')
        for info in entries:
            name = info.filename
            if (not name or '/' in name or '\\' in name or info.is_dir() or
                    name in members or info.file_size < 0 or
                    info.file_size > MAX_ZIP_UNCOMPRESSED):
                raise ValueError('Unsafe/duplicate/non-flat ZIP member')
            total += info.file_size
            if total > MAX_ZIP_UNCOMPRESSED:
                raise ValueError('ZIP uncompressed size exceeds safety limit')
            # Decompression catches wrong payload CRCs as well as short streams.
            with archive.open(info) as stream:
                while stream.read(131072):
                    pass
            members[name] = (info.file_size, info.CRC)
    matches, mismatches, absent = [], [], []
    known_variants = []
    known_alternatives = known_alternatives or {}
    for name, (size, crc) in sorted(expected.items()):
        actual = members.get(name)
        if actual is None:
            absent.append(name)
        elif actual == (size, crc):
            matches.append(name)
        elif actual in known_alternatives.get(name, ()):
            known_variants.append({
                'name': name, 'bytes': actual[0],
                'crc32': f'{actual[1]:08x}',
                'note': 'Known alternate archival revision; compare your installed MAME listxml',
            })
        else:
            mismatches.append({
                'name': name,
                'expected_bytes': size, 'actual_bytes': actual[0],
                'expected_crc32': f'{crc:08x}',
                'actual_crc32': f'{actual[1]:08x}',
            })
    return {
        'expected_count': len(expected),
        'matching_count': len(matches),
        'known_variant_count': len(known_variants),
        'known_variant_matches': known_variants,
        'missing_names': absent,
        'mismatches': mismatches,
        'archive_member_count': len(members),
        'matching_names': matches,
    }


def audit_game(path):
    """Distinguish required game ROMs from archived PLD differences."""
    core = audit_zip(path, CORE)
    archival = audit_zip(path, ARCHIVAL_PLD,
                         known_alternatives=KNOWN_ARCHIVAL_ALTERNATIVES)
    return {
        'core_game_roms': core,
        'archival_logic_dumps': archival,
        'core_complete': core['matching_count'] == len(CORE),
        'all_archival_plds_match': archival['matching_count'] == len(ARCHIVAL_PLD),
        'all_archival_plds_known': (archival['matching_count'] + archival['known_variant_count']
                                    == len(ARCHIVAL_PLD)),
    }


def check_device(path):
    if path is None or not Path(path).is_file():
        return {
            'status': 'not_supplied', 'valid': False,
            'note': 'QSound HLE dependency was not verified in accessible files',
        }
    report = audit_zip(path, QSOUND_HLE)
    complete = report['matching_count'] == len(QSOUND_HLE)
    return {
        'status': 'validated' if complete else 'invalid',
        'valid': complete, 'roms': report,
    }


def audit(game_zip, device_zip=None):
    game = audit_game(game_zip)
    device = check_device(device_zip)
    return {
        'tool': 'cps1_dino_offline_rom_readiness',
        'schema_version': 1, 'game': 'dino',
        'variant': 'World 930201 / CPS-B-21 QS2 / CD63B',
        'game_roms': game,
        'qsound_hle': device,
        'main_cpu_gfx_sound_roms_verified': game['core_complete'],
        'modern_mame_rom_prerequisites_verified':
            game['core_complete'] and device['valid'],
        'emulator_installed_or_launched': False,
        'game_boot_verified': False,
        'capture_achieved': False,
        'limitations': (
            'ROM metadata and separate device checks cannot establish emulator '
            'compatibility, live playback or actual CPS-1 frame capture.'
        ),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('game_zip', type=Path)
    p.add_argument('--qsound-hle', type=Path,
                   help='Optional user-supplied local qsound_hle.zip')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        result = audit(args.game_zip, args.qsound_hle)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x', encoding='utf8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
            f.write('\n')
        print('Core game ROMs:',
              result['game_roms']['core_game_roms']['matching_count'],
              'of', len(CORE))
        print('Archival PLDs matching chosen reference:',
              result['game_roms']['archival_logic_dumps']['matching_count'],
              'of', len(ARCHIVAL_PLD))
        print('Known alternate PLDs:',
              result['game_roms']['archival_logic_dumps']['known_variant_count'])
        print('QSound HLE:', result['qsound_hle']['status'])
        print('Actual MAME boot: NOT VERIFIED')
        return 0 if result['modern_mame_rom_prerequisites_verified'] else 1
    except (OSError, ValueError, zipfile.BadZipFile,
            RuntimeError, NotImplementedError) as exc:
        print('ROM audit rejected:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
