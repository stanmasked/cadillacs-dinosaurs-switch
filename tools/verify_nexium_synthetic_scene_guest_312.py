#!/usr/bin/env python3
"""Stage312: verify evidence emitted by an actual opt-in NeXium NRO run.

Only artificial graphics from Stage308 and invented frame data from Stage307
are rendered independently. No commercial ROM, keys, captures or photographs.
Never turn a host-only test or an emulator launch into a guest-render claim.
"""
import argparse
import json
from pathlib import Path
import re

try:
    from . import cps1_synthetic_gfx_fixture_308 as graphics
    from . import cps1_private_scene_compositor_parity as scenes
    from . import cps1_frame
except ImportError:
    import cps1_synthetic_gfx_fixture_308 as graphics
    import cps1_private_scene_compositor_parity as scenes
    import cps1_frame

SCHEMA = "dino-stage312-nexium-synthetic-scene-real-guest-v1"
PASS = "NEXIUM_GUEST_SYNTHETIC_SCENES_SUBMITTED_PYTHON_PARITY"
BLOCKED = "BLOCKED_NO_AUTHENTIC_GUEST_SCENE_TRACE"
HEADER = "event,index,scene_fnv64,screen_fnv64"
LINE = re.compile(r"FRAME_SUBMITTED,(0|[1-9][0-9]*),([0-9A-F]{16}),([0-9A-F]{16})\Z")
COUNT = 14
MASK = (1 << 64) - 1


def fnv64(blob):
    digest = 14695981039346656037
    for byte in blob:
        digest = ((digest ^ byte) * 1099511628211) & MASK
    return digest


def validate_text(source):
    if not isinstance(source, str) or len(source) > 2048:
        raise ValueError("invalid bounded guest witness")
    lines = source.splitlines()
    if len(lines) != COUNT + 1 or lines[0] != HEADER:
        raise ValueError("guest trace not a complete fourteen-frame trace")
    known_gfx, proof = graphics.build()
    if proof["graphics_are_artificial"] is not True:
        raise ValueError("unknown fixture graphics")
    seen = set()
    screen_samples = set()
    scene_hashes = []
    for expected, row in enumerate(lines[1:]):
        match = LINE.fullmatch(row)
        if not match:
            raise ValueError("malformed or unauthenticated scene row")
        index = int(match.group(1))
        if index != expected or index in seen:
            raise ValueError("missing, repeated or out-of-order guest scene")
        seen.add(index)
        supplied_scene = int(match.group(2), 16)
        screen = int(match.group(3), 16)
        if screen == 0:
            raise ValueError("empty submitted guest framebuffer sample")
        scene_state = scenes.synthetic_scene(scenes.CASES[index])
        reference = cps1_frame.render_frame(
            known_gfx,
            [tuple(entry) for entry in scene_state["palette_rgb"]],
            scene_state)
        expected_scene = fnv64(reference)
        if supplied_scene != expected_scene:
            raise ValueError("guest scene pixels differ from independent Python")
        scene_hashes.append(supplied_scene)
        screen_samples.add(screen)
    if len(screen_samples) < 4 or len(set(scene_hashes)) < 4:
        raise ValueError("submitted framebuffer did not change meaningfully")
    return {
        "schema": SCHEMA,
        "status": PASS,
        "scene_frames_in_native_guest_submission_order": COUNT,
        "native_guest_scene_hashes_matched_independent_python": COUNT,
        "native_guest_screen_sample_values_unique": len(screen_samples),
        "complete_sequence_verified": True,
        "no_original_rom_or_gameplay_used": True,
        "original_cps1_frame_capture_verified": False,
        "physical_nintendo_switch_execution_verified": False,
        "host_visible_display_capture_verified": False,
        "original_inp_wlf_replay_verified": False,
        "original_rom_or_guest_pixels_exported": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guest-trace", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        # Fail closed on missing or unexpected paths and preserve only a
        # bounded aggregate report; NEVER copy raw guest frame data into CI.
        if args.guest_trace.is_symlink() or not args.guest_trace.is_file():
            raise ValueError("missing guest-generated evidence")
        text = args.guest_trace.read_text("utf-8")
        result = validate_text(text)
        code = 0
    except (OSError, ValueError, UnicodeError, KeyError, TypeError):
        result = {
            "schema": SCHEMA,
            "status": BLOCKED,
            "complete_sequence_verified": False,
            "host_visible_display_capture_verified": False,
            "original_rom_or_guest_pixels_exported": False,
        }
        code = 2
    args.summary.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",
                            encoding="utf-8")
    print(result["status"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
