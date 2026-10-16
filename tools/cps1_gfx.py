#!/usr/bin/env python3
"""Assemble dino CPS-1 graphics ROM region locally; no assets are bundled or uploaded."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROM_SIZE = 0x80000
BANK_SIZE = 0x200000
LANES = (
    ('cd-1m.3a', 0), ('cd-3m.5a', 2),
    ('cd-2m.4a', 4), ('cd-4m.6a', 6),
    ('cd-5m.7a', 0), ('cd-7m.9a', 2),
    ('cd-6m.8a', 4), ('cd-8m.10a', 6),
)

def assemble_gfx(reader):
    result = bytearray(BANK_SIZE * 2)
    for i, (name, lane) in enumerate(LANES):
        data = reader(name)
        if len(data) != ROM_SIZE:
            raise ValueError(f'{name}: expected {ROM_SIZE} bytes, got {len(data)}')
        base = (i // 4) * BANK_SIZE + lane
        result[base:base + 8 * (ROM_SIZE // 2):8] = data[0::2]
        result[base + 1:base + 1 + 8 * (ROM_SIZE // 2):8] = data[1::2]
    return bytes(result)

def metadata(region):
    return {'region_bytes': len(region), 'sha256': hashlib.sha256(region).hexdigest(),
            'first_32_bytes_hex': region[:32].hex()}

def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('rom_zip', type=Path)
    parser.add_argument('--out-local', type=Path,
                        help='Write assembled 4 MiB graphics region to local disk only; '
                             'never commit or redistribute game contents')
    args = parser.parse_args(argv)
    with zipfile.ZipFile(args.rom_zip) as z:
        region = assemble_gfx(z.read)
    print(json.dumps(metadata(region), indent=2))
    if args.out_local is not None:
        # Exclusive create avoids unintentional overwriting of personal dumps.
        with args.out_local.open('xb') as out:
            out.write(region)
        print(f'Created local graphics region: {args.out_local}')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
