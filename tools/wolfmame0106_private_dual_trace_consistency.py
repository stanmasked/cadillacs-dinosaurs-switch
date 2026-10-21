#!/usr/bin/env python3
"""Stage291: private cross-run check for overlapping MNG pixels and count traces.

Two unsigned local capture receipts and two traces are NOT independent
attestation of emulator provenance, INP replay or exact frame alignment.
Only aggregate, explicitly unauthenticated diagnostics leave this function.
"""
import argparse
import hashlib
from pathlib import Path

try:
    from . import wolfmame0106_private_binary_gate as gate
    from . import wolfmame0106_private_capture_receipt_pair as binding
    from . import wolfmame0106_private_count_trace as counts
    from . import wolfmame0106_private_window_overlap as overlap
except ImportError:
    import wolfmame0106_private_binary_gate as gate
    import wolfmame0106_private_capture_receipt_pair as binding
    import wolfmame0106_private_count_trace as counts
    import wolfmame0106_private_window_overlap as overlap

SCHEMA = "dino-private-mame0106-dual-capture-counter-overlap-v1"
MATCH = "PIXELS_AND_INPUT_READ_COUNTERS_MATCH_UNAUTHENTICATED"
MISMATCH = "PIXELS_MATCH_INPUT_READ_COUNTERS_DIVERGE_UNAUTHENTICATED"
STATIC = "PIXELS_MATCH_COUNTERS_STATIC_IN_OVERLAP_UNAUTHENTICATED"
NO_PIXELS = "BLOCKED_CANDIDATE_PIXEL_OVERLAP_NOT_DYNAMIC_MATCH"


def _empty_report():
    return {
        "schema": SCHEMA,
        "status": "BLOCKED_DUAL_CAPTURE_NOT_CHECKED",
        "first_candidate_mng_receipt_valid": False,
        "second_candidate_mng_receipt_valid": False,
        "first_candidate_counter_receipt_valid": False,
        "second_candidate_counter_receipt_valid": False,
        "same_private_inp_and_wlf_hashes": False,
        "dynamic_pixel_overlap_matching": False,
        "overlap_callback_frames": 0,
        "matching_port0_read_counts": 0,
        "mismatching_port0_read_counts": 0,
        "matching_total_playback_word_counts": 0,
        "mismatching_total_playback_word_counts": 0,
        "first_counter_mismatch_callback_index": None,
        "overlap_counter_values_change": False,
        "independent_emulator_executions_authenticated": False,
        "original_inp_playback_verified": False,
        "emulator_provenance_verified": False,
        "input_record_video_frame_alignment_verified": False,
        "original_gameplay_parity_verified": False,
        "physical_nintendo_switch_tested": False,
        "private_paths_video_pixels_input_bits_or_digests_in_report": False,
    }


def _trace_rows(trace_path, receipt):
    """Bound and revalidate a trace after the Stage290 audit."""
    path = Path(trace_path)
    size = receipt.get("candidate_count_trace_byte_count")
    digest = receipt.get("candidate_count_trace_sha256")
    count = receipt.get("candidate_video_frames")
    start = receipt.get("requested_start_frame")
    total_input = receipt.get("recorded_input_records")
    if (receipt.get("candidate_count_trace_retained_privately") is not True
            or type(size) is not int or not 50 <= size <= counts.MAX_BYTES
            or type(digest) is not str
            or binding.DIGEST_PATTERN.fullmatch(digest) is None
            or type(count) is not int or not 2 <= count <= 3601
            or type(start) is not int or start < 0
            or type(total_input) is not int or total_input <= 0):
        raise ValueError("invalid private counter receipt parameters")
    if not gate.outside_repo(path) or not gate.is_regular(path) or path.stat().st_size != size:
        raise ValueError("unsafe or missing private trace file")
    raw = path.read_bytes()
    if len(raw) != size or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("counter file no longer matches its private receipt")
    try:
        source = raw.decode("ascii")
    except UnicodeError as exc:
        raise ValueError("counter trace not ASCII") from exc
    if "\r" in source or not source.endswith("\n"):
        raise ValueError("counter trace not LF-delimited")
    lines = source.splitlines()
    if len(lines) != count + 1 or lines[0] != counts.HEADER:
        raise ValueError("counter trace header/length mismatch")
    output = []
    for i, row in enumerate(lines[1:]):
        m = counts.COUNTER_ROW.fullmatch(row)
        if not m:
            raise ValueError("malformed private counter row")
        callback, port0, words = map(int, m.groups())
        if callback != start + i or port0 > total_input or words < port0 or words > total_input * 128:
            raise ValueError("counter value or callback order invalid")
        if output and (port0 < output[-1][0] or words < output[-1][1]):
            raise ValueError("regressing private counter value")
        output.append((port0, words))
    if output[-1][0] <= output[0][0] or output[-1][1] <= output[0][1]:
        raise ValueError("counter trace never advanced")
    return output


