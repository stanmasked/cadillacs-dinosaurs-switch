#!/usr/bin/env python3
"""Stage297: real MAME 0.106 replay twice, compare overlap (SYNTHETIC only).

The test ROM is original artificial Z80 code for Minivader. Never use
original dino ROM, INP or WLF; never publish MNG, recording or trace bytes.
Results prove only cross-run consistency of two candidate synthetic replays.
"""
import argparse
import json
import tempfile
from pathlib import Path

try:
    from . import mame0106_synthetic_runtime_probe_295 as base
    from . import wolfmame0106_private_mng_audit as mng
except ImportError:
    import mame0106_synthetic_runtime_probe_295 as base
    import wolfmame0106_private_mng_audit as mng

SCHEMA = "dino-stage297-real-mame-synthetic-dual-replay-v1"
MATCH = "SYNTHETIC_REAL_MAME_DUAL_REPLAY_MATCH_UNAUTHENTICATED"
NO_MATCH = "SYNTHETIC_REAL_MAME_DUAL_REPLAY_DIVERGED"
STATIC = "SYNTHETIC_REAL_MAME_OVERLAP_STATIC_VIDEO"
FIRST_START = 10
SECOND_START = 18
FRAME_COUNT = 24
OVERLAP_COUNT = FIRST_START + FRAME_COUNT - SECOND_START
TRACE_NAME = "stage290-mng-counts.csv"


def _report():
    return {
        "schema": SCHEMA,
        "status": "BLOCKED_SYNTHETIC_DUAL_REPLAY_NOT_RUN",
        "synthetic_original_z80_rom_loader_verified": False,
        "synthetic_input_recorded_by_real_mame": False,
        "first_synthetic_replay_complete": False,
        "second_synthetic_replay_complete": False,
        "first_mng_decoded_frames": 0,
        "second_mng_decoded_frames": 0,
        "first_trace_rows": 0,
        "second_trace_rows": 0,
        "first_window_start": FIRST_START,
        "second_window_start": SECOND_START,
        "frames_per_window": FRAME_COUNT,
        "requested_overlap": OVERLAP_COUNT,
        "overlap_frames_compared": 0,
        "matching_normalized_pixel_frames": 0,
        "matching_port0_read_counts": 0,
        "matching_total_playback_word_counts": 0,
        "first_counter_mismatch_callback": None,
        "overlap_contains_dynamic_video": False,
        "overlap_counters_advance": False,
        "synthetic_media_or_input_bytes_exported": False,
        "real_dino_rom_or_inp_used": False,
        "wolfmame_provenance_verified": False,
        "exact_input_video_causality_verified": False,
        "arcade_original_gameplay_parity_verified": False,
        "physical_nintendo_switch_tested": False,
    }


def parse_trace(path, *, first_frame, count):
    """Read private synthetic numeric trace; never return original input bytes."""
    path = Path(path)
    if (path.is_symlink() or not path.is_file() or
            not 40 <= path.stat().st_size <= base.MAX_BYTES):
        raise ValueError("missing or unsafe synthetic count trace")
    try:
        raw = path.read_bytes()
        if b"\r" in raw or not raw.endswith(b"\n"):
            raise ValueError("non-canonical CSV record separator")
        rows = raw.decode("ascii").splitlines()
    except (OSError, UnicodeError) as err:
        raise ValueError("invalid synthetic CSV encoding") from err
    if len(rows) != count + 1 or rows[0] != base.TRACE_HEAD:
        raise ValueError("synthetic count trace has wrong header/length")
    out = []
    for i, line in enumerate(rows[1:]):
        fields = line.split(",")
        if len(fields) != 3 or any(not v.isdecimal() for v in fields):
            raise ValueError("malformed synthetic trace row")
        frame, first_read, words = map(int, fields)
        if (frame != first_frame + i or words < first_read or
                first_read > 10_000_000 or words > 100_000_000):
            raise ValueError("out of range synthetic callback/read counter")
        if out and (first_read < out[-1][0] or words < out[-1][1]):
            raise ValueError("synthetic counters went backwards")
        out.append((first_read, words))
    return out


def compare_windows(first_hashes, first_counts, second_hashes, second_counts,
                    *, first_start=FIRST_START, second_start=SECOND_START):
    """Compare equal absolute callback indices, never local zero-based positions."""
    if (type(first_start) is not int or type(second_start) is not int or
            first_start < 0 or second_start <= first_start):
        raise ValueError("invalid synthetic window ordering")
    if any(type(v) is not list or len(v) != FRAME_COUNT for v in
           (first_hashes, first_counts, second_hashes, second_counts)):
        raise ValueError("unexpected decoded candidate window frame count")
    if any(type(h) is not bytes or len(h) != 32 for h in first_hashes + second_hashes):
        raise ValueError("invalid private decoded pixel fingerprint")
    if any(type(v) is not tuple or len(v) != 2 or
           any(type(n) is not int or n < 0 for n in v)
           for v in first_counts + second_counts):
        raise ValueError("invalid private trace tuple")
    start = max(first_start, second_start)
    end = min(first_start + FRAME_COUNT, second_start + FRAME_COUNT)
    n = end - start
    if n < 16:
        raise ValueError("insufficient overlap for independent runs")
    ai = start - first_start
    bi = start - second_start
    ah, bh = first_hashes[ai:ai+n], second_hashes[bi:bi+n]
    ac, bc = first_counts[ai:ai+n], second_counts[bi:bi+n]
    if any(len(rows) != n for rows in (ah, bh, ac, bc)):
        raise ValueError("incomplete overlapping synthetic windows")
    matching_pixels = sum(a == b for a, b in zip(ah, bh))
    matching_port0 = sum(a[0] == b[0] for a, b in zip(ac, bc))
    matching_words = sum(a[1] == b[1] for a, b in zip(ac, bc))
    first_mismatch = next((start + i for i, (a, b) in
                           enumerate(zip(ac, bc)) if a != b), None)
    changing_video = any(a != b for a, b in zip(ah, ah[1:]))
    advancing_counters = any(a != b for a, b in zip(ac, ac[1:]))
    result = {
        "overlap_frames_compared": n,
        "matching_normalized_pixel_frames": matching_pixels,
        "matching_port0_read_counts": matching_port0,
        "matching_total_playback_word_counts": matching_words,
        "first_counter_mismatch_callback": first_mismatch,
        "overlap_contains_dynamic_video": changing_video,
        "overlap_counters_advance": advancing_counters,
    }
    if matching_pixels != n or matching_port0 != n or matching_words != n:
        result["status"] = NO_MATCH
    elif not changing_video or not advancing_counters:
        result["status"] = STATIC
    else:
        result["status"] = MATCH
    return result


