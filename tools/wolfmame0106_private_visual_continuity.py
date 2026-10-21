#!/usr/bin/env python3
"""Stage280: ROM-free, private temporal consistency check for candidate PNG captures.

Normalizes PNG scanline filters and supported 8-bit pixel modes before
comparison. Does NOT attest emulator provenance, actual INP replay, or
input-to-video synchronization; different pixels alone prove none of these.
"""
import argparse
import json
import struct
import zlib
from pathlib import Path

try:
    from . import wolfmame0106_replay_preflight as pre
    from . import wolfmame0106_private_binary_gate as gate
except ImportError:
    import wolfmame0106_replay_preflight as pre
    import wolfmame0106_private_binary_gate as gate

PIXEL_LIMIT = 4_000_000


def _paeth(a, b, c):
    p = a + b - c
    da, db, dc = abs(p - a), abs(p - b), abs(p - c)
    if da <= db and da <= dc:
        return a
    return b if db <= dc else c


def normalized_rgba(raw):
    """Decode tested PNG bytes into uncomposited RGBA8, not screen evidence."""
    info = pre.png_integrity(raw)
    w, h, kind = info["width"], info["height"], info["png_color_type"]
    if w * h > PIXEL_LIMIT:
        raise ValueError("capture exceeds Stage280 pixel budget")
    chunks, pos = [], 8
    while pos < len(raw):
        n = struct.unpack(">I", raw[pos:pos + 4])[0]
        tag = raw[pos + 4:pos + 8]
        data = raw[pos + 8:pos + 8 + n]
        chunks.append((tag, data))
        pos += 12 + n
    if any(tag == b"tRNS" for tag, _ in chunks):
        raise ValueError("tRNS alpha not supported by visual comparator")
    palette = next((data for tag, data in chunks if tag == b"PLTE"), b"")
    compressed = b"".join(data for tag, data in chunks if tag == b"IDAT")
    decoded = zlib.decompress(compressed)  # pre.png_integrity bounded and checked it
    bpp = pre.PNG_CHANNELS[kind]
    stride = w * bpp
    previous = bytearray(stride)
    result = bytearray()
    offset = 0
    for _ in range(h):
        filt = decoded[offset]
        offset += 1
        row = bytearray(decoded[offset:offset + stride])
        offset += stride
        for x in range(stride):
            left = row[x - bpp] if x >= bpp else 0
            above = previous[x]
            upper_left = previous[x - bpp] if x >= bpp else 0
            if filt == 1:
                predictor = left
            elif filt == 2:
                predictor = above
            elif filt == 3:
                predictor = (left + above) // 2
            elif filt == 4:
                predictor = _paeth(left, above, upper_left)
            else:
                predictor = 0
            row[x] = (row[x] + predictor) & 255
        if kind == 6:
            result.extend(row)
        elif kind == 2:
            for x in range(0, stride, 3):
                result.extend((row[x], row[x + 1], row[x + 2], 255))
        elif kind == 0:
            for v in row:
                result.extend((v, v, v, 255))
        elif kind == 4:
            for x in range(0, stride, 2):
                result.extend((row[x], row[x], row[x], row[x + 1]))
        elif kind == 3:
            for index in row:
                i = 3 * index
                if i + 2 >= len(palette):
                    raise ValueError("palette entry out of range")
                result.extend((palette[i], palette[i + 1], palette[i + 2], 255))
        previous = row
    return w, h, bytes(result)


def validate_request(request):
    if type(request) is not dict or request.get("schema") != pre.REQUEST_SCHEMA:
        raise ValueError("not a Stage272 private capture request")
    if request.get("status") != "CAPTURE_REQUEST_NOT_CAPTURED":
        raise ValueError("unexpected capture provenance claim")
    n = request.get("recorded_input_frames")
    indices = request.get("frame_indices")
    names = request.get("image_names")
    if (type(n) is not int or not 1 <= n <= 10_000_000 or
        type(indices) is not list or not 2 <= len(indices) <= 2000 or
        type(names) is not list or len(names) != len(indices) or
        request.get("expected_capture_count") != len(indices) or
        any(type(x) is not int or x < 0 or x >= n for x in indices) or
        indices != sorted(set(indices)) or
        names != [f"frame-{x:08d}.png" for x in indices]):
        raise ValueError("inconsistent ordered capture indices or names")
    return indices


def audit(request, folder):
    indices = validate_request(request)
    folder = Path(folder)
    if not gate.outside_repo(folder) or folder.is_symlink():
        raise ValueError("captures must be in a private non-symlink directory")
    # Stage272 audits the exact file set, CRCs, compressed stream and scanlines.
    pre.audit_captures(request, folder)
    pairs = 0
    changed_pairs = 0
    changed_pixels = 0
    compared_pixels = 0
    first_changed_pair = None
    dimensions = None
    prev_frame, prev_rgba = None, None
    for index, filename in zip(indices, request["image_names"]):
        raw = pre.ordinary_file(folder / filename, 40 * 1024 * 1024)
        w, h, rgba = normalized_rgba(raw)
        if dimensions is None:
            dimensions = (w, h)
        elif dimensions != (w, h):
            raise ValueError("capture resolutions differ")
        if prev_frame is not None and index == prev_frame + 1:
            pairs += 1
            delta = sum(
                rgba[i:i + 4] != prev_rgba[i:i + 4]
                for i in range(0, len(rgba), 4)
            )
            changed_pixels += delta
            compared_pixels += w * h
            if delta:
                changed_pairs += 1
                if first_changed_pair is None:
                    first_changed_pair = [prev_frame, index]
        prev_frame, prev_rgba = index, rgba
    status = ("NO_ADJACENT_PAIRS_TO_COMPARE" if pairs == 0 else
              "PIXEL_CHANGES_OBSERVED_UNAUTHENTICATED" if changed_pairs else
              "ADJACENT_PIXELS_IDENTICAL_UNAUTHENTICATED")
    return {
        "schema": "dino-private-wolfmame-candidate-png-temporal-audit-v1",
        "status": status,
        "requested_capture_count": len(indices),
        "adjacent_frame_pairs_compared": pairs,
        "changed_pairs": changed_pairs,
        "unchanged_pairs": pairs - changed_pairs,
        "changed_pixel_fraction_across_pairs": (
            round(changed_pixels / compared_pixels, 8) if compared_pixels else None
        ),
        "first_changed_candidate_pair": first_changed_pair,
        "consistent_dimensions": True,
        "crc_and_scanlines_validated": True,
        "emulator_provenance_verified": False,
        "actual_inp_playback_verified": False,
        "input_video_alignment_verified": False,
        "original_gameplay_parity_verified": False,
        "physical_switch_tested": False,
        "raw_pngs_or_private_paths_in_report": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--captures", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not gate.outside_repo(args.request) or args.request.is_symlink():
        raise ValueError("capture request must be private and non-symlink")
    request = pre.read_json(args.request, 200_000)
    report = audit(request, args.captures)
    gate.write_private_receipt(args.out, report)
    print(report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
