#!/usr/bin/env python3
"""Stage314 — fail-closed comparison of TWO actual Stage313 NeXium cold boots.

This comparator does not run an emulator. Only the CI matrix execution
provides the independent real-run provenance; fixture unit tests alone do
not prove anything about a Nintendo Switch guest or X11 output.
"""
import argparse
import json
from pathlib import Path

SCHEMA = "dino-stage314-two-cold-nexium-optical-boots-v1"
PASS = "TWO_INDEPENDENT_NEXIUM_OPTICAL_GUEST_BOOTS_CONFIRMED"
BLOCKED = "BLOCKED_TWO_INDEPENDENT_NEXIUM_OPTICAL_BOOTS"
STAGE313_SCHEMA = "dino-stage313-nexium-optical-scene-14-v1"
STAGE313_PASS = "NEXIUM_HOST_OPTICAL_14_SYNTHETIC_FRAMES_CONFIRMED"


def _read_and_check(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8192:
        raise ValueError("missing or unsafe cold boot result")
    record = json.loads(path.read_text(encoding="utf-8"))
    if type(record) is not dict:
        raise ValueError("optical summary is not an object")
    expected = {
        "schema": STAGE313_SCHEMA,
        "status": STAGE313_PASS,
        "synthetic_guest_and_host_frames_bound": 14,
        "host_optical_frame_identity_all_14": True,
        "host_visible_scene_pixels_verified": True,
        "native_guest_reference_scene_parity": True,
        "original_rom_or_gameplay_used": False,
        "original_gameplay_frame_display_verified": False,
        "physical_switch_display_verified": False,
        "private_host_screenshots_uploaded": False,
        "host_gpu_scanout_timing_verified": False,
    }
    for key, expected_value in expected.items():
        value = record.get(key)
        if type(value) is not type(expected_value) or value != expected_value:
            raise ValueError("optical result lacks proven field: " + key)
    sample_count = record.get("host_scene_pixel_sample_min_matched")
    if type(sample_count) is not int or not 10 <= sample_count <= 25:
        raise ValueError("host scene pixel sample count outside contract")
    return sample_count


def compare(boot_a, boot_b):
    if boot_a.resolve() == boot_b.resolve():
        raise ValueError("cannot compare a cold-boot result with itself")
    minima = (_read_and_check(boot_a), _read_and_check(boot_b))
    return {
        "schema": SCHEMA,
        "status": PASS,
        "independently_started_isolated_guest_jobs": 2,
        "real_guest_frames_verified_per_boot": 14,
        "real_host_optical_frames_verified_per_boot": 14,
        "independent_python_reference_matching_both_runs": True,
        "minimum_matched_host_scene_pixels_across_both_runs": min(minima),
        "two_real_boot_summaries_accepted": True,
        "host_visible_synthetic_scenes_reproduced": True,
        "original_rom_or_gameplay_used": False,
        "original_gameplay_frame_display_verified": False,
        "physical_switch_display_verified": False,
        "private_host_screenshots_uploaded": False,
        "original_inp_wlf_replay_verified": False,
        "host_gpu_scanout_timing_verified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--boot-a", required=True, type=Path)
    parser.add_argument("--boot-b", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare(args.boot_a, args.boot_b)
        rc = 0
    except (ValueError, TypeError, OSError, UnicodeError,
            json.JSONDecodeError):
        result = {
            "schema": SCHEMA,
            "status": BLOCKED,
            "two_real_boot_summaries_accepted": False,
            "host_visible_synthetic_scenes_reproduced": False,
            "physical_switch_display_verified": False,
            "private_host_screenshots_uploaded": False,
        }
        rc = 2
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                        encoding="utf-8")
    print(result["status"])
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