def run_synthetic_dual_replay(executable, rom_root, *, invoke=base._invoke,
                              audit=mng.audit):
    """Actual MAME process launches, all synthetic artifacts ephemeral."""
    report = _report()
    with tempfile.TemporaryDirectory(prefix="stage297-synthetic-only-") as folder:
        cwd = Path(folder)
        for name in ("inp", "cfg", "nvram", "hi", "diff"):
            (cwd / name).mkdir()
        rc, verify_stdout = invoke(
            executable, ["-verifyroms", "minivadr",
                         "-rompath", str(Path(rom_root).resolve())], cwd)
        if rc != 0 or not base.VERIFY.search(verify_stdout):
            report["status"] = "BLOCKED_SYNTHETIC_ROM_VALIDATION"
            return report
        report["synthetic_original_z80_rom_loader_verified"] = True
        argv = base._base_args(rom_root)
        rc, _ = invoke(executable, argv + ["-record", "stage297"], cwd)
        recorded = cwd / "inp" / "stage297.inp"
        if (rc != 0 or recorded.is_symlink() or not recorded.is_file() or
                not 32 < recorded.stat().st_size < base.MAX_BYTES):
            report["status"] = "BLOCKED_SYNTHETIC_RECORDING"
            return report
        report["synthetic_input_recorded_by_real_mame"] = True

        history = []
        for ordinal, start in enumerate((FIRST_START, SECOND_START)):
            name = "stage297-first" if ordinal == 0 else "stage297-second"
            video = cwd / (name + ".mng")
            trace = cwd / TRACE_NAME
            # Remove the last completed trace rather than accidentally
            # accepting stale CSV if the second MAME process fails to write.
            if trace.is_symlink():
                report["status"] = "BLOCKED_SYNTHETIC_TRACE_SYMLINK"
                return report
            if trace.exists():
                trace.unlink()
            rc, _ = invoke(
                executable,
                argv + ["-playback", "stage297",
                        "-mngwrite", name,
                        "-mngstartframe", str(start),
                        "-mngframes", str(FRAME_COUNT),
                        "-mngcounttrace"], cwd)
            if rc != 0 or video.is_symlink() or not video.is_file() or not trace.is_file():
                report["status"] = ("BLOCKED_SYNTHETIC_FIRST_REPLAY"
                                    if ordinal == 0 else "BLOCKED_SYNTHETIC_SECOND_REPLAY")
                return report
            try:
                counters = parse_trace(trace, first_frame=start, count=FRAME_COUNT)
                digests = []
                metadata = audit(video, minimum_frames=FRAME_COUNT,
                                 _private_frame_digests=digests)
                if metadata["candidate_frame_count"] != FRAME_COUNT or len(digests) != FRAME_COUNT:
                    raise ValueError("synthetic MNG decoder frame-count mismatch")
            except (OSError, KeyError, ValueError, UnicodeError, TypeError):
                report["status"] = ("BLOCKED_SYNTHETIC_FIRST_MEDIA_AUDIT"
                                    if ordinal == 0 else "BLOCKED_SYNTHETIC_SECOND_MEDIA_AUDIT")
                return report
            history.append((digests, counters))
            tag = "first" if ordinal == 0 else "second"
            report[tag + "_synthetic_replay_complete"] = True
            report[tag + "_mng_decoded_frames"] = FRAME_COUNT
            report[tag + "_trace_rows"] = len(counters)
        try:
            result = compare_windows(
                history[0][0], history[0][1], history[1][0], history[1][1],
                first_start=FIRST_START, second_start=SECOND_START)
        except (ValueError, TypeError):
            report["status"] = "BLOCKED_SYNTHETIC_DUAL_COMPARISON"
            return report
        report.update(result)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator", type=Path, required=True)
    parser.add_argument("--rom-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_synthetic_dual_replay(args.emulator, args.rom_root)
    if args.out.exists() or args.out.is_symlink():
        raise ValueError("refusing to overwrite synthetic-only status file")
    # Only aggregate fields; the temporary traces, input files, MNGs,
    # and decoded image fingerprints are never printed or uploaded.
    args.out.write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == MATCH else 2


if __name__ == "__main__":
    raise SystemExit(main())
