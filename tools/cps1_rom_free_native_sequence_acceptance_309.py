#!/usr/bin/env python3
"""Stage309: ROM-free native CPS1SEQ1 playback/parity acceptance, NOT gameplay.

Builds only deterministic artificial Stage307+308 fixtures in memory.
Compiles the exact portable C sequence, scene, and tile sources used by the
Switch NRO. Tests native sequence acceptance, frame rendering and independent
Python RGBA agreement, plus controlled visual priority/palette effects.
Does not launch MAME or a Switch, extract original assets, or persist frames.
"""
import ctypes
import json
from pathlib import Path
import subprocess
import tempfile

try:
    from . import cps1_synthetic_scene_sequence_307 as timeline
    from . import cps1_synthetic_gfx_fixture_308 as graphics
    from . import cps1_private_scene_compositor_parity as scenes
    from . import cps1_frame as python_scene
    from . import cps1_sequence_export as sequence
except ImportError:
    import cps1_synthetic_scene_sequence_307 as timeline
    import cps1_synthetic_gfx_fixture_308 as graphics
    import cps1_private_scene_compositor_parity as scenes
    import cps1_frame as python_scene
    import cps1_sequence_export as sequence

PASS = "ROM_FREE_NATIVE_CPS1_SEQUENCE_PARITY_PASSED_NOT_GAMEPLAY"
BLOCKED = "ROM_FREE_NATIVE_CPS1_SEQUENCE_PARITY_REFUSED"
SCHEMA = "dino-stage309-rom-free-native-sequence-acceptance-v1"
RG_BYTES = 384 * 224 * 4
SCENE_MEMORY_BYTES = 70000


class NativeSequence(ctypes.Structure):
    _fields_ = [
        ("blob", ctypes.c_void_p),
        ("frame_count", ctypes.c_uint16),
        ("fps", ctypes.c_uint16),
    ]


class Playback(ctypes.Structure):
    _fields_ = [
        ("index", ctypes.c_uint32),
        ("remainder", ctypes.c_uint32),
        ("speed_num", ctypes.c_uint),
        ("paused", ctypes.c_bool),
    ]


def compile_native(destination):
    root = Path(__file__).resolve().parents[1]
    command = [
        "gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-fPIC", "-shared", "-I" + str(root / "source"),
        str(root / "source" / "cps1_tile.c"),
        str(root / "source" / "cps1_scene.c"),
        str(root / "source" / "cps1_sequence.c"),
        "-o", str(destination),
    ]
    subprocess.run(command, check=True, capture_output=True, timeout=60)


def native_api(path):
    library = ctypes.CDLL(str(path))
    decode = library.cps1_sequence_decode
    decode.argtypes = (ctypes.c_void_p, ctypes.c_size_t,
                       ctypes.POINTER(NativeSequence))
    decode.restype = ctypes.c_bool
    frame = library.cps1_sequence_frame
    frame.argtypes = (ctypes.POINTER(NativeSequence), ctypes.c_uint,
                      ctypes.c_void_p)
    frame.restype = ctypes.c_bool
    render = library.cps1_scene_render
    render.argtypes = (ctypes.c_void_p, ctypes.c_size_t,
                       ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t)
    render.restype = ctypes.c_bool
    return decode, frame, render


def _changed_pixels(a, b):
    if len(a) != RG_BYTES or len(b) != RG_BYTES:
        raise ValueError("invalid RGBA frame size")
    return sum(a[i:i + 4] != b[i:i + 4]
               for i in range(0, RG_BYTES, 4))


