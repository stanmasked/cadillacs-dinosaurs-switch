#!/usr/bin/env python3
"""Stage310: safely stage a ROM-free two-file CPS-1 diagnostic SD bundle.

Generates only artificial Stage307/308 data. NEVER reads an original ROM,
private MAME recording, original graphics, or previously installed gfx.bin.
Creates a brand-new directory outside the repository, refuses to overwrite
existing files, and places a local-only receipt last when fully verified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

try:
    from . import cps1_synthetic_scene_sequence_307 as timeline
    from . import cps1_synthetic_gfx_fixture_308 as graphics
    from . import wolfmame0106_private_binary_gate as privacy
except ImportError:
    import cps1_synthetic_scene_sequence_307 as timeline
    import cps1_synthetic_gfx_fixture_308 as graphics
    import wolfmame0106_private_binary_gate as privacy

SCHEMA = "dino-rom-free-switch-sd-bundle-v1"
PASS = "ROM_FREE_SWITCH_SD_DIAGNOSTIC_BUNDLE_STAGED_NOT_GAMEPLAY"
BLOCKED = "BLOCKED_ROM_FREE_SWITCH_SD_DIAGNOSTIC_BUNDLE"
APP_RELATIVE = Path("switch") / "cadillacs-dinosaurs-switch"
RECEIPT_NAME = "rom-free-install-ready.json"


def _validate(gfx, sequence):
    """Accept only the explicit, unambiguous, expected synthetic file pair."""
    # Framing, marker and repetitive layout alone CANNOT prove provenance:
    # an unrelated (possibly game-derived) 32-KiB period can be repeated
    # with the marker intact. Require byte-exact equality to a fresh known
    # ROM-free generator output, never to user-controlled external bytes.
    expected_gfx, expected_gfx_report = graphics.build()
    if (type(gfx) is not bytes or gfx != expected_gfx or
            expected_gfx_report.get("graphics_are_artificial") is not True or
            expected_gfx_report.get("original_rom_was_read") is not False):
        raise ValueError("gfx data is not the canonical artificial Stage308 fixture")
    if type(sequence) is not bytes:
        raise ValueError("scene sequence is not a byte string")
    details = timeline._inspect(
        sequence, fps=2, frames=timeline.SCENE_COUNT)
    # A CRC32 can be recalculated over arbitrary binary scene contents.
    # Validate the exact canonical sequence, not merely its valid envelope.
    expected_sequence, expected_scene_report = timeline.build(fps=2)
    if (sequence != expected_sequence or
            expected_scene_report.get("frame_states_are_synthetic") is not True or
            details["status"] != timeline.PASS or
            details["frame_states_are_synthetic"] is not True or
            details["original_gfx_rom_is_not_embedded"] is not True):
        raise ValueError("sequence is not the canonical artificial Stage307 fixture")
    return details


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            data = handle.read(128 * 1024)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def _file_verified(path, data):
    # File properties matter: neither symlinks nor unknown extra bytes are OK.
    path = Path(path)
    if (path.is_symlink() or not path.is_file() or
            (path.stat().st_mode & 0o777) != 0o600 or
            path.stat().st_size != len(data) or
            _sha256_file(path) != hashlib.sha256(data).hexdigest()):
        raise ValueError("private staged file failed exact readback")
    return hashlib.sha256(data).hexdigest()


def stage(new_folder):
    """Create a new external directory. Never use an existing SD folder.

    Failure can leave a PARTIAL private directory, but a success manifest is
    written last. Never delete files that another process might have created.
    """
    folder = timeline._safe_output(Path(new_folder))
    fake_gfx, gfx_report = graphics.build()
    sequence, seq_report = timeline.build(fps=2)
    _validate(fake_gfx, sequence)
    if (gfx_report["graphics_are_artificial"] is not True or
            gfx_report["original_rom_was_read"] is not False or
            seq_report["frame_states_are_synthetic"] is not True):
        raise ValueError("synthetic provenance check failed")

    os.mkdir(folder, 0o700)
    os.mkdir(folder / "switch", 0o700)
    location = folder / APP_RELATIVE
    os.mkdir(location, 0o700)

    graphics_path = location / "gfx.bin"
    sequence_path = location / "sequence.bin"
    timeline._write_exclusive(graphics_path, fake_gfx)
    timeline._write_exclusive(sequence_path, sequence)
    graphics_digest = _file_verified(graphics_path, fake_gfx)
    sequence_digest = _file_verified(sequence_path, sequence)

    # Local-only receipt contains checksums of INVENTED data, never ROM hashes.
    receipt = {
        "schema": SCHEMA,
        "status": PASS,
        "local_sd_relative_directory": APP_RELATIVE.as_posix(),
        "synthetic_graphics_filename": "gfx.bin",
        "synthetic_sequence_filename": "sequence.bin",
        "synthetic_graphics_bytes": graphics.REGION_BYTES,
        "synthetic_sequence_bytes": timeline.EXPECTED_SEQUENCE_BYTES,
        "total_synthetic_data_bytes":
            graphics.REGION_BYTES + timeline.EXPECTED_SEQUENCE_BYTES,
        "synthetic_graphics_sha256": graphics_digest,
        "synthetic_sequence_sha256": sequence_digest,
        "all_14_scene_envelopes_validated": True,
        "synthetic_graphics_readback_verified": True,
        "synthetic_sequence_readback_verified": True,
        "ready_for_manual_local_sd_copy": True,
        "graphics_and_scenes_are_artificial": True,
        "original_rom_or_original_graphics_read": False,
        "original_gameplay_captured": False,
        "original_inp_wlf_playback_verified": False,
        "host_c_test_run_by_this_command": False,
        "nintendo_switch_or_emulator_execution_verified": False,
        "physical_switch_framebuffer_verified": False,
        "private_paths_or_game_assets_exported": False,
    }
    privacy.write_private_receipt(folder / RECEIPT_NAME, receipt)
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", required=True, type=Path,
                        help="NEW external private staging directory")
    args = parser.parse_args(argv)
    try:
        receipt = stage(args.out_dir)
        status = receipt["status"]
    except (OSError, ValueError, KeyError, TypeError):
        status = BLOCKED
    print(status)
    return 0 if status == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
