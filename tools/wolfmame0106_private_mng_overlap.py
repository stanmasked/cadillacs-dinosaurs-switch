#!/usr/bin/env python3
"""Stage287: private decoded-pixel overlap comparison of two candidate MNG windows.

Both files must remain outside the public repository. This tool cannot attest
independent emulator runs, original INP playback, video-to-input synchronization
or game parity. No frame digest, raw pixel, path or video is written to reports.
"""
import argparse
import os
from pathlib import Path

try:
    from . import wolfmame0106_private_mng_audit as mng
    from . import wolfmame0106_private_binary_gate as gate
except ImportError:
    import wolfmame0106_private_mng_audit as mng
    import wolfmame0106_private_binary_gate as gate

REPORT_SCHEMA = "dino-private-mame0106-candidate-mng-overlap-v1"
MAX_START_FRAME = 10000000
MATCH = "CANDIDATE_OVERLAP_PIXELS_EQUAL_UNAUTHENTICATED"
MISMATCH = "CANDIDATE_OVERLAP_PIXEL_MISMATCH"
STATIC = "STATIC_CANDIDATE_OVERLAP_INCONCLUSIVE"
BLOCKED = "BLOCKED_INVALID_CANDIDATE_OVERLAP"


def _empty_report(first_start, second_start):
    return {
        "schema": REPORT_SCHEMA,
        "status": BLOCKED,
        "first_requested_start_frame": first_start,
        "second_requested_start_frame": second_start,
        "first_candidate_frame_count": 0,
        "second_candidate_frame_count": 0,
        "both_candidate_mngs_valid": False,
        "candidate_formats_match": False,
        "overlap_start_candidate_frame": None,
        "overlap_end_candidate_frame_exclusive": None,
        "overlap_frame_count": 0,
        "matching_decoded_pixel_frames": 0,
        "mismatching_decoded_pixel_frames": 0,
        "first_mismatched_candidate_frame": None,
        "overlap_has_frame_to_frame_changes": False,
        "all_overlap_decoded_pixels_equal": False,
        "capture_from_independent_runs_verified": False,
        "emulator_binary_provenance_verified": False,
        "original_inp_playback_verified": False,
        "input_video_alignment_verified": False,
        "original_gameplay_parity_verified": False,
        "physical_nintendo_switch_tested": False,
        "raw_frames_paths_or_pixel_digests_exported": False,
    }


def compare(first, first_start, second, second_start):
    """Compare same-index candidate video frames; return aggregate-only report.

    The offsets are video callback positions, NOT authenticated input ticks.
    Require at least two shared positions; silent/static equality is inconclusive.
    """
    for start in (first_start, second_start):
        if type(start) is not int or not 0 <= start <= MAX_START_FRAME:
            raise ValueError("invalid candidate video-window offset")

    source_a, source_b = mng._source(first), mng._source(second)
    if os.path.samefile(source_a, source_b):
        raise ValueError("two distinct private candidate files are required")

    digests_a, digests_b = [], []
    audit_a = mng.audit(
        source_a, frame_sha256_sink=lambda index, digest: digests_a.append(digest))
    audit_b = mng.audit(
        source_b, frame_sha256_sink=lambda index, digest: digests_b.append(digest))

    report = _empty_report(first_start, second_start)
    report["both_candidate_mngs_valid"] = True
    count_a, count_b = audit_a["candidate_frame_count"], audit_b["candidate_frame_count"]
    if (len(digests_a) != count_a or len(digests_b) != count_b
            or count_a > mng.MAX_FRAMES or count_b > mng.MAX_FRAMES):
        raise ValueError("candidate frame digest enumeration mismatch")
    report["first_candidate_frame_count"] = count_a
    report["second_candidate_frame_count"] = count_b
    same_format = (
        audit_a["candidate_frame_dimensions"] == audit_b["candidate_frame_dimensions"]
        and audit_a["mng_ticks_per_second"] == audit_b["mng_ticks_per_second"]
    )
    report["candidate_formats_match"] = same_format
    if not same_format:
        return report

    start = max(first_start, second_start)
    end = min(first_start + count_a, second_start + count_b)
    if end - start < 2:
        return report
    report["overlap_start_candidate_frame"] = start
    report["overlap_end_candidate_frame_exclusive"] = end
    report["overlap_frame_count"] = end - start

    overlap_a = digests_a[start - first_start:end - first_start]
    overlap_b = digests_b[start - second_start:end - second_start]
    if len(overlap_a) != end - start or len(overlap_b) != end - start:
        raise ValueError("invalid candidate overlap indexing")
    changed_a = any(a != b for a, b in zip(overlap_a, overlap_a[1:]))
    changed_b = any(a != b for a, b in zip(overlap_b, overlap_b[1:]))
    report["overlap_has_frame_to_frame_changes"] = changed_a or changed_b
    mismatches = [i for i, (a, b) in enumerate(zip(overlap_a, overlap_b)) if a != b]
    report["mismatching_decoded_pixel_frames"] = len(mismatches)
    report["matching_decoded_pixel_frames"] = len(overlap_a) - len(mismatches)
    if mismatches:
        report["first_mismatched_candidate_frame"] = start + mismatches[0]
        report["status"] = MISMATCH
    elif not report["overlap_has_frame_to_frame_changes"]:
        report["all_overlap_decoded_pixels_equal"] = True
        report["status"] = STATIC
    else:
        report["all_overlap_decoded_pixels_equal"] = True
        report["status"] = MATCH
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first", type=Path, required=True,
                        help="private first candidate MNG")
    parser.add_argument("--first-start", type=int, required=True,
                        help="first candidate video callback index")
    parser.add_argument("--second", type=Path, required=True,
                        help="private second candidate MNG")
    parser.add_argument("--second-start", type=int, required=True,
                        help="second candidate video callback index")
    parser.add_argument("--out", type=Path, required=True,
                        help="new private-only exclusive JSON report")
    args = parser.parse_args(argv)
    try:
        report = compare(args.first, args.first_start, args.second, args.second_start)
    except (OSError, ValueError, KeyError, TypeError):
        report = _empty_report(args.first_start, args.second_start)
    gate.write_private_receipt(args.out, report)
    print(report["status"])
    return {MATCH: 0, STATIC: 4, MISMATCH: 3}.get(report["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
