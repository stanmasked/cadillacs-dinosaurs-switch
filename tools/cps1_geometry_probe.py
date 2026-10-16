#!/usr/bin/env python3
"""CPS-1 dino screen-coordinate to tile-map address diagnostic.

Independent geometry calculation from MAME cps1_v.cpp scan functions:
viewport x=64..447, y=16..239, map dimensions 64x64, tile sizes 8/16/32.
No graphics ROM, palette contents or rendered image required.
"""
import argparse
import json
from pathlib import Path
import sys

MAPS = {'scroll1': (8, 5), 'scroll2': (16, 4), 'scroll3': (32, 3)}
VIEWPORT = (64, 16, 384, 224)


def probe_layer(snapshot, layer, screen_x, screen_y):
    if layer not in MAPS:
        raise ValueError('Unknown CPS-1 scroll layer')
    if (type(screen_x) is not int or type(screen_y) is not int or
            not 0 <= screen_x < 512 or not 0 <= screen_y < 256):
        raise ValueError('CPS-1 pixel address outside 512x256 raster')
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get(layer), dict):
        raise ValueError('Snapshot is missing requested scroll layer')
    ram = snapshot[layer]
    words = ram.get('words')
    if not isinstance(words, list) or len(words) != 8192:
        raise ValueError('Scroll RAM must contain exactly 8192 16-bit words')
    size, col_shift = MAPS[layer]
    scroll_x, scroll_y = ram.get('scrollx', 0), ram.get('scrolly', 0)
    for name, v in (('scrollx', scroll_x), ('scrolly', scroll_y)):
        if type(v) is not int or not -65536 <= v <= 65535:
            raise ValueError(f'{name} is not a CPS-1 register value')
    delta = 0
    if layer == 'scroll2' and snapshot.get('video_control', 0) & 1:
        offset = snapshot.get('rowscroll_offset', 0)
        rows = snapshot.get('rowscroll')
        if (type(offset) is not int or not isinstance(rows, list) or
                len(rows) != 1024):
            raise ValueError('Enabled rowscroll requires 1024 values and integer offset')
        delta = rows[(screen_y + offset) & 1023]
        if type(delta) is not int or not 0 <= delta <= 65535:
            raise ValueError('Invalid rowscroll word')
    wx = (screen_x + scroll_x + delta) & (64 * size - 1)
    wy = (screen_y + scroll_y) & (64 * size - 1)
    col, local_x = divmod(wx, size)
    row, local_y = divmod(wy, size)
    if size == 8:
        index = (row & 31) + (col << 5) + ((row & 32) << 6)
    elif size == 16:
        index = (row & 15) + (col << 4) + ((row & 48) << 6)
    else:
        index = (row & 7) + (col << 3) + ((row & 56) << 6)
    code, attr = words[index*2:index*2+2]
    if any(type(n) is not int or not 0 <= n <= 65535 for n in (code,attr)):
        raise ValueError('Invalid tile code or attribute word')
    if layer == 'scroll3':
        code &= 0x3fff
    sampled_x = size - 1 - local_x if attr & 0x20 else local_x
    sampled_y = size - 1 - local_y if attr & 0x40 else local_y
    return {
        'layer': layer, 'screen_xy': [screen_x, screen_y],
        'inside_visible_area': 64 <= screen_x <= 447 and 16 <= screen_y <= 239,
        'enabled': bool(ram.get('enabled', True)),
        'tile_size': size, 'effective_scroll_x': scroll_x + delta,
        'effective_scroll_y': scroll_y,
        'world_xy': [wx,wy], 'tile_col_row': [col,row],
        'tile_index': index, 'ram_word_index': index*2,
        'tile_code': code, 'attribute': attr,
        'sampled_pixel_xy': [sampled_x,sampled_y],
        'scroll1_half': ('right' if index & 32 else 'left') if size == 8 else None,
        'palette_group_base': {'scroll1':512,'scroll2':1024,'scroll3':1536}[layer]
                              + (attr & 31)*16,
        'priority_group': (attr >> 7) & 3,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('snapshot', type=Path, help='Private local scene snapshot JSON')
    p.add_argument('--layer', choices=tuple(MAPS), required=True)
    p.add_argument('--x', type=int, required=True, help='Hardware raster X (64..447 visible)')
    p.add_argument('--y', type=int, required=True, help='Hardware raster Y (16..239 visible)')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    try:
        data = json.loads(args.snapshot.read_text(encoding='utf-8'))
        report = probe_layer(data,args.layer,args.x,args.y)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x',encoding='utf-8') as f:
            json.dump(report,f,indent=2)
            f.write('\n')
        print(f"{args.layer} ({args.x},{args.y}) -> tile {report['tile_index']}, "
              f"code {report['tile_code']}, sampled pixel {report['sampled_pixel_xy']}")
        return 0
    except (ValueError,OSError,TypeError,KeyError) as exc:
        print(f'Geometry probe rejected: {exc}',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
