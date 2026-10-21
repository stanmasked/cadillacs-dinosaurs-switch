#!/usr/bin/env python3
"""Stage308: create synthetic, ROM-free CPS-1 graphics for the Switch viewer.

This is a deliberate fake 4-MiB graphics region. Never derived from dino,
MAME, ROM dumps, screenshots, or video. It is only a diagnostic pixel pattern.
Generate it locally; do not commit gfx.bin to the repository.
"""
import argparse
import hashlib
from pathlib import Path

try:
    from . import cps1_synthetic_scene_sequence_307 as stage307
    from . import wolfmame0106_private_binary_gate as privacy
except ImportError:
    import cps1_synthetic_scene_sequence_307 as stage307
    import wolfmame0106_private_binary_gate as privacy

SCHEMA = "dino-rom-free-switch-synthetic-gfx-v1"
PASS = "SYNTHETIC_CPS1_GFX_READY_NOT_ORIGINAL_GAME"
BLOCKED = "BLOCKED_SYNTHETIC_CPS1_GFX"
REGION_BYTES = 0x400000
PERIOD_BYTES = 32768
SEED = b"ROM-FREE CPS1 GRAPHICS FIXTURE / STAGE308 / NOT ORIGINAL DINO ROM"
MARKER = b"ROM-FREE CPS1 SYNTHETIC PIXELS STAGE308"


def build():
    """256 invented 16x16 tile blocks repeated 128 times, CPS-1 planar bytes.

    Hashing a PUBLIC, hard-coded text seed here is a byte-pattern generator,
    not a hash of copyrighted, private or game-derived data.
    """
    period = bytearray(b"".join(
        hashlib.sha256(SEED + n.to_bytes(4, "little")).digest()
        for n in range(PERIOD_BYTES // hashlib.sha256().digest_size)
    ))
    period[:len(MARKER)] = MARKER
    gfx = bytes(period) * (REGION_BYTES // PERIOD_BYTES)
    if (len(gfx) != REGION_BYTES or gfx[:len(MARKER)] != MARKER or
            gfx[PERIOD_BYTES:PERIOD_BYTES + len(MARKER)] != MARKER):
        raise ValueError("synthetic graphics invariant failed")
    report = {
        "schema": SCHEMA,
        "status": PASS,
        "gfx_file_bytes": REGION_BYTES,
        "synthetic_pattern_period_bytes": PERIOD_BYTES,
        "synthetic_tile16_variants": PERIOD_BYTES // 128,
        "native_viewer_required_gfx_bytes": REGION_BYTES,
        "graphics_are_artificial": True,
        "compatible_with_stage307_sequence_format": True,
        "original_rom_was_read": False,
        "original_rom_or_derived_graphics_embedded": False,
        "original_mame_execution_verified": False,
        "original_inp_wlf_playback_verified": False,
        "switch_hardware_display_verified": False,
        "private_game_paths_or_assets_exported": False,
    }
    return gfx, report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path,
                        help="new private gfx.bin path outside the checkout")
    parser.add_argument("--report", type=Path,
                        help="new optional private aggregate-only JSON receipt")
    args = parser.parse_args(argv)
    try:
        out = stage307._safe_output(args.out)
        if args.report is not None:
            receipt = stage307._safe_output(args.report)
            if out.resolve() == receipt.resolve():
                raise ValueError("receipt cannot overwrite gfx output")
        gfx, result = build()
        stage307._write_exclusive(out, gfx)
        if args.report is not None:
            privacy.write_private_receipt(args.report, result)
    except (OSError, ValueError, TypeError):
        result = {
            "schema": SCHEMA,
            "status": BLOCKED,
            "original_rom_was_read": False,
            "switch_hardware_display_verified": False,
            "private_game_paths_or_assets_exported": False,
        }
    print(result["status"])
    return 0 if result["status"] == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
