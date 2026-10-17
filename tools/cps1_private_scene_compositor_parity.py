#!/usr/bin/env python3
"""Local-only CPS-1 native/Python compositor parity with personally held ROM.

Graphics are real original CPS-1 data; layer control, palette, scroll RAM,
priority masks and buffered OBJ are deliberately SYNTHETIC. Never describe
the generated composites as actual MAME gameplay or original game frames.
No ROM, graphical output, palette, raw pixels, SHA or private path is saved.
"""
import argparse
import ctypes
import json
from pathlib import Path
import subprocess
import sys
import tempfile

try:
    from tools.cps1_private_native_tile_parity import read_private_gfx
    from tools.cps1_scene_export import pack_scene
    from tools.cps1_frame import render_frame
    from tools.cps1_video import TOTAL_COLORS
except ModuleNotFoundError:
    from cps1_private_native_tile_parity import read_private_gfx
    from cps1_scene_export import pack_scene
    from cps1_frame import render_frame
    from cps1_video import TOTAL_COLORS

WIDTH, HEIGHT = 384, 224
PIXELS = WIDTH * HEIGHT
FRAME_BYTES = PIXELS * 4
GFX_BYTES = 0x400000
ORDER_CODES = {'sprites': 0, 'scroll1': 1, 'scroll2': 2, 'scroll3': 3}
GROUP_UNMASKED_CASES = {
    'priority_group0_unmasked': 0,
    'priority_group1_unmasked': 1,
    'priority_group2_unmasked': 2,
    'priority_group3_unmasked': 3,
}


def _order(*layers):
    if len(layers) != 4 or set(layers) != set(ORDER_CODES):
        raise ValueError('Synthetic compositor order must include four distinct layers')
    return sum(ORDER_CODES[name] << (6 + 2 * i)
               for i, name in enumerate(layers))


