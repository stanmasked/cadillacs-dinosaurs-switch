#!/usr/bin/env python3
"""Stage289: conservative, private candidate INP-record / MNG-callback offset audit.

Requires two privately retained Stage286 MNGs/receipts, a matching local
INP/WLF pair and *manually selected* visual-response annotations. It verifies
input rising press edges and compares annotated offsets, but DOES NOT prove
the observed frames depict those controls or establish true synchronization.
Never publish the original INP/WLF, annotations, MNGs, or file digests.
"""
import argparse
import hashlib
import json
import statistics
from pathlib import Path

try:
    from . import wolfmame0106_private_binary_gate as gate
    from . import wolfmame0106_dino_input_reference as inp_ref
    from . import wolfmame0106_private_mng_capture as capture
    from . import wolfmame0106_private_capture_receipt_pair as binding
    from . import wolfmame0106_private_window_overlap as overlap
    from . import wolfmame0106_replay_preflight as preflight
except ImportError:
    import wolfmame0106_private_binary_gate as gate
    import wolfmame0106_dino_input_reference as inp_ref
    import wolfmame0106_private_mng_capture as capture
    import wolfmame0106_private_capture_receipt_pair as binding
    import wolfmame0106_private_window_overlap as overlap
    import wolfmame0106_replay_preflight as preflight

SCHEMA = "dino-private-mame0106-manual-offset-candidate-v1"
ANNOTATION_SCHEMA = "dino-private-mame0106-observed-response-anchors-v1"
MIN_ANCHORS = 3
MAX_ANCHORS = 24
MAX_OFFSET_ABS = 3600
MIN_EDGE_SEPARATION = 30
MAX_OFFSET_SPREAD = 2
SIGNALS = {
    f"{port}.{name}": (inp_ref.PORTS[port], bit)
    for port, defs in inp_ref.NAMES.items()
    for bit, name in defs.items()
}


def _private_digest(path, max_size):
    path = Path(path)
    if (not gate.outside_repo(path) or not gate.is_regular(path)
            or path.stat().st_size > max_size):
        raise ValueError("invalid private recording file")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_annotations(path):
    path = Path(path)
    if not gate.outside_repo(path) or not gate.is_regular(path):
        raise ValueError("annotations must be private ordinary file")
    data = preflight.read_json(path, 65536)
    if type(data) is not dict or set(data) != {"schema", "anchors"}:
        raise ValueError("invalid private annotation document")
    if data["schema"] != ANNOTATION_SCHEMA:
        raise ValueError("unsupported annotation schema")
    anchors = data["anchors"]
    if type(anchors) is not list or not MIN_ANCHORS <= len(anchors) <= MAX_ANCHORS:
        raise ValueError("incorrect number of manual annotations")
    clean = []
    for item in anchors:
        if (type(item) is not dict or set(item) !=
                {"signal", "input_record_index", "video_callback_index"}):
            raise ValueError("unsupported manual event fields")
        signal = item["signal"]
        i = item["input_record_index"]
        v = item["video_callback_index"]
        if (type(signal) is not str or signal not in SIGNALS
                or type(i) is not int or type(v) is not int
                or not 1 <= i <= 10_000_000
                or not 0 <= v <= 10_000_000 + 3601):
            raise ValueError("invalid signal or manual index")
        clean.append((signal, i, v))
    if len(set(clean)) != len(clean):
        raise ValueError("repeated manual annotation")
    return clean


def _press_edge_at(inp, frame, offset, bit):
    with Path(inp).open("rb") as handle:
        handle.seek(inp_ref.HEADER_BYTES + (frame - 1) * inp_ref.FRAME_BYTES)
        previous = handle.read(inp_ref.FRAME_BYTES)
        current = handle.read(inp_ref.FRAME_BYTES)
    if len(previous) != inp_ref.FRAME_BYTES or len(current) != inp_ref.FRAME_BYTES:
        raise ValueError("truncated input record at manual anchor")
    mask = 1 << bit
    return (previous[offset] & mask) != 0 and (current[offset] & mask) == 0


def _empty_report():
    return {
        "schema": SCHEMA,
        "status": "BLOCKED_NOT_CALIBRATED",
        "annotation_count": 0,
        "checked_input_press_edges": 0,
        "overlap_dynamic_and_receipted": False,
        "private_inp_wlf_bytes_match_capture_receipts": False,
        "offset_median_callback_minus_record": None,
        "offset_min_callback_minus_record": None,
        "offset_max_callback_minus_record": None,
        "offset_spread": None,
        "manual_visual_annotations_independently_verified": False,
        "input_record_to_video_callback_alignment_verified": False,
        "authentic_wolfmame_binary_verified": False,
        "actual_original_gameplay_parity_verified": False,
        "physical_nintendo_switch_tested": False,
        "raw_input_events_frames_paths_or_content_digests_exported": False,
    }


