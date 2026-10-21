#!/usr/bin/env python3
"""Stage288: bind two private Stage286 MNG receipts to Stage287 pixel overlap.

This checks internally consistent local candidate evidence only. A receipt is
not a cryptographic attestation of the emulator, recording or gameplay.
Keep the source videos, original input, ROMs and receipts outside the repo.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

try:
    from . import wolfmame0106_private_binary_gate as gate
    from . import wolfmame0106_private_mng_capture as capture
    from . import wolfmame0106_private_mng_audit as mng
    from . import wolfmame0106_private_window_overlap as overlap
except ImportError:
    import wolfmame0106_private_binary_gate as gate
    import wolfmame0106_private_mng_capture as capture
    import wolfmame0106_private_mng_audit as mng
    import wolfmame0106_private_window_overlap as overlap

SCHEMA = "dino-private-mame0106-capture-receipt-overlap-v1"
MAX_RECEIPT_BYTES = 65536
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _read_receipt(path):
    path = Path(path)
    if (not gate.outside_repo(path) or path.is_symlink()
            or not gate.is_regular(path)):
        raise ValueError("receipt must be a private regular non-symlink file")
    if not 2 <= path.stat().st_size <= MAX_RECEIPT_BYTES:
        raise ValueError("private receipt exceeds size budget")
    with path.open("rb") as handle:
        data = handle.read(MAX_RECEIPT_BYTES + 1)
    if len(data) > MAX_RECEIPT_BYTES:
        raise ValueError("private receipt exceeds size budget")
    decoded = json.loads(data)
    if type(decoded) is not dict:
        raise ValueError("private capture receipt is not an object")
    return decoded


def _digest_file(path):
    source = Path(path)
    if (not gate.outside_repo(source) or source.is_symlink()
            or not gate.is_regular(source)):
        raise ValueError("candidate MNG must be a private regular non-symlink file")
    size = source.stat().st_size
    if not 8 <= size <= mng.MAX_MNG_BYTES:
        raise ValueError("candidate MNG outside file budget")
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return size, digest.hexdigest()


def _validate_receipt(receipt_path, candidate_path, expected_start):
    report = _read_receipt(receipt_path)
    if report.get("schema") != capture.REPORT_SCHEMA:
        raise ValueError("incompatible private capture receipt schema")
    if report.get("status") != "CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED":
        raise ValueError("capture did not finish with a clean candidate status")
    required_true = (
        "capture_window_within_recording",
        "capture_frame_count_matches_request",
        "candidate_mng_found",
        "candidate_mng_integrity_verified",
        "candidate_capture_retained_privately",
        "private_input_staging_byte_identical",
        "recording_wolfmame_family_0_106",
        "emulator_help_reports_mame_0_106",
        "dino_rom_verifyroms_passed",
        "emulator_process_spawned",
    )
    if any(report.get(key) is not True for key in required_true):
        raise ValueError("required private capture prerequisite is false")
    if report.get("process_timed_out") is not False or type(report.get("process_exit_code")) is not int or report["process_exit_code"] != 0:
        raise ValueError("capture did not have a clean emulator exit")
    start = report.get("requested_start_frame")
    count = report.get("requested_game_frames")
    total = report.get("recorded_input_records")
    end = report.get("requested_end_frame_exclusive")
    if (type(expected_start) is not int or type(start) is not int
            or type(count) is not int or type(total) is not int
            or type(end) is not int or not 0 <= start <= overlap.MAX_START
            or start != expected_start or not 2 <= count <= mng.MAX_FRAMES
            or total <= 0 or start + count > total or end != start + count
            or type(report.get("candidate_video_frames")) is not int
            or report["candidate_video_frames"] != count):
        raise ValueError("capture receipt frame-window inconsistency")
    digest = report.get("capture_mng_sha256")
    nbytes = report.get("capture_mng_byte_count")
    if (type(digest) is not str or DIGEST_PATTERN.fullmatch(digest) is None
            or type(nbytes) is not int or not 8 <= nbytes <= mng.MAX_MNG_BYTES):
        raise ValueError("capture receipt lacks a valid private content binding")
    size, actual_hash = _digest_file(candidate_path)
    if size != nbytes or actual_hash != digest:
        raise ValueError("private candidate MNG differs from its capture receipt")
    return count


def compare_receipted(first_mng, second_mng, first_receipt, second_receipt,
                      *, minimum_overlap=overlap.MIN_OVERLAP):
    """Verify private receipt/MNG pairs before and after pixel overlap audit."""
    if Path(first_mng).samefile(second_mng):
        raise ValueError("overlap comparison needs different candidate videos")
    if Path(first_receipt).samefile(second_receipt):
        raise ValueError("overlap comparison needs different private receipts")
    a = _read_receipt(first_receipt)
    b = _read_receipt(second_receipt)
    start_a = a.get("requested_start_frame")
    start_b = b.get("requested_start_frame")
    if type(start_a) is not int or type(start_b) is not int:
        raise ValueError("missing integer capture start index")
    frames_a = _validate_receipt(first_receipt, first_mng, start_a)
    frames_b = _validate_receipt(second_receipt, second_mng, start_b)
    result = overlap.compare(first_mng, second_mng, start_a, start_b,
                             minimum_overlap=minimum_overlap)
    # Recheck after decoding to detect a changed file during the audit.
    _validate_receipt(first_receipt, first_mng, start_a)
    _validate_receipt(second_receipt, second_mng, start_b)
    if (result["first_candidate_frame_count"] != frames_a or
            result["second_candidate_frame_count"] != frames_b):
        raise ValueError("audited MNG frame counts differ from capture receipts")
    result["schema"] = SCHEMA
    result["first_capture_receipt_validated_privately"] = True
    result["second_capture_receipt_validated_privately"] = True
    result["candidate_mng_bytes_bound_to_receipts"] = True
    # Never claim capture provenance, video/INP alignment or independent runs.
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-mng", type=Path, required=True)
    parser.add_argument("--second-mng", type=Path, required=True)
    parser.add_argument("--first-receipt", type=Path, required=True)
    parser.add_argument("--second-receipt", type=Path, required=True)
    parser.add_argument("--min-overlap", type=int, default=overlap.MIN_OVERLAP)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = compare_receipted(
            args.first_mng, args.second_mng, args.first_receipt,
            args.second_receipt, minimum_overlap=args.min_overlap)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        result = overlap._empty_report(None, None)
        result["schema"] = SCHEMA
        result["status"] = "BLOCKED_PRIVATE_CAPTURE_RECEIPT_LINKAGE"
        result["first_capture_receipt_validated_privately"] = False
        result["second_capture_receipt_validated_privately"] = False
        result["candidate_mng_bytes_bound_to_receipts"] = False
    gate.write_private_receipt(args.out, result)
    print(result["status"])
    return 0 if (
        result["status"] == overlap.MATCH_DYNAMIC
        and result.get("candidate_mng_bytes_bound_to_receipts") is True
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
