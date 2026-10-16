#!/usr/bin/env python3
"""Decode indexed CPS-1 graphics tiles and generate local-only diagnostic PNGs.

Pixel layouts transcribed from MAME cps1_layout8x8/_2, 16x16 and 32x32:
https://github.com/mamedev/mame/blob/master/src/mame/capcom/cps1.cpp

Palettes in CPS-1 are runtime state, not encoded alongside pixel indices in GFX ROM.
Diagnostic grayscale is deliberately NOT an original game palette.
"""
import argparse
import struct
import sys
import zipfile
import zlib
from pathlib import Path

try:
    from tools.cps1_gfx import assemble_gfx
except ModuleNotFoundError:
    # Also support running directly as a script from the repository root.
    from cps1_gfx import assemble_gfx

# (width, height, bytes per code, 8-pixel half-row offset)
LAYOUTS = {
    '8x8-left': (8, 8, 64, 0),
    '8x8-right': (8, 8, 64, 4),
    '16x16': (16, 16, 128, 0),
    '32x32': (32, 32, 512, 0),
}

def tile_count(region, layout):
    if layout not in LAYOUTS:
        raise ValueError(f'Unsupported layout: {layout}')
    _, _, char_size, _ = LAYOUTS[layout]
    return len(region) // char_size

def decode_tile(region, layout, code):
    """Return raw palette indices 0..15 in row-major order (no palette RAM)."""
    if layout not in LAYOUTS:
        raise ValueError(f'Unsupported layout: {layout}')
    if not isinstance(code, int) or code < 0 or code >= tile_count(region, layout):
        raise IndexError(f'Code {code} out of range for {layout}')
    width, height, char_size, offset = LAYOUTS[layout]
    start = code * char_size
    row_stride = (width // 2) if width > 8 else 8
    out = bytearray(width * height)
    for y in range(height):
        row_base = start + y * row_stride + offset
        for x in range(width):
            group = row_base + (x // 8) * 4
            bit = 7 - (x % 8)
            out[y * width + x] = sum(((region[group + plane] >> bit) & 1) << (3 - plane)
                                     for plane in range(4))
    return bytes(out)

def _png_chunk(chunk_type, data):
    payload = chunk_type + data
    return struct.pack('>I', len(data)) + payload + struct.pack('>I', zlib.crc32(payload))

def _png_rgba(width, height, rgba, comment):
    if len(rgba) != width * height * 4:
        raise ValueError('Invalid RGBA buffer length')
    stride = width * 4
    scanlines = b''.join(b'\x00' + rgba[y * stride:(y + 1) * stride]
                         for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' +
            _png_chunk(b'IHDR', struct.pack('>2I5B', width, height, 8, 6, 0, 0, 0)) +
            _png_chunk(b'tEXt', b'Comment\x00' + comment.encode('latin-1')) +
            _png_chunk(b'IDAT', zlib.compress(scanlines, 9)) +
            _png_chunk(b'IEND', b''))

def diagnostic_atlas(region, layout, start=0, count=64, columns=8, scale=2):
    """Generate RGBA PNG, treating index 15 as transparent checker.

    Output has no genuine CPS-1 palette or sprite composition.
    """
    if count <= 0 or columns <= 0 or not 1 <= scale <= 8:
        raise ValueError('count and columns must be positive; scale must be 1..8')
    if start < 0 or start + count > tile_count(region, layout):
        raise ValueError('Selected range exceeds graphics region')
    tw, th, _, _ = LAYOUTS[layout]
    cols = min(count, columns)
    rows = (count + cols - 1) // cols
    width, height = cols * tw * scale, rows * th * scale
    rgba = bytearray(width * height * 4)
    for i in range(count):
        pix = decode_tile(region, layout, start + i)
        cell_x, cell_y = (i % cols) * tw * scale, (i // cols) * th * scale
        for y in range(th):
            for x in range(tw):
                pen = pix[y * tw + x]
                if pen == 15:
                    v = 50 if ((x // 4 + y // 4) & 1) else 70
                    color = (v, v, v, 255)
                else:
                    v = 20 + pen * 15
                    color = (v, v, v, 255)
                for sy in range(scale):
                    idx = ((cell_y + y * scale + sy) * width + cell_x + x * scale) * 4
                    rgba[idx:idx + 4 * scale] = bytes(color) * scale
    return _png_rgba(width, height, rgba, 'CPS-1 indices only; diagnostic grayscale, not original palette')

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('rom_zip', type=Path)
    ap.add_argument('--layout', choices=LAYOUTS.keys(), default='16x16')
    ap.add_argument('--start', type=int, default=0)
    ap.add_argument('--count', type=int, default=64)
    ap.add_argument('--columns', type=int, default=8)
    ap.add_argument('--scale', type=int, default=2)
    ap.add_argument('--out', type=Path, required=True, help='Local-only PNG destination')
    args = ap.parse_args(argv)
    try:
        with zipfile.ZipFile(args.rom_zip) as archive:
            region = assemble_gfx(archive.read)
        png = diagnostic_atlas(region, args.layout, args.start, args.count,
                               args.columns, args.scale)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(png)
        print(f'Diagnostic atlas saved: {args.out} ({len(png)} bytes)')
    except (OSError, ValueError, IndexError, zipfile.BadZipFile) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
