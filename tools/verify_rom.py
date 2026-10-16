#!/usr/bin/env python3
"""Audit the World 930201 parent ROM set without distributing ROMs."""
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
    print("ROM audit:", "FAIL" if failed else "PASS")
    return int(failed)
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("rom_zip")
    args = parser.parse_args()
    try: sys.exit(verify(args.rom_zip))
    except (OSError, zipfile.BadZipFile) as e: parser.exit(2, str(e) + "\n")
