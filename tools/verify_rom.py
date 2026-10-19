#!/usr/bin/env python3
"""Local World 930201 ROM ZIP catalog check, including CPS-1 PAL/PLD files.

Matching ZIP metadata does NOT independently authenticate game provenance or
replace the full local MAME 0.289 -verifyroms audit. Never publish ROM bytes.
"""
import argparse
import sys
import zipfile

EXPECTED = {
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
 'cde_21a.6f': (524288, 0x66d23de2),
 'cde_22a.7f': (524288, 0x9278aa12),
 'cde_23a.8f': (524288, 0x8f4e585e),
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
def verify(path):
    failed = False
    with zipfile.ZipFile(path) as archive:
        for name, (size, crc) in EXPECTED.items():
            try: info = archive.getinfo(name)
            except KeyError:
                print("MISSING", name)
                failed = True
                continue
            good = info.file_size == size and info.CRC == crc
            print("OK" if good else "FAIL", name, f"size={info.file_size} crc={info.CRC:08x}")
            failed |= not good
    print("ROM ZIP catalog metadata:", "MISMATCH" if failed else "MATCH_ONLY_NOT_MAME_VERIFIED")
    return int(failed)
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("rom_zip")
    args = parser.parse_args()
    try: sys.exit(verify(args.rom_zip))
    except (OSError, zipfile.BadZipFile) as e: parser.exit(2, str(e) + "\n")
