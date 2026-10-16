#!/usr/bin/env python3
"""Render local CPS-1 indexed ROM tiles using a *runtime palette RAM snapshot*.

The original colors cannot be inferred from static ROM graphics alone.
Use a saved palette source captured from an authorized local game runtime.
No gameplay ROM content or extracted sprites are included in this project.
"""
import argparse
import json
from pathlib import Path
import sys
import zipfile

try:
    from tools.cps1_gfx import assemble_gfx
    from tools.cps1_tiles import LAYOUTS, decode_tile, tile_count, _png_rgba
    from tools.cps1_video import build_palette, color_group_base, gfxrom_bank_mapper
except ModuleNotFoundError:
    from cps1_gfx import assemble_gfx
    from cps1_tiles import LAYOUTS, decode_tile, tile_count, _png_rgba
    from cps1_video import build_palette, color_group_base, gfxrom_bank_mapper

LAYERS = {'sprites': '16x16', 'scroll1': '8x8-left',
          'scroll2': '16x16', 'scroll3': '32x32'}


def parse_snapshot(path):
    """JSON: {"control": "0x3f", "words": [0xf000, ...]}.

    `words` are *CPS-1 gfx RAM source palette words*, not preconverted RGBA.
    """
    obj = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(obj, dict) or 'control' not in obj or 'words' not in obj:
        raise ValueError('Expected JSON object with control and words')
    def integer(x):
        if isinstance(x, bool):
            raise ValueError('Boolean values are invalid palette words')
        if isinstance(x, str):
            return int(x, 0)
        if not isinstance(x, int):
            raise ValueError('Palette words must be integers or integer strings')
        return x
    control = integer(obj['control'])
    if not isinstance(obj['words'], list):
        raise ValueError('words must be a list of unsigned 16-bit values')
    return control, [integer(w) for w in obj['words']]


def render_atlas(region, palette, layer='sprites', first_code=0,
                 count=32, color=0, columns=8, scale=2):
    if layer not in LAYERS:
        raise ValueError('Unknown layer')
    if len(palette) != 3072:
        raise ValueError('Palette must contain 3072 colors')
    if not 1 <= scale <= 8 or count <= 0 or columns <= 0 or first_code < 0:
        raise ValueError('Invalid atlas geometry')
    width, height, _, _ = LAYOUTS[LAYERS[layer]]
    cols = min(columns, count)
    rows = (count + cols - 1) // cols
    w, h = cols * width * scale, rows * height * scale
    rgba = bytearray(w * h * 4)
    pbase = color_group_base(layer, color)
    for i in range(count):
        mapped = gfxrom_bank_mapper(layer, first_code + i)
        if mapped < 0 or mapped >= tile_count(region, LAYERS[layer]):
            continue  # transparent, just like hardware out-of-range tile
        pixels = decode_tile(region, LAYERS[layer], mapped)
        bx, by = (i % cols) * width * scale, (i // cols) * height * scale
        for y in range(height):
            for x in range(width):
                pen = pixels[y * width + x]
                rgb = palette[pbase + pen]
                pixel = bytes(rgb) + bytes((0 if pen == 15 else 255,))
                for sy in range(scale):
                    offset = ((by + y * scale + sy) * w + bx + x * scale) * 4
                    rgba[offset:offset + scale * 4] = pixel * scale
    return _png_rgba(w, h, rgba, 'CPS-1 RAM palette snapshot; pen 15 transparent')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom_zip', type=Path)
    p.add_argument('palette_json', type=Path)
    p.add_argument('--layer', choices=LAYERS, default='sprites')
    p.add_argument('--color', type=int, default=0)
    p.add_argument('--first-code', type=lambda s: int(s, 0), default=0)
    p.add_argument('--count', type=int, default=32)
    p.add_argument('--columns', type=int, default=8)
    p.add_argument('--scale', type=int, default=2)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        control, source_words = parse_snapshot(args.palette_json)
        palette = build_palette(source_words, control)
        with zipfile.ZipFile(args.rom_zip) as archive:
            region = assemble_gfx(archive.read)
        png = render_atlas(region, palette, args.layer, args.first_code,
                           args.count, args.color, args.columns, args.scale)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(png)
        print(f'Palette-based tile atlas: {args.out} ({len(png)} bytes)')
    except (ValueError, OSError, KeyError, zipfile.BadZipFile, IndexError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
