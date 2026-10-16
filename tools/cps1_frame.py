#!/usr/bin/env python3
"""Partial MAME-referenced CPS-1 frame replay for locally captured VIDEO RAM.

Implements CD63B tile codes, 64x64 tilemaps, normal sprite lists,
blocked sprites, color groups, palette and hardware visible area.
Includes CPS-B priority pens and Scroll2 raster rowscroll from coherent snapshots.
Limitations: stars, flipscreen, accurate raster interrupts, sprite latency and
mid-frame changes are NOT emulated. No ROM bundled.
"""
import argparse
import json
from pathlib import Path
import sys
import zipfile

try:
    from tools.cps1_raster import scroll2_x_for_line, pen_blocks_sprite
    from tools.cps1_gfx import assemble_gfx
    from tools.cps1_tiles import decode_tile, tile_count, _png_rgba
    from tools.cps1_video import (TOTAL_COLORS, build_palette, color_group_base,
                                   gfxrom_bank_mapper, sprite_block_tiles)
except ModuleNotFoundError:
    from cps1_raster import scroll2_x_for_line, pen_blocks_sprite
    from cps1_gfx import assemble_gfx
    from cps1_tiles import decode_tile, tile_count, _png_rgba
    from cps1_video import (TOTAL_COLORS, build_palette, color_group_base,
                            gfxrom_bank_mapper, sprite_block_tiles)

VIEWPORT = (64, 16, 384, 224)
TILE_SIZE = {'scroll1': 8, 'scroll2': 16, 'scroll3': 32}
LAYER_CODES = ('sprites', 'scroll1', 'scroll2', 'scroll3')


def tile_ram_index(layer, col, row):
    """MAME CPS-1 tilemap0/1/2_scan: 64 columns x 64 rows."""
    if layer not in TILE_SIZE:
        raise ValueError('Unknown scroll layer')
    if not 0 <= col < 64 or not 0 <= row < 64:
        raise ValueError('Scroll map position must be in 0..63')
    if layer == 'scroll1':
        return (row & 0x1f) + ((col & 0x3f) << 5) + ((row & 0x20) << 6)
    if layer == 'scroll2':
        return (row & 0x0f) + ((col & 0x3f) << 4) + ((row & 0x30) << 6)
    return (row & 7) + ((col & 0x3f) << 3) + ((row & 0x38) << 6)


def decode_layer_control(value):
    """Bottom-to-top CPS-B bitfield order (bits 6,8,10,12)."""
    if not isinstance(value, int) or not 0 <= value <= 0xffff:
        raise ValueError('layer_control must be 16-bit')
    return tuple(LAYER_CODES[(value >> shift) & 3] for shift in (6, 8, 10, 12))


def scan_sprite_words(words):
    """Parse buffered OBJ RAM; stop before marker attribute with high byte 0xff.

    CPS-1 games latch OBJ RAM one frame late. Caller must provide ALREADY
    BUFFERED (not current unlatched) sprite RAM for accurate temporal state.
    """
    if len(words) % 4:
        raise ValueError('Sprite RAM must contain groups of four 16-bit words')
    sprites = []
    for i in range(0, len(words), 4):
        x, y, code, attr = words[i:i+4]
        if any(not isinstance(w, int) or not 0 <= w <= 65535 for w in (x,y,code,attr)):
            raise ValueError('Sprite RAM contains invalid 16-bit word')
        if attr & 0xff00 == 0xff00:
            break
        sprites.append((x & 0x1ff, y & 0x1ff, code, attr))
    return sprites


def _validate_layer(layer):
    if not isinstance(layer, dict) or not isinstance(layer.get('words'), list) or len(layer['words']) != 8192:
        raise ValueError('Each scroll layer requires exactly 8192 16-bit words')
    if any(type(w) is not int or not 0 <= w <= 65535 for w in layer['words']):
        raise ValueError('Scroll RAM words must be unsigned 16-bit integers')
    for key in ('scrollx','scrolly'):
        if type(layer.get(key, 0)) is not int or not -65536 <= layer.get(key,0) <= 65535:
            raise ValueError('Scroll values must be signed integers')


