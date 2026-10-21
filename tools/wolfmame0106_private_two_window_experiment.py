#!/usr/bin/env python3
"""Stage292: single local-only two-window MAME 0.106 experiment coordinator.

Runs two requested captures sequentially, preserving all actual ROM/INP/WLF,
MNG, input-read traces and unhashed private receipts OFF the public repo.
A successful candidate experiment is NOT authentic WolfMAME/INP playback,
exact video/input synchronization or arcade/Switch parity verification.
"""
import argparse
from pathlib import Path

try:
    from . import wolfmame0106_private_binary_gate as gate
    from . import wolfmame0106_private_mng_capture as capture
    from . import wolfmame0106_private_dual_trace_consistency as dual
    from . import wolfmame0106_private_window_overlap as overlap
except ImportError:
    import wolfmame0106_private_binary_gate as gate
    import wolfmame0106_private_mng_capture as capture
    import wolfmame0106_private_dual_trace_consistency as dual
    import wolfmame0106_private_window_overlap as overlap

SCHEMA = "dino-private-mame0106-two-window-experiment-v1"
MATCH = "TWO_CAPTURE_PIXEL_AND_COUNT_CONSISTENCY_CANDIDATE_ONLY"
BLOCKED_FIRST = "BLOCKED_FIRST_PRIVATE_CAPTURE"
BLOCKED_SECOND = "BLOCKED_SECOND_PRIVATE_CAPTURE"
BLOCKED_COMPARE = "BLOCKED_PRIVATE_DUAL_COMPARISON"
NONMATCH = "TWO_CAPTURE_CANDIDATES_NOT_CONSISTENT"


def _empty_report(start, frames, shift):
    return {
        "schema": SCHEMA,
        "status": "BLOCKED_NOT_RUN",
        "requested_first_callback_start": start,
        "requested_second_callback_start": start + shift,
        "requested_frames_per_window": frames,
        "requested_overlap_frames": frames - shift,
        "first_capture_complete": False,
        "second_capture_complete": False,
        "cross_capture_evidence_checked": False,
        "overlap_callbacks_compared": 0,
        "overlap_port0_count_mismatches": None,
        "overlap_word_count_mismatches": None,
        "dual_check_status": None,
        "privately_retained_input_video_receipts": False,
        "independent_emulator_runs_authenticated": False,
        "original_inp_playback_verified": False,
        "wolfmame_binary_provenance_verified": False,
        "exact_input_record_to_video_callback_mapping_verified": False,
        "original_gameplay_parity_verified": False,
        "physical_nintendo_switch_tested": False,
        "private_paths_inputs_video_frames_counters_or_hashes_in_report": False,
    }


def _validate_config(start, frames, shift, seconds, total_input_frames):
    if (type(start) is not int or not 0 <= start <= overlap.MAX_START or
            type(frames) is not int or not 2 <= frames <= capture.MAX_FRAMES or
            type(shift) is not int or not overlap.MIN_OVERLAP <= shift < frames or
            frames - shift < overlap.MIN_OVERLAP or
            type(seconds) is not int or not 1 <= seconds <= capture.MAX_SECONDS or
            type(total_input_frames) is not int or total_input_frames < 1 or
            start + shift + frames > total_input_frames):
        raise ValueError("private capture windows invalid or outside recording")


def _private_fresh_directory(directory):
    """Atomically create a fresh private output directory, never replace files."""
    directory = Path(directory).absolute()
    parent = directory.parent
    if not gate.outside_repo(directory):
        raise ValueError("private outputs must stay outside the repository")
    if (directory.exists() or directory.is_symlink() or
            not parent.is_dir() or parent.is_symlink() or
            not gate.outside_repo(parent)):
        raise ValueError("output folder must be new and under a private directory")
    # Reject symlinks in the existing ancestor chain to limit redirection.
    if any(node.is_symlink() for node in (parent, *parent.parents)):
        raise ValueError("private output parent chain must not contain symlinks")
    directory.mkdir(mode=0o700, exist_ok=False)
    return directory


def _captured_clean(report, start, frames):
    return (
        type(report) is dict and
        report.get("status") == "CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED" and
        report.get("requested_start_frame") == start and
        report.get("requested_game_frames") == frames and
        report.get("candidate_video_frames") == frames and
        report.get("capture_frame_count_matches_request") is True and
        report.get("candidate_mng_integrity_verified") is True and
        report.get("candidate_capture_retained_privately") is True and
        report.get("candidate_count_trace_retained_privately") is True and
        report.get("private_input_staging_byte_identical") is True and
        report.get("process_timed_out") is False and
        type(report.get("process_exit_code")) is int and
        report["process_exit_code"] == 0
    )


