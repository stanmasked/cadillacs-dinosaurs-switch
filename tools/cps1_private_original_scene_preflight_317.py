#!/usr/bin/env python3
"""Stage317: privately bind original ROM GFX to native C/Python 14-scene parity.

Run exclusively on the user's own machine with their privately prepared
source-verified canonical MAME 0.106 dino.zip and Stage315 SD root. Public
tests mock the interfaces; never upload original ROMs, graphics or frames.

This verifies STATIC original ROM graphics combined with deliberately
SYNTHETIC palette/scroll/OBJ/priority. Not actual original gameplay.
"""
import argparse
import json
from pathlib import Path

try:
    from . import cps1_private_canonical_scene_gate_305 as gate305
    from . import cps1_private_original_gfx_synthetic_sd_315 as stage315
    from . import nexium_private_original_gfx_optical_316 as gate316
    from . import wolfmame0106_private_binary_gate as private
    from . import cps1_private_scene_compositor_parity as scene
except ImportError:
    import cps1_private_canonical_scene_gate_305 as gate305
    import cps1_private_original_gfx_synthetic_sd_315 as stage315
    import nexium_private_original_gfx_optical_316 as gate316
    import wolfmame0106_private_binary_gate as private
    import cps1_private_scene_compositor_parity as scene

SCHEMA = "dino-stage317-private-original-gfx-native-c-python-scene-preflight-v1"
PASS = "PRIVATE_ORIGINAL_GFX_NATIVE_C_PY_14_SCENES_AND_SD_MATCH"
BLOCKED = "BLOCKED_PRIVATE_ORIGINAL_GFX_NATIVE_C_PY_SCENE_PREFLIGHT"
PIXELS = scene.WIDTH * scene.HEIGHT * 14


def validate_stage305(record):
    """Do not allow a mocked 305 success or misleading provenance fields."""
    if type(record) is not dict:
        raise ValueError("private original GFX native scene record absent")
    exact = {
        "schema": gate305.SCHEMA,
        "status": gate305.PASS,
        "original_cps1_rom_source_crc32_sha1_verified": True,
        "original_rom_member_count": 16,
        "synthetic_scene_cases_checked": 14,
        "synthetic_scene_rgba_pixels_compared": PIXELS,
        "c_python_mismatching_rgba_pixels": 0,
        "synthetic_priority_and_palette_metamorphic_checks_passed": True,
        "actual_gameplay_palette_or_vram_verified": False,
        "original_game_frame_captured": False,
        "original_dino_mame_execution_verified": False,
        "original_dino_inp_wlf_replay_verified": False,
        "original_gameplay_equivalence_verified": False,
        "real_nintendo_switch_framebuffer_verified": False,
        "original_rom_images_hashes_or_paths_exported": False,
    }
    for key,expected in exact.items():
        got=record.get(key)
        if type(got) is not type(expected) or got!=expected:
            raise ValueError("incomplete original graphics scene parity evidence")
    return True


def run(rom,sd_root,*,c_python_gate=None,sd_gate=None):
    if c_python_gate is None: c_python_gate=gate305.run
    if sd_gate is None: sd_gate=gate316._local_inputs
    # Stage316 checks both private ROM provenance and exact two-file SD
    # readback; Stage305 independently compiles actual portable native C.
    graphics=sd_gate(Path(rom),Path(sd_root))
    if type(graphics) is not bytes or len(graphics)!=stage315.GFX_BYTES:
        raise ValueError("not an exact original CPS-1 graphics region")
    proof=c_python_gate(Path(rom))
    validate_stage305(proof)
    return {
        "schema": SCHEMA,
        "status": PASS,
        "verified_original_rom_members": 16,
        "private_original_graphics_bytes": stage315.GFX_BYTES,
        "native_c_python_synthetic_scenes_matched": 14,
        "native_c_python_rgba_pixels_matched": PIXELS,
        "native_c_python_rgba_pixel_mismatches": 0,
        "synthetic_priority_palette_differentials_checked": True,
        "stage315_private_sd_graphics_and_synthetic_sequence_matched": True,
        "runtime_scene_state_is_artificial": True,
        "original_game_mame_execution_verified": False,
        "original_gameplay_vram_palette_captured": False,
        "original_gameplay_frames_captured": False,
        "original_inp_wlf_replay_verified": False,
        "original_graphics_host_x11_display_verified": False,
        "physical_nintendo_switch_display_verified": False,
        "private_original_pixels_paths_hashes_or_assets_exported": False,
    }


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom",required=True,type=Path)
    ap.add_argument("--sd-root",required=True,type=Path)
    ap.add_argument("--out",required=True,type=Path)
    args=ap.parse_args(argv)
    try:
        if (not private.outside_repo(args.out) or args.out.exists()
                or args.out.is_symlink() or not args.out.parent.is_dir()
                or any(x.is_symlink() for x in args.out.parents)):
            raise ValueError("private exclusive aggregate-only receipt required")
        record=run(args.rom,args.sd_root)
        code=0
    except Exception:
        # Errors may contain original paths/data: never echo exception text.
        record={
            "schema": SCHEMA, "status":BLOCKED,
            "native_c_python_synthetic_scenes_matched":0,
            "original_gameplay_frames_captured":False,
            "original_graphics_host_x11_display_verified":False,
            "physical_nintendo_switch_display_verified":False,
            "private_original_pixels_paths_hashes_or_assets_exported":False,
        }
        code=2
    try:
        private.write_private_receipt(args.out,record)
    except (OSError,ValueError):
        print(BLOCKED)
        return 2
    print(record["status"])
    return code


if __name__=="__main__":
    raise SystemExit(main())
