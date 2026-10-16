#!/usr/bin/env python3
"""Deterministic ROM-free multilayer CPS-1 Switch timeline demo (NOT game data).

Exports CPS1SEQ1 through existing scene/timeline packers. Original game
graphics are loaded only at playback from the user's private local ROM.
"""
import argparse
import json
from pathlib import Path
import sys


def tile_index(layer, col, row):
    if not isinstance(col, int) or not isinstance(row, int) or not (0 <= col < 64 and 0 <= row < 64):
        raise ValueError('Tile grid position outside 64x64')
    if layer == 'scroll1':
        return (row & 31) + (col << 5) + ((row & 32) << 6)
    if layer == 'scroll2':
        return (row & 15) + (col << 4) + ((row & 48) << 6)
    if layer == 'scroll3':
        return (row & 7) + (col << 3) + ((row & 56) << 6)
    raise ValueError('Unsupported tilemap')


def make_tilemap(layer):
    """Fill a 64x64 tilemap with index-preserving synthetic patterns."""
    words = [0] * 8192
    base = {'scroll1': 0x0100, 'scroll2': 0x0200, 'scroll3': 0x0180}[layer]
    code_mod = {'scroll1': 128, 'scroll2': 96, 'scroll3': 32}[layer]
    for row in range(64):
        for col in range(64):
            index = tile_index(layer, col, row)
            code = base + ((col * 3 + row * 11 + ((col ^ row) & 7)) % code_mod)
            color = ((col // 6) + (row // 8)) & 31
            attr = color | (0x20 if (col // 9) % 2 else 0)
            words[index * 2:index * 2 + 2] = (code, attr)
    return words


def make_palette():
    palette = [[0, 0, 0] for _ in range(3072)]
    palette[0xbff] = [15, 21, 31]
    # This is a diagnostic palette, not the game's original palette.
    for page in range(4):
        for group in range(32):
            for pen in range(15):
                p = page * 512 + group * 16 + pen
                base = (13 + pen * 14 + group * 5) & 255
                palette[p] = [
                    (base + (70 if page == 0 else 13 * page)) & 255,
                    (27 + pen * 9 + group * 4 + 18 * page) & 255,
                    (35 + pen * 8 + page * 35) & 255,
                ]
    return palette


def make_sprites(frame):
    """Three moving synthetic objects and a CPS-1 end-of-list marker."""
    first_x = 78 + frame * 3
    second_y = 155 - ((frame * 2) % 54)
    third_x = 378 - frame * 2
    flip = 0x20 if (frame // 12) & 1 else 0
    return [
        first_x & 511, 119, 0x0130, 0x1101 | flip,
        245, second_y & 511, 0x0240, 0x0005,
        third_x & 511, 180, 0x0190, 0x0109 | flip,
        0, 0, 0, 0xff00,
    ]


def demo_snapshots(count=36):
    if type(count) is not int or not 1 <= count <= 120:
        raise ValueError('Demo frame count must be 1..120')
    backgrounds = {name: make_tilemap(name) for name in ('scroll1', 'scroll2', 'scroll3')}
    palette = make_palette()
    scenes = []
    for frame in range(count):
        rows = [0] * 1024
        for physical_y in range(256):
            rows[(physical_y + 9) & 1023] = (physical_y // 12 + frame * 2) & 31
        scene = {
            'game': 'dino', 'demo_type': 'SYNTHETIC_MULTI_LAYER_NOT_GAMEPLAY',
            'layer_control': (3 << 6) | (2 << 8) | (1 << 10) | (0 << 12),
            'video_control': 0x0d,
            'palette_rgb': palette,
            'priority_masks': [0, 0, 0, 0],
            'rowscroll_offset': 9, 'rowscroll': rows,
            'scroll1': {'words': backgrounds['scroll1'], 'enabled': True,
                        'scrollx': frame * 4, 'scrolly': (frame // 6) & 0xffff},
            'scroll2': {'words': backgrounds['scroll2'], 'enabled': True,
                        'scrollx': frame * 2, 'scrolly': 0},
            'scroll3': {'words': backgrounds['scroll3'], 'enabled': True,
                        'scrollx': frame // 3, 'scrolly': 0},
            'buffered_obj_words': make_sprites(frame),
        }
        scenes.append(scene)
    return scenes


def report_for(scenes, fps):
    return {
        'format': 'cps1_synthetic_scene_timeline_v1',
        'game': 'dino', 'authentic_gameplay': False,
        'requires_original_rom_graphics_at_playback': True,
        'render_parity_with_MAME_verified': False,
        'frame_count': len(scenes), 'fps': fps,
        'viewport_width': 384, 'viewport_height': 224,
        'layers': ['scroll3', 'scroll2', 'scroll1', 'sprites'],
        'scroll2_rowscroll_enabled': True,
        'synthetic_sprite_entities': 3,
        'first_camera_scrolls': {n: scenes[0][n]['scrollx'] for n in ('scroll1', 'scroll2', 'scroll3')},
        'last_camera_scrolls': {n: scenes[-1][n]['scrollx'] for n in ('scroll1', 'scroll2', 'scroll3')},
        'notes': 'A moving multilayer visual diagnostic, not the original stage layout, AI, music or gameplay.',
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--frames', type=int, default=36)
    ap.add_argument('--fps', type=int, default=12)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--report', type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        if type(args.fps) is not int or not 1 <= args.fps <= 60:
            raise ValueError('FPS outside 1..60')
        try:
            from tools.cps1_scene_export import pack_scene
            from tools.cps1_sequence_export import pack_sequence
        except ModuleNotFoundError:
            from cps1_scene_export import pack_scene
            from cps1_sequence_export import pack_sequence
        scenes = demo_snapshots(args.frames)
        packed = pack_sequence([pack_scene(s) for s in scenes], args.fps)
        if args.out.resolve() == args.report.resolve():
            raise ValueError('Output sequence and report must be different paths')
        if args.out.exists() or args.report.exists():
            raise FileExistsError('Refusing to overwrite scene or report')
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('xb') as f:
            f.write(packed)
        with args.report.open('x', encoding='utf-8') as f:
            json.dump(report_for(scenes, args.fps), f, indent=2)
            f.write('\n')
        print(f'Synthetic multilayer {len(scenes)}-frame sequence: {len(packed)} bytes')
        return 0
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print('Synthetic scene export refused:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
