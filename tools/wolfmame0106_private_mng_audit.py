#!/usr/bin/env python3
"""Stage284: private MAME 0.106 candidate MNG frame-integrity/continuity audit.

The historical MAME 0.106 src/png.c writer emits MNG Signature, MHDR,
ordinary PNG chunks (IHDR..IEND) per frame, and MEND.
This audits *candidate video data*, not emulator provenance, INP playback,
recording time alignment, game authenticity or Switch parity.
"""
import argparse
import hashlib
import os
import struct
import zlib
from pathlib import Path

try:
    from . import wolfmame0106_replay_preflight as png
    from . import wolfmame0106_private_visual_continuity as pixels
    from . import wolfmame0106_private_binary_gate as gate
except ImportError:
    import wolfmame0106_replay_preflight as png
    import wolfmame0106_private_visual_continuity as pixels
    import wolfmame0106_private_binary_gate as gate

MNG_SIGNATURE = b"\x8aMNG\r\n\x1a\n"
MAX_MNG_BYTES = 512 * 1024 * 1024
MAX_CHUNK_BYTES = 8 * 1024 * 1024
MAX_PNG_FRAME_BYTES = 40 * 1024 * 1024
MAX_FRAMES = 3601
REPORT_SCHEMA = "dino-private-mame0106-candidate-mng-audit-v1"


def _exact(handle, length, what):
    data = handle.read(length)
    if len(data) != length:
        raise ValueError("truncated " + what)
    return data


def _kind(kind):
    return len(kind) == 4 and all(
        65 <= x <= 90 or 97 <= x <= 122 for x in kind
    )


def _source(path):
    path = Path(path)
    if not gate.outside_repo(path) or path.is_symlink() or not path.is_file():
        raise ValueError("source MNG must be a private regular file")
    if not 8 <= path.stat().st_size <= MAX_MNG_BYTES:
        raise ValueError("candidate MNG file outside size budget")
    return path


def audit(path, minimum_frames=2, *, _private_frame_digests=None):
    """Audit candidate MNG. Optional digest sink is ephemeral and never in receipt."""
    if _private_frame_digests is not None and type(_private_frame_digests) is not list:
        raise ValueError("private frame digest sink must be a list")
    if type(minimum_frames) is not int or not 2 <= minimum_frames <= MAX_FRAMES:
        raise ValueError("invalid expected minimum frame count")
    source = _source(path)
    frames = 0
    identical_pairs = 0
    changed_pairs = 0
    first_change = None
    dimensions = None
    previous_rgba = None
    header = None
    frame = None
    ended = False
    with source.open("rb") as handle:
        if _exact(handle, 8, "MNG signature") != MNG_SIGNATURE:
            raise ValueError("invalid MNG signature")
        while not ended:
            chunk_len = struct.unpack(">I", _exact(handle, 4, "MNG chunk length"))[0]
            kind = _exact(handle, 4, "MNG chunk type")
            if chunk_len > MAX_CHUNK_BYTES or not _kind(kind):
                raise ValueError("invalid MNG chunk length or type")
            body = _exact(handle, chunk_len, "MNG chunk body")
            expected_crc = struct.unpack(">I", _exact(handle, 4, "MNG CRC"))[0]
            if zlib.crc32(kind + body) & 0xFFFFFFFF != expected_crc:
                raise ValueError("MNG chunk CRC mismatch")
            encoded_chunk = struct.pack(">I", chunk_len) + kind + body + struct.pack(">I", expected_crc)
            if header is None:
                if kind != b"MHDR" or chunk_len != 28:
                    raise ValueError("MAME MNG must begin with 28-byte MHDR")
                w, h, ticks, layers, hdr_frames, play_time, simplicity = struct.unpack(
                    ">7I", body
                )
                if not (1 <= w <= 4096 and 1 <= h <= 4096
                        and w * h <= pixels.PIXEL_LIMIT
                        and 1 <= ticks <= 1000 and
                        layers == 0 and hdr_frames == 0 and play_time == 0 and
                        simplicity == 0x41):
                    raise ValueError("invalid or non-MAME-0.106 MHDR")
                header = (w, h, ticks)
            elif kind == b"MEND":
                if chunk_len or frame is not None or frames == 0:
                    raise ValueError("incomplete frame or malformed MNG end")
                if handle.read(1):
                    raise ValueError("trailing bytes after MNG end")
                ended = True
            elif kind == b"IHDR":
                if frame is not None or frames == MAX_FRAMES:
                    raise ValueError("nested PNG frame or too many frames")
                frame = bytearray(png.PNG_SIG)
                frame.extend(encoded_chunk)
            elif frame is not None:
                if len(frame) + len(encoded_chunk) > MAX_PNG_FRAME_BYTES:
                    raise ValueError("PNG frame exceeds private audit budget")
                frame.extend(encoded_chunk)
                if kind == b"IEND":
                    raw_png = bytes(frame)
                    info = png.png_integrity(raw_png)
                    if (info["width"], info["height"]) != header[:2]:
                        raise ValueError("MNG/PNG image dimensions differ")
                    w, h, rgba = pixels.normalized_rgba(raw_png)
                    if dimensions is None:
                        dimensions = (w, h)
                    if previous_rgba is not None:
                        if rgba == previous_rgba:
                            identical_pairs += 1
                        else:
                            changed_pairs += 1
                            if first_change is None:
                                first_change = [frames - 1, frames]
                    if _private_frame_digests is not None:
                        _private_frame_digests.append(hashlib.sha256(rgba).digest())
                    previous_rgba = rgba
                    frames += 1
                    frame = None
            else:
                raise ValueError("unexpected global chunk in MAME 0.106 MNG")
        if frames < minimum_frames:
            raise ValueError("fewer candidate frames than requested minimum")
    return {
        "schema": REPORT_SCHEMA,
        "status": "STRUCTURALLY_VALID_CANDIDATE_MNG_UNAUTHENTICATED",
        "mng_signature_header_end_and_chunk_crcs_valid": True,
        "embedded_png_scanlines_and_chunk_crcs_valid": True,
        "candidate_frame_count": frames,
        "candidate_frame_width": header[0],
        "candidate_frame_height": header[1],
        "frame_pairs_compared": frames - 1,
        "changed_candidate_pairs": changed_pairs,
        "identical_candidate_pairs": identical_pairs,
        "first_changed_candidate_pair": first_change,
        "consistent_frame_dimensions": True,
        "mng_ticks_per_second": header[2],
        "exact_video_to_inp_frame_alignment_verified": False,
        "emulator_provenance_verified": False,
        "original_inp_playback_verified": False,
        "original_gameplay_parity_verified": False,
        "physical_switch_tested": False,
        "raw_pixels_or_private_paths_exported": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mng", type=Path, required=True, help="private candidate .mng")
    parser.add_argument("--minimum-frames", type=int, default=2)
    parser.add_argument("--out", type=Path, required=True, help="exclusive private JSON report")
    args = parser.parse_args(argv)
    report = audit(args.mng, args.minimum_frames)
    gate.write_private_receipt(args.out, report)
    print(report["status"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