def calibrate(inp, wlf, annotations, first_mng, second_mng,
              first_receipt, second_receipt, *,
              minimum_overlap=overlap.MIN_OVERLAP):
    """Return aggregate-only hypothesis; never return individual annotation rows."""
    if not (gate.outside_repo(inp) and gate.outside_repo(wlf)):
        raise ValueError("original recordings cannot be in the public repository")
    frames, version, duration = gate.private_inputs(inp, wlf)
    if not (version.startswith("0.106 ") and 0 <= duration <= 20 * 3600):
        raise ValueError("unsupported recording")
    if (Path(inp).stat().st_size > capture.MAX_INP_BYTES
            or Path(wlf).stat().st_size > capture.MAX_WLF_BYTES):
        raise ValueError("recording exceeds private input budget")

    anchors = _load_annotations(annotations)
    # Receipts are ordinary unsigned data. Pair/byte checks avoid accidental
    # mixups but cannot authenticate the emulator, the game or visual labels.
    a = binding._read_receipt(first_receipt)
    b = binding._read_receipt(second_receipt)
    inp_hash = _private_digest(inp, capture.MAX_INP_BYTES)
    wlf_hash = _private_digest(wlf, capture.MAX_WLF_BYTES)
    for receipt in (a, b):
        if (receipt.get("private_inp_sha256") != inp_hash
                or receipt.get("private_wlf_sha256") != wlf_hash
                or type(receipt.get("recorded_input_records")) is not int
                or receipt["recorded_input_records"] != frames):
            raise ValueError("recording content does not match both capture receipts")
    linked = binding.compare_receipted(
        first_mng, second_mng, first_receipt, second_receipt,
        minimum_overlap=minimum_overlap)
    if linked["status"] != overlap.MATCH_DYNAMIC:
        raise ValueError("need exact dynamic candidate-video overlap")
    left = linked["overlap_start"]
    right = left + linked["overlap_frame_count"]
    if type(left) is not int or type(right) is not int:
        raise ValueError("invalid private callback overlap bounds")

    event_indices = [i for _, i, _ in anchors]
    if (len(set(event_indices)) != len(event_indices)
            or any(b - a < MIN_EDGE_SEPARATION
                   for a, b in zip(sorted(event_indices), sorted(event_indices)[1:]))):
        raise ValueError("manual anchors must be distinct widely spaced press events")

    offsets = []
    for signal, input_index, video_index in anchors:
        if not (input_index < frames and left <= video_index < right):
            raise ValueError("manual response lies outside input/overlap bounds")
        offset, bit = SIGNALS[signal]
        if not _press_edge_at(inp, input_index, offset, bit):
            raise ValueError("annotated input event is not a confirmed press edge")
        lag = video_index - input_index
        if abs(lag) > MAX_OFFSET_ABS:
            raise ValueError("manual callback/record distance is too large")
        offsets.append(lag)

    report = _empty_report()
    report["annotation_count"] = len(anchors)
    report["checked_input_press_edges"] = len(anchors)
    report["overlap_dynamic_and_receipted"] = True
    report["private_inp_wlf_bytes_match_capture_receipts"] = True
    report["offset_median_callback_minus_record"] = statistics.median(offsets)
    report["offset_min_callback_minus_record"] = min(offsets)
    report["offset_max_callback_minus_record"] = max(offsets)
    spread = max(offsets) - min(offsets)
    report["offset_spread"] = spread
    report["status"] = (
        "CONSISTENT_MANUALLY_ANNOTATED_OFFSET_HYPOTHESIS_ONLY"
        if spread <= MAX_OFFSET_SPREAD
        else "DISPERSED_MANUAL_OFFSETS_NOT_CALIBRATED")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inp", required=True, type=Path)
    parser.add_argument("--wlf", required=True, type=Path)
    parser.add_argument("--annotations", required=True, type=Path)
    parser.add_argument("--first-mng", required=True, type=Path)
    parser.add_argument("--second-mng", required=True, type=Path)
    parser.add_argument("--first-receipt", required=True, type=Path)
    parser.add_argument("--second-receipt", required=True, type=Path)
    parser.add_argument("--min-overlap", type=int, default=overlap.MIN_OVERLAP)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = calibrate(
            args.inp, args.wlf, args.annotations,
            args.first_mng, args.second_mng,
            args.first_receipt, args.second_receipt,
            minimum_overlap=args.min_overlap)
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        report = _empty_report()
        report["status"] = "BLOCKED_PRIVATE_MANUAL_OFFSET_AUDIT"
    gate.write_private_receipt(args.out, report)
    print(report["status"])
    return 0 if report["status"] == (
        "CONSISTENT_MANUALLY_ANNOTATED_OFFSET_HYPOTHESIS_ONLY") else 2


if __name__ == "__main__":
    raise SystemExit(main())
