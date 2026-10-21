#!/usr/bin/env python3
"""Stage306: exhaustively compare original CPS1 tile pens, actual C vs Python.

Requires the user's complete *private* source-hash-verified canonical
MAME 0.106 dino.zip and a local C compiler. No ROM/image/digest bytes,
private paths, sample indices or decoded pixels are printed/persisted.
This checks STATIC original tile encoding, NOT original MAME gameplay.
"""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from . import cps1_private_native_tile_parity as tiles
    from . import mame0106_private_dino_rom_canonicalize_299 as canonical
    from . import wolfmame0106_private_binary_gate as gate
except ImportError:
    import cps1_private_native_tile_parity as tiles
    import mame0106_private_dino_rom_canonicalize_299 as canonical
    import wolfmame0106_private_binary_gate as gate

SCHEMA = "dino-private-exhaustive-original-cps1-tile-decoding-v1"
MATCH = "PRIVATE_ORIGINAL_DINO_CPS1_STATIC_TILE_C_PY_EXHAUSTIVE_MATCH"
MISMATCH = "PRIVATE_DINO_STATIC_CPS1_TILE_C_PY_MISMATCH"
BLOCKED = "BLOCKED_PRIVATE_DINO_EXHAUSTIVE_GFX_SETUP"
EXPECTED_GFX_BYTES = 0x400000
SIZES = (8, 16, 32)


def _decode_python(gfx, side, code, half=0):
    """Independent direct CPS-1 4-bit-plane byte expansion."""
    if side not in SIZES or code < 0 or code >= len(gfx) // (
            64 if side == 8 else side * side // 2):
        raise ValueError("outside CPS-1 tile size and code bounds")
    if side == 8 and half not in (0, 32):
        raise ValueError("invalid CPS-1 eight-pixel half selector")
    if side != 8 and half != 0:
        raise ValueError("half selector valid only for 8x8")
    stride = 64 if side == 8 else side * side // 2
    row_bytes = 8 if side == 8 else side // 2
    offset = 4 if side == 8 and half == 32 else 0
    expected = bytearray(side * side)
    for y in range(side):
        base = code * stride + y * row_bytes + offset
        for cell in range(side // 8):
            i = base + 4 * cell
            p0, p1, p2, p3 = gfx[i:i+4]
            for x in range(8):
                bit = 7 - x
                expected[y*side + cell*8 + x] = (
                    ((p0 >> bit & 1) << 3) |
                    ((p1 >> bit & 1) << 2) |
                    ((p2 >> bit & 1) << 1) |
                    (p3 >> bit & 1))
    return bytes(expected)


def _compile_native(path):
    """Compile the actual portable C source used by the Switch project."""
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        ["gcc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-fPIC", "-shared", "-I" + str(root / "source"),
         str(root / "source" / "cps1_tile.c"), "-o", str(path)],
        check=True, capture_output=True, timeout=60,
        cwd=str(root),
    )


def _native_functions(library):
    funcs = {}
    byte_ptr = ctypes.POINTER(ctypes.c_uint8)
    for side in SIZES:
        func = getattr(library, "cps1_decode_tile" + str(side))
        func.argtypes = [
            byte_ptr, ctypes.c_size_t, ctypes.c_size_t,
            *([ctypes.c_uint] if side == 8 else []),
            byte_ptr,
        ]
        func.restype = ctypes.c_bool
        funcs[side] = func
    return funcs