def verify():
    fake_gfx, gfx_evidence = graphics.build()
    payload, stream_evidence = timeline.build(fps=2)
    if (gfx_evidence["graphics_are_artificial"] is not True or
            stream_evidence["frame_states_are_synthetic"] is not True or
            len(fake_gfx) != graphics.REGION_BYTES or
            len(payload) != timeline.EXPECTED_SEQUENCE_BYTES):
        raise ValueError("not the known ROM-free synthetic fixtures")
    pairs = {
        "unmasked_sprite": ("priority_sprite",
                            "priority_mask_changed_rgba_pixels"),
        "priority_transparent_bit": ("priority_sprite",
                                     "priority_pen15_changed_rgba_pixels"),
        "priority_group_selective": ("priority_sprite",
                                     "priority_groups_changed_rgba_pixels"),
        "transparent_palette_unused": ("unmasked_sprite",
                                        "transparent_palette_changed_rgba_pixels"),
        "palette_channels_shift": ("unmasked_sprite",
                                    "palette_remap_changed_rgba_pixels"),
        "scroll1_unmasked": ("scroll1_priority",
                             "scroll1_priority_changed_rgba_pixels"),
        **{name: ("priority_sprite",
                  "priority_group{}_individual_changed_rgba_pixels".format(group))
           for name, group in scenes.GROUP_UNMASKED_CASES.items()},
    }
    if set(pairs.values()) == set() or len(pairs) != 10:
        raise ValueError("incomplete controlled synthetic expectations")

    with tempfile.TemporaryDirectory(prefix="stage309-native-c-code-only-") as td:
        libpath = Path(td) / "native.so"
        compile_native(libpath)
        decode, frame, render = native_api(libpath)
        raw_stream = ctypes.create_string_buffer(payload, len(payload))
        stream = NativeSequence()
        if not decode(raw_stream, len(payload), ctypes.byref(stream)):
            raise ValueError("native C refused Stage307 sequence")
        if stream.frame_count != len(scenes.CASES) or stream.fps != 2:
            raise ValueError("native sequence metadata differs")
        native_gfx = (ctypes.c_uint8 * len(fake_gfx)).from_buffer_copy(fake_gfx)
        state = ctypes.create_string_buffer(SCENE_MEMORY_BYTES)
        output = ctypes.create_string_buffer(RG_BYTES)
        frames = {}
        mismatches = 0
        for i, name in enumerate(scenes.CASES):
            if not frame(ctypes.byref(stream), i, state):
                raise ValueError("native C refused synthetic scene frame")
            if not render(native_gfx, len(fake_gfx), state, output, RG_BYTES):
                raise ValueError("native C refused synthetic graphics render")
            native_rgba = output.raw
            snapshot = scenes.synthetic_scene(name)
            reference = python_scene.render_frame(
                fake_gfx,
                [tuple(x) for x in snapshot["palette_rgb"]],
                snapshot)
            if native_rgba != reference:
                mismatches += _changed_pixels(native_rgba, reference)
            # Only in-memory artificial frames: no images or hashes exported.
            frames[name] = native_rgba
        if frame(ctypes.byref(stream), stream.frame_count, state):
            raise ValueError("out-of-bounds native frame accepted")
        effects = {}
        isolated = True
        for test_name, (base_name, effect_name) in pairs.items():
            isolated &= scenes.pure_synthetic_pair(
                scenes.synthetic_scene(base_name),
                scenes.synthetic_scene(test_name), test_name)
            effects[effect_name] = _changed_pixels(
                frames[base_name], frames[test_name])
        coverage = (isolated and
                    set(effects) == set(scenes.DIFFERENTIAL_EXPECTATIONS) and
                    all((effects[name] > 0) == changed
                        for name, changed in scenes.DIFFERENTIAL_EXPECTATIONS.items()))
        if mismatches or not coverage:
            raise ValueError("native/Python parity or visual coverage failed")
    return {
        "schema": SCHEMA,
        "status": PASS,
        "synthetic_sequence_frames_accepted_by_native_c": len(frames),
        "synthetic_cps1_rgba_pixels_compared": len(frames) * scenes.PIXELS,
        "native_python_mismatching_rgba_pixels": 0,
        "isolated_priority_and_palette_effects_checked": len(effects),
        "differential_coverage_verified": True,
        "native_out_of_range_frame_rejected": True,
        "graphics_are_artificial": True,
        "original_rom_was_read": False,
        "real_mame_frame_captured": False,
        "original_inp_wlf_replay_verified": False,
        "physical_switch_framebuffer_verified": False,
        "private_paths_or_game_pixels_exported": False,
    }


def main():
    try:
        result = verify()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError,
            ctypes.ArgumentError, AttributeError, TypeError):
        # Never leak file paths or graphics if a private environment is used.
        result = {
            "schema": SCHEMA,
            "status": BLOCKED,
            "original_rom_was_read": False,
            "physical_switch_framebuffer_verified": False,
            "private_paths_or_game_pixels_exported": False,
        }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
