#!/usr/bin/env python3
"""Stage290: audit private same-process MAME input-read / movie-callback counts.

Counters are diagnostic only: they are not input bytes, proof of true gameplay,
INP/video causality, WolfMAME authenticity or original Switch parity.
"""
import argparse
import hashlib
import re
import statistics
from pathlib import Path

try:
    from . import wolfmame0106_private_binary_gate as gate
    from . import wolfmame0106_private_capture_receipt_pair as binding
    from . import wolfmame0106_private_mng_audit as mng
except ImportError:
    import wolfmame0106_private_binary_gate as gate
    import wolfmame0106_private_capture_receipt_pair as binding
    import wolfmame0106_private_mng_audit as mng

SCHEMA = "dino-private-mame0106-inprocess-count-trace-v1"
MAX_BYTES = 256 * 1024
HEADER = "callback_index,first_port_reads,playback_words"
COUNTER_ROW = re.compile(r"([0-9]+),([0-9]+),([0-9]+)\Z")
STATUS = "STRUCTURALLY_CONSISTENT_INPROCESS_COUNTS_UNAUTHENTICATED"


def _empty_report():
    return {
        "schema": SCHEMA,
        "status": "BLOCKED_COUNT_TRACE_NOT_AUDITED",
        "candidate_mng_and_private_receipt_bound": False,
        "counter_trace_bytes_bound_to_receipt": False,
        "audited_callback_rows": 0,
        "first_port_reads_advanced": False,
        "playback_words_advanced": False,
        "monotonic_counters": False,
        "candidate_callback_minus_port0_counter_median": None,
        "candidate_callback_minus_port0_counter_min": None,
        "candidate_callback_minus_port0_counter_max": None,
        "candidate_callback_minus_port0_counter_spread": None,
        "stage290_counters_same_emulator_process_claimed_not_independently_attested": True,
        "source_wolfmame_binary_provenance_verified": False,
        "original_inp_playback_independently_verified": False,
        "exact_input_video_alignment_verified": False,
        "original_gameplay_parity_verified": False,
        "physical_nintendo_switch_tested": False,
        "private_paths_game_pixels_input_bits_or_digests_in_receipt": False,
    }


def audit(mng_path, private_receipt, trace_path):
    """Verify the private trace/recording pair and emit aggregate-only counts."""
    receipt = binding._read_receipt(private_receipt)
    start = receipt.get("requested_start_frame")
    if type(start) is not int:
        raise ValueError("private capture receipt lacks start frame")
    expected_count = binding._validate_receipt(private_receipt, mng_path, start)
    if receipt.get("status") != "CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED":
        raise ValueError("candidate capture did not exit cleanly")
    if receipt.get("candidate_count_trace_retained_privately") is not True:
        raise ValueError("no privately retained same-process trace")
    nbytes = receipt.get("candidate_count_trace_byte_count")
    digest = receipt.get("candidate_count_trace_sha256")
    if (type(nbytes) is not int or not 50 <= nbytes <= MAX_BYTES
            or type(digest) is not str
            or binding.DIGEST_PATTERN.fullmatch(digest) is None):
        raise ValueError("invalid counter trace content binding")
    trace = Path(trace_path)
    if (not gate.outside_repo(trace) or not gate.is_regular(trace)
            or trace.stat().st_size != nbytes):
        raise ValueError("counter trace is missing, unsafe or unexpected size")
    raw = trace.read_bytes()
    if len(raw) != nbytes or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("private counter trace mismatches original capture receipt")
    # The candidate MNG audit checks actual frame count, PNG and MNG contents
    # rather than trusting unsigned receipt status alone.
    video = mng.audit(mng_path, minimum_frames=2)
    if video["candidate_frame_count"] != expected_count:
        raise ValueError("MNG count differs from capture receipt")

    try:
        txt = raw.decode("ascii")
    except UnicodeError as exc:
        raise ValueError("trace must contain ASCII counters only") from exc
    if "\r" in txt or not txt.endswith("\n"):
        raise ValueError("trace must use complete LF-delimited rows")
    lines = txt.splitlines()
    if len(lines) != expected_count + 1 or lines[0] != HEADER:
        raise ValueError("incorrect callback row count or header")
    first, words, offsets = [], [], []
    frames = receipt["recorded_input_records"]
    if type(frames) is not int or frames < 1:
        raise ValueError("invalid source input record count")
    for index, line in enumerate(lines[1:]):
        match = COUNTER_ROW.fullmatch(line)
        if match is None:
            raise ValueError("invalid candidate counter row")
        callback, port0, nwords = map(int, match.groups())
        if callback != start + index:
            raise ValueError("missing, repeated or misordered video callback")
        if port0 > frames or nwords < port0 or nwords > frames * 128:
            raise ValueError("impossible input word counter bounds")
        if first and (port0 < first[-1] or nwords < words[-1]):
            raise ValueError("non-monotonic input counters")
        first.append(port0)
        words.append(nwords)
        offsets.append(callback - port0)
    if first[-1] <= first[0] or words[-1] <= words[0]:
        raise ValueError("capture did not observe increasing INP read counters")
    result = _empty_report()
    result.update({
        "status": STATUS,
        "candidate_mng_and_private_receipt_bound": True,
        "counter_trace_bytes_bound_to_receipt": True,
        "audited_callback_rows": expected_count,
        "first_port_reads_advanced": True,
        "playback_words_advanced": True,
        "monotonic_counters": True,
        "candidate_callback_minus_port0_counter_median": statistics.median(offsets),
        "candidate_callback_minus_port0_counter_min": min(offsets),
        "candidate_callback_minus_port0_counter_max": max(offsets),
        "candidate_callback_minus_port0_counter_spread": max(offsets) - min(offsets),
    })
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mng", type=Path, required=True)
    parser.add_argument("--capture-receipt", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.mng, args.capture_receipt, args.trace)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        result = _empty_report()
        result["status"] = "BLOCKED_PRIVATE_INPROCESS_COUNTER_AUDIT"
    gate.write_private_receipt(args.out, result)
    print(result["status"])
    return 0 if result["status"] == STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