def compare(first_mng, first_receipt, first_trace, second_mng, second_receipt,
            second_trace, *, minimum_overlap=overlap.MIN_OVERLAP):
    """Require private file linkage and compare same-index counter pairs."""
    first_mng = Path(first_mng)
    second_mng = Path(second_mng)
    first_receipt = Path(first_receipt)
    second_receipt = Path(second_receipt)
    first_trace = Path(first_trace)
    second_trace = Path(second_trace)
    if (first_mng.samefile(second_mng) or
            first_receipt.samefile(second_receipt) or
            first_trace.samefile(second_trace)):
        raise ValueError("each capture, receipt and counter trace must be distinct")

    a = binding._read_receipt(first_receipt)
    b = binding._read_receipt(second_receipt)
    if a.get("recorded_input_records") != b.get("recorded_input_records"):
        raise ValueError("source recording length differs")
    for key in ("private_inp_sha256", "private_wlf_sha256"):
        first_hash, second_hash = a.get(key), b.get(key)
        if (type(first_hash) is not str or
                binding.DIGEST_PATTERN.fullmatch(first_hash) is None or
                first_hash != second_hash):
            raise ValueError("private input and WLF hashes absent or unequal")

    ra = counts.audit(first_mng, first_receipt, first_trace)
    rb = counts.audit(second_mng, second_receipt, second_trace)
    if ra["status"] != counts.STATUS or rb["status"] != counts.STATUS:
        raise ValueError("counter trace prerequisites failed")

    video = binding.compare_receipted(first_mng, second_mng, first_receipt,
                                      second_receipt,
                                      minimum_overlap=minimum_overlap)
    output = _empty_report()
    output.update({
        "first_candidate_mng_receipt_valid": True,
        "second_candidate_mng_receipt_valid": True,
        "first_candidate_counter_receipt_valid": True,
        "second_candidate_counter_receipt_valid": True,
        "same_private_inp_and_wlf_hashes": True,
        "overlap_callback_frames": video["overlap_frame_count"],
    })
    if video["status"] != overlap.MATCH_DYNAMIC:
        output["status"] = NO_PIXELS
        return output

    left = video["overlap_start"]
    length = video["overlap_frame_count"]
    start_a = a["requested_start_frame"]
    start_b = b["requested_start_frame"]
    rows_a = _trace_rows(first_trace, a)
    rows_b = _trace_rows(second_trace, b)
    selected_a = rows_a[left - start_a:left - start_a + length]
    selected_b = rows_b[left - start_b:left - start_b + length]
    if len(selected_a) != length or len(selected_b) != length:
        raise ValueError("candidate callback overlap was truncated")

    # Verify after comparison that local MNG and counter bytes were not
    # swapped by an ordinary concurrent file update. Still not attestation.
    if counts.audit(first_mng, first_receipt, first_trace)["status"] != counts.STATUS:
        raise ValueError("first candidate changed during comparison")
    if counts.audit(second_mng, second_receipt, second_trace)["status"] != counts.STATUS:
        raise ValueError("second candidate changed during comparison")

    match_p = sum(x[0] == y[0] for x, y in zip(selected_a, selected_b))
    match_w = sum(x[1] == y[1] for x, y in zip(selected_a, selected_b))
    mismatch_at = next(
        (left + i for i, (x, y) in enumerate(zip(selected_a, selected_b))
         if x != y), None
    )
    changes = any(x != y for x, y in zip(selected_a, selected_a[1:]))
    output.update({
        "dynamic_pixel_overlap_matching": True,
        "matching_port0_read_counts": match_p,
        "mismatching_port0_read_counts": length - match_p,
        "matching_total_playback_word_counts": match_w,
        "mismatching_total_playback_word_counts": length - match_w,
        "first_counter_mismatch_callback_index": mismatch_at,
        "overlap_counter_values_change": changes,
    })
    if mismatch_at is not None:
        output["status"] = MISMATCH
    elif not changes:
        output["status"] = STATIC
    else:
        output["status"] = MATCH
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--first-mng", type=Path, required=True)
    parser.add_argument("--first-receipt", type=Path, required=True)
    parser.add_argument("--first-trace", type=Path, required=True)
    parser.add_argument("--second-mng", type=Path, required=True)
    parser.add_argument("--second-receipt", type=Path, required=True)
    parser.add_argument("--second-trace", type=Path, required=True)
    parser.add_argument("--min-overlap", type=int, default=overlap.MIN_OVERLAP)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = compare(
            args.first_mng, args.first_receipt, args.first_trace,
            args.second_mng, args.second_receipt, args.second_trace,
            minimum_overlap=args.min_overlap)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        report = _empty_report()
        report["status"] = "BLOCKED_PRIVATE_DUAL_CAPTURE_AUDIT"
    gate.write_private_receipt(args.out, report)
    print(report["status"])
    return 0 if report["status"] == MATCH else 2


if __name__ == "__main__":
    raise SystemExit(main())