def _dual_clean(verification):
    if type(verification) is not dict or verification.get("status") != dual.MATCH:
        return False
    n = verification.get("overlap_callback_frames")
    if type(n) is not int or n < overlap.MIN_OVERLAP:
        return False
    required = (
        "first_candidate_mng_receipt_valid",
        "second_candidate_mng_receipt_valid",
        "first_candidate_counter_receipt_valid",
        "second_candidate_counter_receipt_valid",
        "same_private_inp_and_wlf_hashes",
        "dynamic_pixel_overlap_matching",
        "overlap_counter_values_change",
    )
    if any(verification.get(k) is not True for k in required):
        return False
    for key in ("mismatching_port0_read_counts",
                "mismatching_total_playback_word_counts"):
        if type(verification.get(key)) is not int or verification[key] != 0:
            return False
    for key in ("matching_port0_read_counts",
                "matching_total_playback_word_counts"):
        if type(verification.get(key)) is not int or verification[key] != n:
            return False
    return True


def run_experiment(emulator, rom_dir, inp, wlf, output_dir, *,
                   first_start=36000, frames=1200, shift=600, seconds=1800,
                   metadata_fn=gate.private_inputs, capture_fn=capture.capture,
                   compare_fn=dual.compare):
    """Run two candidate captures and write only bounded private output files.

    On downstream failure, keep the first and/or second candidate files
    privately for diagnosis. Never retry the same private output directory.
    """
    first_start, frames, shift, seconds = (
        first_start, frames, shift, seconds)
    n, recording_version, _elapsed = metadata_fn(Path(inp), Path(wlf))
    if type(recording_version) is not str or not recording_version.startswith("0.106 "):
        raise ValueError("recording version incompatible with private experiment")
    _validate_config(first_start, frames, shift, seconds, n)
    output_dir = _private_fresh_directory(output_dir)
    result = _empty_report(first_start, frames, shift)

    left = (
        output_dir / "first.mng", output_dir / "first-counts.csv",
        output_dir / "first-receipt.json",
    )
    right = (
        output_dir / "second.mng", output_dir / "second-counts.csv",
        output_dir / "second-receipt.json",
    )
    try:
        for ordinal, files, start in (
                ("first", left, first_start),
                ("second", right, first_start + shift)):
            try:
                observed = capture_fn(
                    emulator, rom_dir, inp, wlf,
                    frames=frames, start_frame=start, seconds=seconds,
                    capture_out=files[0], trace_out=files[1])
            except (OSError, ValueError, KeyError, TypeError):
                observed = capture._empty_report(frames, start)
                observed["status"] = "BLOCKED_PRIVATE_CAPTURE_EXCEPTION"
            # Always retain private capture receipt even for blocked captures.
            gate.write_private_receipt(files[2], observed)
            if not _captured_clean(observed, start, frames):
                result["status"] = (
                    BLOCKED_FIRST if ordinal == "first" else BLOCKED_SECOND)
                break
            result[ordinal + "_capture_complete"] = True
        else:
            try:
                verified = compare_fn(
                    left[0], left[2], left[1],
                    right[0], right[2], right[1],
                    minimum_overlap=overlap.MIN_OVERLAP)
            except (OSError, ValueError, TypeError, KeyError, UnicodeError):
                result["status"] = BLOCKED_COMPARE
            else:
                # Do not copy arbitrary nested comparison fields into a
                # report: only known aggregate types and status values.
                result["cross_capture_evidence_checked"] = True
                status = verified.get("status") if type(verified) is dict else None
                if status in (dual.MATCH, dual.MISMATCH, dual.STATIC, dual.NO_PIXELS):
                    result["dual_check_status"] = status
                else:
                    result["status"] = BLOCKED_COMPARE
                if type(verified) is dict:
                    count = verified.get("overlap_callback_frames")
                    if type(count) is int and 0 <= count <= frames:
                        result["overlap_callbacks_compared"] = count
                    for key, destination in (
                        ("mismatching_port0_read_counts",
                         "overlap_port0_count_mismatches"),
                        ("mismatching_total_playback_word_counts",
                         "overlap_word_count_mismatches"),
                    ):
                        value = verified.get(key)
                        if (type(value) is int and
                                0 <= value <= result["overlap_callbacks_compared"]):
                            result[destination] = value
                if result["status"] != BLOCKED_COMPARE:
                    result["status"] = (
                        MATCH if (_dual_clean(verified) and
                                  result["overlap_callbacks_compared"] ==
                                  frames - shift)
                        else NONMATCH)
        result["privately_retained_input_video_receipts"] = (
            result["first_capture_complete"] and
            result["second_capture_complete"])
    finally:
        gate.write_private_receipt(output_dir / "stage292-summary.json", result)
    return result


def main(argv=None, *, experiment=run_experiment):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator", type=Path, required=True)
    parser.add_argument("--rom-dir", type=Path, required=True)
    parser.add_argument("--inp", type=Path, required=True)
    parser.add_argument("--wlf", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="new, never-used PRIVATE folder outside repository")
    parser.add_argument("--first-start", type=int, default=36000)
    parser.add_argument("--frames", type=int, default=1200)
    parser.add_argument("--shift", type=int, default=600)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args(argv)
    try:
        report = experiment(
            args.emulator, args.rom_dir, args.inp, args.wlf, args.out_dir,
            first_start=args.first_start, frames=args.frames,
            shift=args.shift, seconds=args.seconds)
        status = report["status"]
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        status = "BLOCKED_PRIVATE_EXPERIMENT_SETUP"
    print(status)
    return 0 if status == MATCH else 2


if __name__ == "__main__":
    raise SystemExit(main())
