#!/usr/bin/env python3
"""Stage315: PRIVATE original CPS-1 graphics + SYNTHETIC 14-scene Switch SD.

This is a local-only staging tool for a user-authorized canonical MAME 0.106
16-ROM dino.zip. It reads real ROM bytes only AFTER CRC32+SHA1 manifest
verification, and NEVER uploads original data to GitHub, CI or chat.

It combines source-authenticated STATIC graphics and artificially invented
scene state, NOT authentic original arcade gameplay, VRAM, palette, or input.
All exported pixels / GFX remain in a new external 0700 private directory.
"""
import argparse
import hashlib
import os
from pathlib import Path

try:
    from . import mame0106_private_dino_rom_canonicalize_299 as canonical
    from . import cps1_private_native_tile_parity as tiles
    from . import cps1_synthetic_scene_sequence_307 as sequence
    from . import cps1_rom_free_sd_bundle_310 as synthetic
    from . import wolfmame0106_private_binary_gate as guard
except ImportError:
    import mame0106_private_dino_rom_canonicalize_299 as canonical
    import cps1_private_native_tile_parity as tiles
    import cps1_synthetic_scene_sequence_307 as sequence
    import cps1_rom_free_sd_bundle_310 as synthetic
    import wolfmame0106_private_binary_gate as guard

SCHEMA = "dino-stage315-private-original-gfx-synthetic-switch-scene-sd-v1"
PASS = "PRIVATE_SOURCE_VERIFIED_DINO_GFX_SYNTHETIC_SWITCH_SCENES_STAGED"
BLOCKED = "BLOCKED_PRIVATE_DINO_GFX_SYNTHETIC_SWITCH_SCENE_STAGING"
GFX_BYTES = 0x400000
SCENE_COUNT = 14
RECEIPT = "private-original-graphics-synthetic-scenes-ready.json"
APP = Path("switch") / "cadillacs-dinosaurs-switch"


def _digest_bytes(data):
    return hashlib.sha256(data).digest()


def _private_canonical_file(path):
    """No symlinks or repo-contained source files; require canonical ZIP."""
    path = canonical._private_regular(Path(path), canonical.MAX_ZIP_BYTES)
    if path.name != "dino.zip":
        raise ValueError("Stage315 accepts only private canonical dino.zip")
    return path


def _validate_rom_evidence(result):
    """Do not trust a partial source checksum count or ambiguous aliases."""
    return (type(result) is dict and result.get("status") == canonical.MATCH
            and type(result.get("required_rom_members_matched_by_crc32_sha1")) is int
            and result["required_rom_members_matched_by_crc32_sha1"] ==
                len(canonical.MANIFEST)
            and result.get("required_payloads_crc_sha1_integrity_checked") is True
            and result.get("canonical_mame_zip_written") is False
            and result.get("all_original_payload_bytes_kept_private") is True
            and result.get("actual_historical_mame_rom_loader_verified") is False
            and result.get("original_dino_gameplay_verified") is False)


def _readback_matches(path, data):
    """Exact private file read-back with no file-derived hash in receipt."""
    if (path.is_symlink() or not path.is_file() or
            (path.stat().st_mode & 0o777) != 0o600 or
            path.stat().st_size != len(data)):
        raise ValueError("private staged file is missing or mutated")
    digest = hashlib.sha256()
    with path.open("rb") as inp:
        while True:
            chunk = inp.read(128*1024)
            if not chunk:
                break
            digest.update(chunk)
    if digest.digest() != _digest_bytes(data):
        raise ValueError("private staged file does not match source")
    return True


def _report():
    """Never reveal original content, source paths, original ROM hashes."""
    return {
        "schema": SCHEMA,
        "status": PASS,
        "original_rom_source_crc32_sha1_verified": True,
        "original_rom_members_verified": len(canonical.MANIFEST),
        "private_cps1_gfx_bytes_written": GFX_BYTES,
        "synthetic_sequence_frames": SCENE_COUNT,
        "synthetic_sequence_fps": 2,
        "synthetic_sequence_bytes_written": sequence.EXPECTED_SEQUENCE_BYTES,
        "private_gfx_readback_exact": True,
        "synthetic_sequence_readback_exact": True,
        "private_sd_structure_ready_for_local_use": True,
        "original_graphics_are_from_source_verified_rom": True,
        "palette_scroll_obj_priority_are_synthetic": True,
        "actual_mame_gameplay_executed": False,
        "original_gameplay_vram_palette_observed": False,
        "original_game_frames_captured": False,
        "original_inp_wlf_replay_verified": False,
        "nexium_original_gfx_guest_run_verified": False,
        "physical_nintendo_switch_display_verified": False,
        "original_graphics_or_hashes_in_public_artifacts": False,
        "private_paths_in_report": False,
    }


def stage(rom, new_folder, *, verify=None, load=None):
    """Preflight all original ROM bytes BEFORE making any output directory.

    Injection is only for ROM-free unit tests. The public CI never runs
    this entrypoint with an original ROM or publishes any private graphics.
    """
    rom = _private_canonical_file(rom)
    folder = sequence._safe_output(Path(new_folder))
    if verify is None:
        verify = canonical.verify_archive
    if load is None:
        load = tiles.read_private_gfx

    evidence = verify(rom, manifest=canonical.MANIFEST)
    if not _validate_rom_evidence(evidence):
        raise ValueError("historical original ROM source validation not complete")
    raw = load(rom)
    if type(raw) is not bytes or len(raw) != GFX_BYTES:
        raise ValueError("private original CPS-1 gfx reconstruction invalid")
    # Stage308 artificial graphics are not genuine original data and must
    # never be mislabeled in a report as source-verified original content.
    if raw.startswith(b"ROM-FREE CPS1 SYNTHETIC PIXELS STAGE308"):
        raise ValueError("artificial graphics mislabeled as original game ROM")

    timeline, receipt = sequence.build(fps=2)
    expected, _ = sequence.build(fps=2)
    if (type(timeline) is not bytes or timeline != expected
            or receipt.get("status") != sequence.PASS
            or receipt.get("frame_states_are_synthetic") is not True
            or receipt.get("original_gfx_rom_is_not_embedded") is not True):
        raise ValueError("sequence is not deterministic synthetic Stage307 data")

    # Neither the real input archive nor this derived output may be inside
    # the repository or hidden behind symlinked parent directories.
    if not guard.outside_repo(folder) or any(x.is_symlink() for x in folder.parents):
        raise ValueError("unsafe output location")
    os.mkdir(folder, 0o700)
    os.mkdir(folder / "switch", 0o700)
    app = folder / APP
    os.mkdir(app, 0o700)
    gfx_path = app / "gfx.bin"
    seq_path = app / "sequence.bin"
    sequence._write_exclusive(gfx_path, raw)
    sequence._write_exclusive(seq_path, timeline)
    _readback_matches(gfx_path, raw)
    _readback_matches(seq_path, timeline)
    report = _report()
    # Only emit after BOTH files pass full checks. Failure leaves a private,
    # incomplete staging directory but NEVER writes a success receipt.
    guard.write_private_receipt(folder / RECEIPT, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", required=True, type=Path,
                        help="private canonical source-authenticated dino.zip")
    parser.add_argument("--out-dir", required=True, type=Path,
                        help="new directory OUTSIDE public GitHub repository")
    args = parser.parse_args(argv)
    try:
        result = stage(args.rom, args.out_dir)
    except Exception:
        # Paths, original ROM hashes or decoded pixels NEVER enter stdout.
        print(BLOCKED)
        return 2
    print(result["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