def compare_graphics(gfx, library, *, reference=_decode_python):
    """All codes and both 8x8 halves; bounded aggregate-only evidence."""
    if (not isinstance(gfx, (bytes, bytearray))
            or not 512 <= len(gfx) <= EXPECTED_GFX_BYTES
            or len(gfx) % 512):
        raise ValueError("invalid sized original graphics region")
    cfunc = _native_functions(library)
    data = bytearray(gfx)
    ptr = (ctypes.c_uint8 * len(data)).from_buffer(data)
    outcomes = []
    for side in SIZES:
        n = len(data) // (64 if side == 8 else side * side // 2)
        count, bad, missing, values = 0, 0, 0, 0
        out = (ctypes.c_uint8 * (side * side))()
        for code in range(n):
            for half in ((0, 32) if side == 8 else (0,)):
                ok = (cfunc[side](ptr, len(data), code, half, out) if side == 8
                      else cfunc[side](ptr, len(data), code, out))
                if not ok:
                    missing += 1
                    continue
                got = bytes(out)
                wanted = reference(data, side, code, half)
                if (type(wanted) is not bytes or len(wanted) != side * side
                        or any(value > 15 for value in wanted)):
                    raise ValueError("invalid independent reference tile")
                if got != wanted:
                    bad += 1
                for pen in set(got):
                    if pen > 15:
                        raise ValueError("invalid original four-bit tile pen")
                    values |= 1 << pen
                count += 1
        expected_count = n * (2 if side == 8 else 1)
        outcomes.append({
            "tile_size": side,
            "compared_tiles": count,
            "compared_pen_indices": count * side * side,
            "mismatching_tiles": bad,
            "native_decode_failures": missing,
            "distinct_pen_values": values.bit_count(),
            "expected_tiles": expected_count,
        })
    passed = all(
        row["mismatching_tiles"] == 0 and row["native_decode_failures"] == 0
        and row["compared_tiles"] == row["expected_tiles"]
        and row["distinct_pen_values"] == 16 for row in outcomes)
    return {
        "schema": SCHEMA,
        "status": MATCH if passed else MISMATCH,
        "original_cps1_rom_source_crc32_sha1_verified": False,
        "original_gfx_region_bytes": len(data),
        "formats": outcomes,
        "all_8_16_32_tile_codes_and_8x8_halves_exhaustive": True,
        "total_compared_tiles": sum(x["compared_tiles"] for x in outcomes),
        "total_compared_pen_indices": sum(x["compared_pen_indices"] for x in outcomes),
        "mame_original_game_executed": False,
        "real_mame_frame_or_palette_observed": False,
        "original_inp_wlf_replay_verified": False,
        "nintendo_switch_hardware_frame_verified": False,
        "original_rom_or_derived_pixel_bytes_exported": False,
    }


def private_audit(rom, *, verify=canonical.verify_archive,
                  load=tiles.read_private_gfx, compiler=_compile_native):
    rom = canonical._private_regular(Path(rom), canonical.MAX_ZIP_BYTES)
    source = verify(rom, manifest=canonical.MANIFEST)
    if (type(source) is not dict or source.get("status") != canonical.MATCH
            or source.get("required_rom_members_matched_by_crc32_sha1")
            != len(canonical.MANIFEST)
            or source.get("required_payloads_crc_sha1_integrity_checked") is not True):
        raise ValueError("original MAME source ROM checksum gate failed")
    gfx = load(rom)
    if len(gfx) != EXPECTED_GFX_BYTES:
        raise ValueError("private canonical CPS-1 graphics region is incomplete")
    with tempfile.TemporaryDirectory(prefix="cps1-stage306-code-only-") as tmp:
        ext = ".dll" if os.name == "nt" else (".dylib" if sys.platform == "darwin" else ".so")
        library = Path(tmp) / ("native_tile" + ext)
        compiler(library)
        result = compare_graphics(gfx, ctypes.CDLL(str(library)))
    result["original_cps1_rom_source_crc32_sha1_verified"] = True
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = private_audit(args.rom)
    except Exception:
        # Never leak archive paths, checksum digests or original pixel data.
        result = {
            "schema": SCHEMA, "status": BLOCKED,
            "original_cps1_rom_source_crc32_sha1_verified": False,
            "mame_original_game_executed": False,
            "real_mame_frame_or_palette_observed": False,
            "original_inp_wlf_replay_verified": False,
            "nintendo_switch_hardware_frame_verified": False,
            "original_rom_or_derived_pixel_bytes_exported": False,
        }
    gate.write_private_receipt(args.out, result)
    print(result["status"])
    return 0 if result["status"] == MATCH else 2


if __name__ == "__main__":
    raise SystemExit(main())
