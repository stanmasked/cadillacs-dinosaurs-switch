#!/usr/bin/env python3
"""Stage305: fail-closed private ORIGINAL gfx + SYNTHETIC scene parity gate.

The real authorized original 16-ROM canonical dino.zip is verified locally
before 14 differential CPS-1 compositor scenarios. Scroll/OBJ/palette
state is synthetic. Never publish ROM, frames, private paths/hashes or
MAME gameplay claims. All outputs are aggregate-only.
"""
import argparse
from pathlib import Path

try:
    from . import mame0106_private_dino_rom_canonicalize_299 as canonical
    from . import cps1_private_scene_compositor_parity as scene
    from . import wolfmame0106_private_binary_gate as private
except ImportError:
    import mame0106_private_dino_rom_canonicalize_299 as canonical
    import cps1_private_scene_compositor_parity as scene
    import wolfmame0106_private_binary_gate as private

SCHEMA = "dino-private-canonical-rom-synthetic-scene-parity-v1"
PASS = "PRIVATE_CANONICAL_DINO_SYNTHETIC_SCENE_C_PY_PARITY_PASSED"
BLOCKED_ROM = "BLOCKED_PRIVATE_CANONICAL_DINO_ORIGINAL_ROM_HASH_GATE"
BLOCKED_SCENE = "BLOCKED_PRIVATE_DINO_SYNTHETIC_SCENE_PARITY_COVERAGE"
BLOCKED_SETUP = "BLOCKED_PRIVATE_DINO_SYNTHETIC_SCENE_SETUP"


def _report(status):
    return {
        "schema": SCHEMA,
        "status": status,
        "original_cps1_rom_source_crc32_sha1_verified": False,
        "original_rom_member_count": 0,
        "synthetic_scene_cases_checked": 0,
        "synthetic_scene_rgba_pixels_compared": 0,
        "c_python_mismatching_rgba_pixels": None,
        "synthetic_priority_and_palette_metamorphic_checks_passed": False,
        "actual_gameplay_palette_or_vram_verified": False,
        "original_game_frame_captured": False,
        "original_dino_mame_execution_verified": False,
        "original_dino_inp_wlf_replay_verified": False,
        "original_gameplay_equivalence_verified": False,
        "real_nintendo_switch_framebuffer_verified": False,
        "original_rom_images_hashes_or_paths_exported": False,
    }


def _validate_native(summary):
    """Reject counterfeit success, missing pairs and false provenance."""
    if not isinstance(summary, dict):
        return False
    if summary.get("status") != "PRIVATE_NATIVE_SCENE_PARITY_PASSED":
        return False
    if (summary.get("diagnostic_only") is not True
            or summary.get("background_tile_graphics_from_original_rom") is not True
            or summary.get("palette_scroll_obj_and_priority_are_synthetic") is not True
            or summary.get("differential_inputs_verified") is not True
            or summary.get("differential_coverage_verified") is not True):
        return False
    for key in ("original_game_frame_captured", "real_gameplay_observed",
                "mame_vblank_synchronization_verified",
                "sprite_latch_timing_verified",
                "nintendo_switch_framebuffer_parity_verified",
                "source_rom_or_derived_pixel_bytes_written_to_disk",
                "private_paths_or_game_digests_in_report"):
        if summary.get(key) is not False:
            return False
    cases = summary.get("scenario_results")
    if (not isinstance(cases, list) or len(cases) != len(scene.CASES)
            or summary.get("synthetic_cases") != len(scene.CASES)
            or summary.get("scene_size") != [scene.WIDTH, scene.HEIGHT]
            or summary.get("pixels_compared") != len(scene.CASES) * scene.PIXELS
            or summary.get("mismatching_pixels_total") != 0):
        return False
    if (len(set(scene.CASES)) != len(scene.CASES) or
            not all(isinstance(c, dict)
                    and c.get("scenario") == name
                    and type(c.get("compared_rgba_pixels")) is int
                    and c["compared_rgba_pixels"] == scene.PIXELS
                    and type(c.get("mismatching_rgba_pixels")) is int
                    and c["mismatching_rgba_pixels"] == 0
                    for c, name in zip(cases, scene.CASES))):
        return False
    if (len(scene.DIFFERENTIAL_EXPECTATIONS) < 8 or
            any(type(summary.get(key)) is not int
                or summary[key] < 0
                or (summary[key] > 0) != expected
                for key, expected in scene.DIFFERENTIAL_EXPECTATIONS.items())):
        return False
    return True


def run(rom, *, verify=canonical.verify_archive,
        compositor=scene.compare_private_native_scene_compositor):
    """Read original content privately; report ONLY conservative counts."""
    result = _report(BLOCKED_ROM)
    rom = canonical._private_regular(Path(rom), canonical.MAX_ZIP_BYTES)
    preflight = verify(rom, manifest=canonical.MANIFEST)
    if (not isinstance(preflight, dict)
            or preflight.get("status") != canonical.MATCH
            or preflight.get("required_rom_members_matched_by_crc32_sha1")
            != len(canonical.MANIFEST)
            or preflight.get("required_payloads_crc_sha1_integrity_checked") is not True):
        return result
    result["original_cps1_rom_source_crc32_sha1_verified"] = True
    result["original_rom_member_count"] = len(canonical.MANIFEST)
    result["status"] = BLOCKED_SCENE
    native = compositor(rom)
    if not _validate_native(native):
        return result
    result["status"] = PASS
    result["synthetic_scene_cases_checked"] = len(scene.CASES)
    result["synthetic_scene_rgba_pixels_compared"] = len(scene.CASES) * scene.PIXELS
    result["c_python_mismatching_rgba_pixels"] = 0
    result["synthetic_priority_and_palette_metamorphic_checks_passed"] = True
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rom", type=Path, required=True,
                    help="private, exact 16-member original source-verified dino.zip")
    ap.add_argument("--out", type=Path, required=True,
                    help="new aggregate-only private JSON receipt outside repository")
    args = ap.parse_args(argv)
    try:
        status = run(args.rom)
    except Exception:
        # No exception message, raw graphics, source file paths, or ROM digests.
        status = _report(BLOCKED_SETUP)
    private.write_private_receipt(args.out, status)
    print(status["status"])
    return 0 if status["status"] == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
