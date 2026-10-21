#!/usr/bin/env python3
"""Stage287: private overlap check of two MAME 0.106 candidate MNG windows.

Compares *normalized* decoded pixels at common requested callback indices.
Both MNG files remain private. This cannot authenticate independent playback,
WolfMAME provenance, INP/video time alignment or original game parity.
"""
import argparse
from pathlib import Path

try:
    from . import wolfmame0106_private_mng_audit as mng
    from . import wolfmame0106_private_binary_gate as gate
except ImportError:
    import wolfmame0106_private_mng_audit as mng
    import wolfmame0106_private_binary_gate as gate

SCHEMA = "dino-private-mame0106-window-overlap-v1"
MIN_OVERLAP = 16
MAX_START = 10_000_000
MATCH_DYNAMIC = "OVERLAP_MATCH_DYNAMIC_UNAUTHENTICATED"


def _empty_report(first_start, second_start):
    return {
        "schema": SCHEMA,
        "status": "BLOCKED_NOT_COMPARED",
        "first_requested_start": first_start,
        "second_requested_start": second_start,
        "first_candidate_frame_count": None,
        "second_candidate_frame_count": None,
        "overlap_start": None,
        "overlap_frame_count": 0,
        "matching_overlap_frames": 0,
        "mismatching_overlap_frames": 0,
        "first_mismatching_callback_index": None,
        "overlap_has_pixel_changes": False,
        "candidate_mng_integrity_verified": False,
        "candidate_layout_compatible": False,
        "two_independent_emulator_runs_verified": False,
        "original_inp_playback_verified": False,
        "exact_input_video_alignment_verified": False,
        "original_gameplay_parity_verified": False,
        "physical_nintendo_switch_tested": False,
        "raw_pixels_hashes_or_private_paths_exported": False,
    }


def compare(first_mng, second_mng, first_start, second_start, *,
            minimum_overlap=MIN_OVERLAP):
    """Compare requested offsets; never return frame bytes or digests."""
    for value in (first_start, second_start):
        if type(value) is not int or not 0 <= value <= MAX_START:
            raise ValueError("invalid candidate callback start index")
    if type(minimum_overlap) is not int or not 2 <= minimum_overlap <= mng.MAX_FRAMES:
        raise ValueError("invalid minimum overlap")
    first = Path(first_mng)
    second = Path(second_mng)
    # The MNG auditor separately rejects paths inside the repo and symlinks.
    if first.samefile(second):
        raise ValueError("comparison requires distinct candidate MNG files")

    first_digests, second_digests = [], []
    a = mng.audit(first, minimum_frames=2, _private_frame_digests=first_digests)
    b = mng.audit(second, minimum_frames=2, _private_frame_digests=second_digests)
    na, nb = a["candidate_frame_count"], b["candidate_frame_count"]
    if len(first_digests) != na or len(second_digests) != nb:
        raise ValueError("candidate frame digest/count inconsistency")
    report = _empty_report(first_start, second_start)
    report["candidate_mng_integrity_verified"] = True
    report["first_candidate_frame_count"] = na
    report["second_candidate_frame_count"] = nb

    layout = all((
        a["candidate_frame_width"] == b["candidate_frame_width"],
        a["candidate_frame_height"] == b["candidate_frame_height"],
        a["mng_ticks_per_second"] == b["mng_ticks_per_second"],
    ))
    if not layout:
        report["status"] = "INCOMPATIBLE_CANDIDATE_MNG_LAYOUT"
        return report
    report["candidate_layout_compatible"] = True

    common_start = max(first_start, second_start)
    common_end = min(first_start + na, second_start + nb)
    count = max(0, common_end - common_start)
    report["overlap_start"] = common_start if count else None
    report["overlap_frame_count"] = count
    if count < minimum_overlap:
        report["status"] = "INSUFFICIENT_REQUESTED_WINDOW_OVERLAP"
        return report

    left = first_digests[common_start - first_start:
                         common_start - first_start + count]
    right = second_digests[common_start - second_start:
                           common_start - second_start + count]
    match = sum(x == y for x, y in zip(left, right))
    report["matching_overlap_frames"] = match
    report["mismatching_overlap_frames"] = count - match
    for i, (x, y) in enumerate(zip(left, right)):
        if x != y:
            report["first_mismatching_callback_index"] = common_start + i
            break
    report["overlap_has_pixel_changes"] = any(
        x != y for x, y in zip(left, left[1:]))
    if match != count:
        report["status"] = "OVERLAP_PIXEL_MISMATCH_UNAUTHENTICATED"
    elif not report["overlap_has_pixel_changes"]:
        report["status"] = "OVERLAP_MATCH_STATIC_UNAUTHENTICATED"
    else:
        report["status"] = MATCH_DYNAMIC
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-mng", type=Path, required=True)
    parser.add_argument("--second-mng", type=Path, required=True)
    parser.add_argument("--first-start", type=int, required=True)
    parser.add_argument("--second-start", type=int, required=True)
    parser.add_argument("--min-overlap", type=int, default=MIN_OVERLAP)
    parser.add_argument("--out", type=Path, required=True,
                        help="new JSON receipt path outside the repository")
    args = parser.parse_args(argv)
    try:
        report = compare(args.first_mng, args.second_mng,
                         args.first_start, args.second_start,
                         minimum_overlap=args.min_overlap)
    except (OSError, ValueError, KeyError, TypeError):
        report = _empty_report(args.first_start, args.second_start)
        report["status"] = "BLOCKED_PRIVATE_OVERLAP_COMPARISON"
    gate.write_private_receipt(args.out, report)
    print(report["status"])
    return 0 if report["status"] == MATCH_DYNAMIC else 2


if __name__ == "__main__":
    raise SystemExit(main())
