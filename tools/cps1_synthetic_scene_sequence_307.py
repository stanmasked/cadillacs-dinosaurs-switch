#!/usr/bin/env python3
"""Stage307: build a 14-case ROM-FREE CPS-1 diagnostic sequence for Switch.

The synthetic scene RAM, palette, OBJ and priority state comes from
Stage305's deliberately invented fixtures. No game ROM, original
input/movie frame, or emulator playback is needed or included.

The resulting private sequence.bin can be used beside a separately
owned local gfx.bin on the Switch diagnostic tile viewer. It is NOT
a recording of original Cadillacs and Dinosaurs gameplay.
"""
import argparse
import os
import struct
import zlib
from pathlib import Path

try:
    from . import cps1_private_scene_compositor_parity as scenes
    from . import cps1_scene_export as exporter
    from . import cps1_sequence_export as sequence
    from . import wolfmame0106_private_binary_gate as privacy
except ImportError:
    import cps1_private_scene_compositor_parity as scenes
    import cps1_scene_export as exporter
    import cps1_sequence_export as sequence
    import wolfmame0106_private_binary_gate as privacy

SCHEMA = "dino-rom-free-fourteen-scene-switch-diagnostic-sequence-v1"
PASS = "SYNTHETIC_CPS1_SWITCH_SCENE_SEQUENCE_READY_NOT_GAMEPLAY"
BLOCKED = "BLOCKED_SYNTHETIC_CPS1_SCENE_SEQUENCE"
SCENE_COUNT = 14
EXPECTED_SCENE_BYTES = exporter.FILE_BYTES
EXPECTED_SEQUENCE_BYTES = sequence.HEADER_BYTES + SCENE_COUNT * EXPECTED_SCENE_BYTES


def _inspect(encoded, *, fps, frames):
    """Parse headers and check both outer and inner CRC, no rendered media."""
    if (type(encoded) is not bytes
            or type(fps) is not int or not 1 <= fps <= 60
            or type(frames) is not int or frames != SCENE_COUNT
            or len(encoded) != EXPECTED_SEQUENCE_BYTES
            or encoded[:8] != sequence.MAGIC):
        raise ValueError("invalid synthetic CPS-1 diagnostic envelope")
    count, declared_fps, outer_crc, reserved = struct.unpack_from(
        "<HHII", encoded, 8)
    if (count != SCENE_COUNT or declared_fps != fps or reserved != 0
            or zlib.crc32(encoded[sequence.HEADER_BYTES:]) != outer_crc):
        raise ValueError("invalid CPS-1 sequence count, rate or checksum")
    seen = set()
    for i in range(SCENE_COUNT):
        start = sequence.HEADER_BYTES + i * EXPECTED_SCENE_BYTES
        blob = encoded[start:start + EXPECTED_SCENE_BYTES]
        if (blob[:8] != exporter.MAGIC
                or struct.unpack_from("<I", blob, 8)[0] != exporter.PAYLOAD_BYTES
                or zlib.crc32(blob[16:]) != struct.unpack_from("<I", blob, 12)[0]
                or any(x > 1 for x in blob[32:35])
                or blob[35] != 0):
            raise ValueError("invalid synthetic scene frame envelope")
        seen.add(zlib.crc32(blob))
    if len(seen) != SCENE_COUNT:
        raise ValueError("diagnostic scene sequence contains duplicate frames")
    return {
        "schema": SCHEMA,
        "status": PASS,
        "scene_frames": SCENE_COUNT,
        "scene_names_in_fixed_order": list(scenes.CASES),
        "target_cps1_width": scenes.WIDTH,
        "target_cps1_height": scenes.HEIGHT,
        "frames_per_second": fps,
        "sequence_file_bytes": EXPECTED_SEQUENCE_BYTES,
        "inner_scene_crc_checks_passed": SCENE_COUNT,
        "outer_sequence_crc_checked": True,
        "frame_states_are_synthetic": True,
        "original_gfx_rom_is_not_embedded": True,
        "original_mame_gameplay_frame_captured": False,
        "real_vram_palette_or_obj_captured": False,
        "original_inp_wlf_replay_verified": False,
        "switch_hardware_display_verified": False,
        "private_game_paths_or_assets_exported": False,
    }


def build(*, fps=2, provider=scenes.synthetic_scene,
          pack=exporter.pack_scene, pack_timeline=sequence.pack_sequence):
    """Generate and strictly inspect exact full CPS-1 diagnostic sequence."""
    if type(fps) is not int or not 1 <= fps <= 60:
        raise ValueError("diagnostic FPS must be a 1..60 integer")
    if (not isinstance(scenes.CASES, tuple) or
            len(scenes.CASES) != SCENE_COUNT
            or len(set(scenes.CASES)) != SCENE_COUNT
            or any(type(name) is not str or not name for name in scenes.CASES)):
        raise ValueError("incomplete or nonunique Stage305 compositor cases")
    blobs = []
    for name in scenes.CASES:
        state = provider(name)
        if (type(state) is not dict or
                state.get("pixel_parity_eligible") is False or
                state.get("buffered_obj_source") == "UNAVAILABLE_MAME_LUA"):
            raise ValueError("unsupported synthetic scene state")
        blob = pack(state)
        if type(blob) is not bytes or len(blob) != EXPECTED_SCENE_BYTES:
            raise ValueError("invalid packed CPS-1 diagnostic frame")
        blobs.append(blob)
    output = pack_timeline(blobs, fps)
    return output, _inspect(output, fps=fps, frames=len(blobs))


def _safe_output(path):
    path = Path(path)
    if (not privacy.outside_repo(path) or path.exists() or path.is_symlink()
            or not path.parent.is_dir() or path.parent.is_symlink()
            or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError("diagnostic output requires an unused external path")
    return path


def _write_exclusive(path, data):
    path = _safe_output(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(data)
    except Exception:
        if fd is not None:
            os.close(fd)
        path.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True,
                        help="fresh private sequence.bin outside repository")
    parser.add_argument("--report", type=Path,
                        help="fresh optional aggregate-only private JSON receipt")
    parser.add_argument("--fps", type=int, default=2)
    args = parser.parse_args(argv)
    try:
        data, result = build(fps=args.fps)
        _write_exclusive(args.out, data)
    except (OSError, ValueError, KeyError, TypeError):
        result = {
            "schema": SCHEMA, "status": BLOCKED,
            "original_mame_gameplay_frame_captured": False,
            "switch_hardware_display_verified": False,
            "private_game_paths_or_assets_exported": False,
        }
    if args.report is not None:
        privacy.write_private_receipt(args.report, result)
    print(result["status"])
    return 0 if result["status"] == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