def _decode_cached(cache, region, layer, code, tile_index=0):
    mapped = gfxrom_bank_mapper(layer, code)
    if mapped < 0:
        return None
    layout = ('8x8-right' if tile_index & 0x20 else '8x8-left') if layer == 'scroll1' else ('16x16' if layer in ('scroll2','sprites') else '32x32')
    if mapped >= tile_count(region, layout):
        return None
    key = (layout, mapped)
    if key not in cache:
        cache[key] = decode_tile(region, layout, mapped)
    return cache[key]


def render_frame(region, palette, snapshot, viewport=VIEWPORT):
    """Compose supported background tilemaps + buffered OBJ sprites into RGBA.

    snapshot schema: {"layer_control": word, "scroll1|2|3":
    {"words": 8192 entries, "scrollx": int, "scrolly": int, "enabled": bool},
    "buffered_obj_words": [x,y,code,attr,...]}.
    Missing layers are transparent. Supports QS2 priority pen masks and
    Scroll2 rowscroll when registers and RAM are supplied. Still partial.
    """
    if len(palette) != TOTAL_COLORS or any(len(rgb) != 3 or any(not isinstance(c,int) or not 0 <= c <= 255 for c in rgb) for rgb in palette):
        raise ValueError('Need 3072 RGB colors in 0..255')
    if len(viewport) != 4 or any(type(q) is not int for q in viewport):
        raise ValueError('Viewport must be four integers')
    vx, vy, width, height = viewport
    if not 1 <= width <= 512 or not 1 <= height <= 256 or not 0 <= vx <= 511 or not 0 <= vy <= 255:
        raise ValueError('Invalid viewport')
    if not isinstance(snapshot, dict):
        raise ValueError('Snapshot must be an object')
    layers = {}
    for lname in TILE_SIZE:
        if lname in snapshot:
            _validate_layer(snapshot[lname])
            layers[lname] = snapshot[lname]
    sprites = scan_sprite_words(snapshot.get('buffered_obj_words', []))
    priority_registers = snapshot.get('priority_masks', [0, 0, 0, 0])
    # Validate masks once; do not silently ignore malformed register dumps.
    pen_blocks_sprite(0, 0, priority_registers)
    video_control = snapshot.get('video_control', 0)
    if type(video_control) is not int or not 0 <= video_control <= 0xffff:
        raise ValueError('video_control must be an unsigned 16-bit value')
    use_rowscroll = bool(video_control & 1)
    rowscroll = snapshot.get('rowscroll', None)
    rowscroll_offset = snapshot.get('rowscroll_offset', 0)
    if use_rowscroll and 'scroll2' in layers:
        if (not isinstance(rowscroll, list) or len(rowscroll) != 1024 or
                any(type(w) is not int or not 0 <= w <= 0xffff for w in rowscroll)):
            raise ValueError('Enabled Scroll2 rowscroll needs 1024 RAM words')
    order = decode_layer_control(snapshot['layer_control'])
    back = bytes(palette[0xbff]) + b'\xff'
    rgba = bytearray(back * (width * height))
    cache = {}
    sprite_occlusion = bytearray(width * height)

    def set_pixel(screen_x, screen_y, rgb):
        if vx <= screen_x < vx+width and vy <= screen_y < vy+height:
            offset = ((screen_y-vy) * width + screen_x-vx) * 4
            rgba[offset:offset+4] = bytes(rgb) + b'\xff'

    for order_index, lname in enumerate(order):
        # MAME draws the *previous* tilemap's high-priority pens into a
        # priority bitmap immediately before sprites are rendered.
        high_before_sprites = (order_index < 3 and order[order_index + 1] == 'sprites')
        if high_before_sprites:
            sprite_occlusion = bytearray(width * height)
        if lname == 'sprites':
            # Listed OBJ entries are traversed from first to last by MAME,
            # with later entries covering earlier ones where alpha permits.
            for x,y,code,attr in sprites:
                mapped = gfxrom_bank_mapper('sprites', code)
                if mapped == -1:
                    continue
                base = color_group_base('sprites', attr & 0x1f)
                for part in sprite_block_tiles(mapped, attr):
                    pixels = _decode_cached(cache, region, 'sprites', part.code)
                    if pixels is None:
                        continue
                    sx, sy = ((x+part.dx)&0x1ff), ((y+part.dy)&0x1ff)
                    for py in range(16):
                        target_y = sy+py
                        if not vy <= target_y < vy+height:
                            continue
                        pixel_y = 15-py if part.flip_y else py
                        for px in range(16):
                            target_x = sx+px
                            if not vx <= target_x < vx+width:
                                continue
                            pixel_x = 15-px if part.flip_x else px
                            pen = pixels[pixel_y*16+pixel_x]
                            if pen != 15 and not sprite_occlusion[(target_y-vy)*width+(target_x-vx)]:
                                set_pixel(target_x,target_y,palette[base+pen])
        elif lname in layers and layers[lname].get('enabled', True):
            layer = layers[lname]
            words = layer['words']
            tile_size = TILE_SIZE[lname]
            wrap = tile_size * 64
            for py in range(height):
                line_scrollx = layer.get('scrollx', 0)
                if lname == 'scroll2' and use_rowscroll:
                    line_scrollx = scroll2_x_for_line(line_scrollx, (vy+py) & 255,
                                                     rowscroll, rowscroll_offset)
                world_y = (vy+py + layer.get('scrolly',0)) % wrap
                row, local_y = divmod(world_y, tile_size)
                for px in range(width):
                    world_x = (vx+px + line_scrollx) % wrap
                    col, local_x = divmod(world_x, tile_size)
                    idx = tile_ram_index(lname,col,row)
                    code,attr = words[2*idx:2*idx+2]
                    if lname == 'scroll3':
                        code &= 0x3fff
                    pixels = _decode_cached(cache,region,lname,code,idx)
                    if pixels is None:
                        continue
                    if attr & 0x20: local_x = tile_size-1-local_x
                    if attr & 0x40: pixel_y = tile_size-1-local_y
                    else: pixel_y=local_y
                    pen = pixels[pixel_y*tile_size+local_x]
                    if pen == 15:
                        continue
                    base = color_group_base(lname,attr & 0x1f)
                    set_pixel(vx+px,vy+py,palette[base+pen])
                    if high_before_sprites:
                        group = (attr & 0x0180) >> 7
                        sprite_occlusion[py * width + px] = int(pen_blocks_sprite(pen,group,priority_registers))
    return bytes(rgba)


def load_snapshot(path):
    """Safely load the explicit JSON snapshot schema (no ROM data)."""
    snap = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(snap,dict):
        raise ValueError('Snapshot root must be JSON object')
    if 'palette_rgb' in snap:
        palette = snap['palette_rgb']
    elif 'palette_source' in snap:
        source = snap['palette_source']
        palette = build_palette(source['words'], source['control'])
    else:
        raise ValueError('Need palette_rgb (copied RAM) or palette_source (source words + control)')
    return snap,palette


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom_zip',type=Path)
    parser.add_argument('snapshot_json',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        snapshot,palette = load_snapshot(args.snapshot_json)
        with zipfile.ZipFile(args.rom_zip) as archive:
            region=assemble_gfx(archive.read)
        rgba=render_frame(region,palette,snapshot)
        png=_png_rgba(VIEWPORT[2],VIEWPORT[3],rgba,'PARTIAL CPS1 frame with priority/rowscroll support; local-only')
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_bytes(png)
        print(f'Wrote {args.out} ({VIEWPORT[2]}x{VIEWPORT[3]}, {len(png)} bytes)')
    except (OSError,ValueError,KeyError,IndexError,zipfile.BadZipFile,TypeError) as exc:
        print(f'Error: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