def _words(layer, variation):
    """Reproducible ROM-free tilemap codes, color groups, flips, priorities."""
    tiles = bytearray()  # No actual game data in this synthetic metadata.
    del tiles
    limits = {'scroll1': 96, 'scroll2': 64, 'scroll3': 32}
    mod = limits[layer]
    result = [0] * 8192
    for i in range(4096):
        code = (i * 7 + 3 * variation + 5) % mod
        attr = ((i // 37 + variation) % 32)
        attr |= ((i // 13 + variation) % 4) << 7
        if i % 29 == 0:
            attr |= 0x20
        if i % 31 == 0:
            attr |= 0x40
        result[i * 2] = code
        result[i * 2 + 1] = attr
    return result


def synthetic_scene(name):
    """Artificial test state, never sampled or reconstructed from gameplay."""
    options = {
        'priority_sprite': (('scroll3', 'scroll1', 'scroll2', 'sprites'), 0),
        'unmasked_sprite': (('scroll3', 'scroll1', 'scroll2', 'sprites'), 0),
        'rowscroll_flip': (('scroll1', 'scroll2', 'sprites', 'scroll3'), 2),
        'sprite_under_layers': (('sprites', 'scroll1', 'scroll2', 'scroll3'), 3),
        'priority_transparent_bit': (('scroll3', 'scroll1', 'scroll2', 'sprites'), 0),
        'priority_group_selective': (('scroll3', 'scroll1', 'scroll2', 'sprites'), 0),
        'transparent_palette_unused': (('scroll3', 'scroll1', 'scroll2', 'sprites'), 0),
        'palette_channels_shift': (('scroll3', 'scroll1', 'scroll2', 'sprites'), 0),
        'scroll1_priority': (('scroll3', 'scroll2', 'scroll1', 'sprites'), 0),
        'scroll1_unmasked': (('scroll3', 'scroll2', 'scroll1', 'sprites'), 0),
        **{name: (('scroll3', 'scroll1', 'scroll2', 'sprites'), 0)
           for name in GROUP_UNMASKED_CASES},
    }
    if name not in options:
        raise ValueError('Unsupported synthetic compositor parity case')
    order, variant = options[name]
    palette = [[(i * 13 + 17) & 255, (i * 7 + 29) & 255,
                (i * 3 + 41) & 255] for i in range(TOTAL_COLORS)]
    palette[0xbff] = [1, 2, 3]
    # All paired stimuli below preserve VRAM, layer controls and OBJ.
    # Pen 15 is transparent regardless of palette RGB or mask bit 15.
    if name in ('priority_sprite', 'scroll1_priority'):
        regs = [0x7fff] * 4
    elif name == 'priority_transparent_bit':
        regs = [0xffff] * 4
    elif name == 'priority_group_selective':
        regs = [0x5555, 0xaaaa, 0x0f0f, 0xf0f0]
    elif name in GROUP_UNMASKED_CASES:
        regs = [0x7fff] * 4
        regs[GROUP_UNMASKED_CASES[name]] = 0
    elif name in ('unmasked_sprite', 'transparent_palette_unused',
                  'palette_channels_shift', 'scroll1_unmasked'):
        regs = [0] * 4
    else:
        regs = [0x00a6, 0x0f0f, 0x1111, 0x8000]

    if name == 'transparent_palette_unused':
        # Every palette entry addressed by a transparent tile/sprite pen,
        # excluding the explicit backdrop at 0xbff, must be unobservable.
        for i in range(15, TOTAL_COLORS, 16):
            if i != 0xbff:
                palette[i] = [253, 1, 199]
    elif name == 'palette_channels_shift':
        # Remap opaque palette entries with nontrivial independent RGB
        # changes; keep the backdrop and transparent-pen colors intact.
        for i in range(TOTAL_COLORS):
            if i != 0xbff and i % 16 != 15:
                r, g, b = palette[i]
                palette[i] = [(r + 71) & 255, g ^ 0x80, (b + 23) & 255]
    # Visible sprites include two overlapping blocks, a flipped sprite,
    # and 16x16 cells crossing all four viewport edges.
    objs = [
        64, 16, 5, 0x1160,
        80, 32, 13, 0x0203,
        61, 14, 3, 0,
        437, 222, 27, 0x0020,
        0, 0, 0, 0xff00,
    ]
    scene = {
        'layer_control': _order(*order),
        'video_control': 1 if variant == 2 else 0,
        'palette_rgb': palette,
        'priority_masks': regs,
        'rowscroll_offset': 1019 if variant == 2 else 0,
        'buffered_obj_words': objs,
    }
    for i, layer in enumerate(('scroll1', 'scroll2', 'scroll3')):
        scene[layer] = {
            'words': _words(layer, variant),
            'enabled': True,
            'scrollx': (65533 + i * 7 + variant * 13) & 0xffff,
            'scrolly': (65531 + i * 5 + variant * 3) & 0xffff,
        }
    if variant == 2:
        scene['rowscroll'] = [(i * 19 + (i // 17) * 11) & 0xffff
                              for i in range(1024)]
    return scene


CASES = (
    'priority_sprite', 'unmasked_sprite',
    'priority_transparent_bit', 'priority_group_selective',
    'transparent_palette_unused', 'palette_channels_shift',
    'scroll1_priority', 'scroll1_unmasked',
    *GROUP_UNMASKED_CASES,
    'rowscroll_flip', 'sprite_under_layers',
)

# Differential assertions are independent of native/Python pixel agreement.
# Invariance means pen 15 is never opaque and never blocks a sprite.
DIFFERENTIAL_EXPECTATIONS = {
    'priority_mask_changed_rgba_pixels': True,
    'priority_pen15_changed_rgba_pixels': False,
    'priority_groups_changed_rgba_pixels': True,
    'transparent_palette_changed_rgba_pixels': False,
    'palette_remap_changed_rgba_pixels': True,
    'scroll1_priority_changed_rgba_pixels': True,
    **{'priority_group{}_individual_changed_rgba_pixels'.format(i): True
       for i in range(4)},
}


def _different_pixels(left, right):
    if len(left) != FRAME_BYTES or len(right) != FRAME_BYTES:
        raise ValueError('Synthetic pair has inconsistent RGBA dimensions')
    return sum(left[i:i+4] != right[i:i+4]
               for i in range(0, FRAME_BYTES, 4))


def _status(code):
    return {
        'schema': 'PRIVATE_DINO_NATIVE_SCENE_COMPOSITOR_PARITY_V1',
        'status': code,
        'diagnostic_only': True,
        'background_tile_graphics_from_original_rom': True,
        'palette_scroll_obj_and_priority_are_synthetic': True,
        'original_game_frame_captured': False,
        'real_gameplay_observed': False,
        'mame_vblank_synchronization_verified': False,
        'sprite_latch_timing_verified': False,
        'nintendo_switch_framebuffer_parity_verified': False,
        'source_rom_or_derived_pixel_bytes_written_to_disk': False,
        'private_paths_or_game_digests_in_report': False,
    }


def _compile_scene(libpath):
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
         '-fPIC', '-shared', '-I' + str(root / 'source'),
         str(root / 'source' / 'cps1_scene.c'),
         str(root / 'source' / 'cps1_tile.c'),
         '-o', str(libpath)],
        check=True, capture_output=True, timeout=60)


def compare_private_native_scene_compositor(archive):
    """Run exact Switch compositor on locally owned ROM in RAM only."""
    gfx = read_private_gfx(archive)
    if len(gfx) != GFX_BYTES:
        raise ValueError('Private original graphics region size invalid')
    with tempfile.TemporaryDirectory(prefix='cps1-rom-free-scene-library-') as tmp:
        library_path = Path(tmp) / 'native_scene.so'
        _compile_scene(library_path)
        dll = ctypes.CDLL(str(library_path))
        decode = dll.cps1_scene_decode
        decode.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]
        decode.restype = ctypes.c_bool
        render = dll.cps1_scene_render
        render.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_size_t,
        ]
        render.restype = ctypes.c_bool
        region = (ctypes.c_uint8 * GFX_BYTES).from_buffer_copy(gfx)
        scene_mem = ctypes.create_string_buffer(70000)
        frame_mem = ctypes.create_string_buffer(FRAME_BYTES)
        total_mismatches = 0
        # Hold only three temporary in-RAM reference frames for pairwise
        # tests; neither C frames nor original graphics are saved to disk.
        baselines = {}
        effects = {}
        paired_cases = {
            **{name: ('priority_sprite',
                      'priority_group{}_individual_changed_rgba_pixels'.format(index))
               for name, index in GROUP_UNMASKED_CASES.items()},
            'unmasked_sprite': ('priority_sprite',
                                'priority_mask_changed_rgba_pixels'),
            'priority_transparent_bit': ('priority_sprite',
                                         'priority_pen15_changed_rgba_pixels'),
            'priority_group_selective': ('priority_sprite',
                                         'priority_groups_changed_rgba_pixels'),
            'transparent_palette_unused': ('unmasked_sprite',
                                            'transparent_palette_changed_rgba_pixels'),
            'palette_channels_shift': ('unmasked_sprite',
                                       'palette_remap_changed_rgba_pixels'),
            'scroll1_unmasked': ('scroll1_priority',
                                 'scroll1_priority_changed_rgba_pixels'),
        }
        cases = []
        for name in CASES:
            snap = synthetic_scene(name)
            serialized = pack_scene(snap)
            if not decode(serialized, len(serialized), scene_mem):
                raise ValueError('Native synthetic CPS-1 scene input refused')
            if not render(region, GFX_BYTES, scene_mem, frame_mem, FRAME_BYTES):
                raise ValueError('Native synthetic CPS-1 frame render failed')
            actual = frame_mem.raw
            if name in ('priority_sprite', 'unmasked_sprite',
                        'scroll1_priority'):
                baselines[name] = actual
            if name in paired_cases:
                baseline, metric = paired_cases[name]
                effects[metric] = _different_pixels(baselines[baseline], actual)
            expected = render_frame(
                gfx, [tuple(rgb) for rgb in snap['palette_rgb']], snap)
            if len(actual) != FRAME_BYTES or len(expected) != FRAME_BYTES:
                raise ValueError('CPS-1 synthetic scene dimensions invalid')
            mismatches = _different_pixels(actual, expected)
            total_mismatches += mismatches
            cases.append({
                'scenario': name,
                'compared_rgba_pixels': PIXELS,
                'mismatching_rgba_pixels': mismatches,
            })
    covered = (set(effects) == set(DIFFERENTIAL_EXPECTATIONS) and
               all((effects[key] > 0) == must_change
                   for key, must_change in DIFFERENTIAL_EXPECTATIONS.items()))
    result = _status(
        'PRIVATE_NATIVE_SCENE_PARITY_MISMATCH' if total_mismatches else
        'PRIVATE_NATIVE_SCENE_DIFFERENTIAL_COVERAGE_REFUSED' if not covered else
        'PRIVATE_NATIVE_SCENE_PARITY_PASSED')
    result.update({
        'scene_size': [WIDTH, HEIGHT],
        'synthetic_cases': len(CASES),
        'pixels_compared': len(CASES) * PIXELS,
        'mismatching_pixels_total': total_mismatches,
        **effects,
        'differential_coverage_verified': covered,
        'scenario_results': cases,
    })
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('private_owned_dino_zip', type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare_private_native_scene_compositor(
            args.private_owned_dino_zip)
    except Exception:
        # Suppress all private archive paths, exception texts, raw graphics,
        # compiler messages, captured tile pixels and device identifiers.
        result = _status('PRIVATE_NATIVE_SCENE_INPUT_OR_BUILD_REFUSED')
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'PRIVATE_NATIVE_SCENE_PARITY_PASSED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
