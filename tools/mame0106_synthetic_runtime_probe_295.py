#!/usr/bin/env python3
"""Stage295 ROM-free synthetic driver probe against an actual MAME 0.106 binary.

Not a test of Cadillacs and Dinosaurs. The fixture is artificially generated
Z80 code, patched into a disposable Minivader driver build. No private game
files, original images, paths or input logs are printed or published.
"""
import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_BYTES = 256 * 1024
VERIFY = re.compile(
    r"romset\s+minivadr(?:\s+\[[^\]\r\n]*\])?\s+is\s+(?:good|best available)",
    re.IGNORECASE
)
TRACE_HEAD = "callback_index,first_port_reads,playback_words"


def _invoke(executable, argv, cwd, timeout=30):
    try:
        result = subprocess.run(
            [str(Path(executable).resolve()), *argv],
            cwd=str(cwd), stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            timeout=timeout, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, ""
    # Output could contain unrelated emulator messages: never print raw text.
    return result.returncode, result.stdout[:MAX_BYTES].decode(
        "utf-8", errors="replace")


def _check_trace(path, first_frame, count):
    path = Path(path)
    if not path.is_file() or not 40 <= path.stat().st_size <= MAX_BYTES:
        return False
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError):
        return False
    if len(lines) != count + 1 or lines[0] != TRACE_HEAD:
        return False
    prev = None
    for offset, row in enumerate(lines[1:]):
        bits = row.split(",")
        if len(bits) != 3 or any(not v.isdecimal() for v in bits):
            return False
        callback, port0, words = map(int, bits)
        if callback != first_frame + offset or words < port0:
            return False
        if prev is not None and (port0 < prev[0] or words < prev[1]):
            return False
        prev = (port0, words)
    return True


def _base_args(rom_root):
    return [
        "minivadr", "-rompath", str(Path(rom_root).resolve()),
        "-window", "-noddraw", "-nodirect3d", "-nothrottle",
        "-noautoframeskip", "-frameskip", "0",
        "-skip_gameinfo", "-frames_to_run", "48",
    ]


def _classify_mng_audit_error(error):
    """Map parser failures to a fixed, path-free diagnostic code."""
    message = str(error).lower()
    rules = (
        ("signature", "INVALID_SIGNATURE"),
        ("truncated", "TRUNCATED_STREAM"),
        ("chunk length or type", "INVALID_CHUNK"),
        ("crc mismatch", "CHUNK_CRC_MISMATCH"),
        ("dimensions differ", "DIMENSION_MISMATCH"),
        ("unexpected global chunk", "UNEXPECTED_GLOBAL_CHUNK"),
        ("nested png frame", "NESTED_FRAME"),
        ("too many frames", "FRAME_LIMIT"),
        ("fewer candidate frames", "FRAME_COUNT_TOO_LOW"),
        ("trailing bytes", "TRAILING_DATA"),
        ("incomplete frame", "INCOMPLETE_FRAME"),
        ("mhdr", "INVALID_MHDR"),
        ("mame mng must begin", "INVALID_MHDR"),
        ("corrupted png", "INVALID_EMBEDDED_PNG"),
        ("invalid png", "INVALID_EMBEDDED_PNG"),
        ("private regular file", "INVALID_PRIVATE_PATH"),
    )
    for fragment, code in rules:
        if fragment in message:
            return code
    return "UNCLASSIFIED_AUDIT_ERROR"


def probe(executable, rom_root):
    """Require real MAME to load fixture ROM; attempt gameplay if GUI allows.

    A graphics-less GitHub-hosted Windows runner may be unable to present a
    playable window. In that case report the blocking stage, never pass it
    off as successful MNG generation.
    """
    report = {
        "schema": "dino-stage295-real-mame-synthetic-z80-probe-v1",
        "synthetic_minivader_rom_verification": False,
        "synthetic_mame_recording_executed": False,
        "synthetic_mame_playback_executed": False,
        "synthetic_mng_and_counter_trace_observed": False,
        "synthetic_mng_audited_frames": 0,
        "synthetic_mng_audit_failure_code": None,
        "synthetic_trace_audited_rows": 0,
        "synthetic_replay_process_exit_zero": False,
        "synthetic_replay_mng_file_present": False,
        "synthetic_replay_trace_file_present": False,
        "synthetic_replay_trace_csv_rows": None,
        "synthetic_replay_trace_first_callback": None,
        "synthetic_replay_trace_last_callback": None,
        "status": "BLOCKED_TEST_NOT_RUN",
        "original_dino_rom_or_inp_used": False,
        "original_gameplay_verified": False,
        "wolfmame_binary_authenticity_verified": False,
        "exact_input_video_alignment_verified": False,
        "physical_nintendo_switch_tested": False,
    }
    with tempfile.TemporaryDirectory(prefix="stage295-synthetic-runtime-") as work:
        workspace = Path(work)
        (workspace / "inp").mkdir()
        (workspace / "cfg").mkdir()
        (workspace / "nvram").mkdir()
        (workspace / "hi").mkdir()
        (workspace / "diff").mkdir()
        code, output = _invoke(
            executable,
            ["-verifyroms", "minivadr", "-rompath", str(Path(rom_root).resolve())],
            workspace,
        )
        if code != 0 or not VERIFY.search(output):
            report["status"] = "BLOCKED_SYNTHETIC_ROM_LOADER"
            return report
        report["synthetic_minivader_rom_verification"] = True

        base = _base_args(rom_root)
        code, _ = _invoke(executable, base + ["-record", "test295"], workspace)
        recording = workspace / "inp" / "test295.inp"
        if code != 0 or not recording.is_file() or not 32 < recording.stat().st_size < MAX_BYTES:
            report["status"] = "BLOCKED_SYNTHETIC_RECORDING_WINDOW_OR_GUI"
            return report
        report["synthetic_mame_recording_executed"] = True

        # MAME playback is exercised only on the recording it created from
        # the artificial Minivader CPU; it is not the user's original INP.
        replay = base + [
            "-playback", "test295", "-mngwrite", "test295-replay",
            "-mngstartframe", "10", "-mngframes", "24", "-mngcounttrace",
        ]
        code, _ = _invoke(executable, replay, workspace)
        mng_path = workspace / "test295-replay.mng"
        trace_path = workspace / "stage290-mng-counts.csv"
        report["synthetic_replay_process_exit_zero"] = (code == 0)
        report["synthetic_replay_mng_file_present"] = mng_path.is_file()
        report["synthetic_replay_trace_file_present"] = trace_path.is_file()
        if trace_path.is_file() and trace_path.stat().st_size <= MAX_BYTES:
            try:
                rows = trace_path.read_text(encoding="ascii").splitlines()
                if rows and rows[0] == TRACE_HEAD and len(rows) > 1:
                    report["synthetic_replay_trace_csv_rows"] = len(rows) - 1
                    first = rows[1].split(",")
                    last = rows[-1].split(",")
                    if len(first) == len(last) == 3 and first[0].isdecimal() and last[0].isdecimal():
                        report["synthetic_replay_trace_first_callback"] = int(first[0])
                        report["synthetic_replay_trace_last_callback"] = int(last[0])
            except (OSError, UnicodeError):
                pass
        if code != 0:
            report["status"] = "BLOCKED_SYNTHETIC_PLAYBACK_PROCESS_EXIT"
            return report
        if not mng_path.is_file():
            report["status"] = "BLOCKED_SYNTHETIC_PLAYBACK_MNG_MISSING"
            return report
        if not trace_path.is_file():
            report["status"] = "BLOCKED_SYNTHETIC_PLAYBACK_TRACE_MISSING"
            return report
        if not _check_trace(trace_path, 10, 24):
            report["status"] = "BLOCKED_SYNTHETIC_PLAYBACK_TRACE_STRUCTURE"
            return report
        report["synthetic_mame_playback_executed"] = True
        try:
            try:
                from . import wolfmame0106_private_mng_audit as audit_tool
            except ImportError:
                import wolfmame0106_private_mng_audit as audit_tool
            audited = audit_tool.audit(mng_path, minimum_frames=2)
            count = audited["candidate_frame_count"]
        except (OSError, ValueError, KeyError) as exc:
            report["synthetic_mng_audit_failure_code"] = _classify_mng_audit_error(exc)
            report["status"] = "BLOCKED_SYNTHETIC_MNG_DECODING"
            return report
        if count != 24:
            report["status"] = "BLOCKED_SYNTHETIC_MNG_FRAME_COUNT"
            return report
        report["synthetic_mng_and_counter_trace_observed"] = True
        report["synthetic_mng_audited_frames"] = count
        report["synthetic_trace_audited_rows"] = 24
        report["status"] = "SYNTHETIC_MINIVADER_MAME_VIDEO_AND_INPUT_READ_CONFIRMED"
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator", type=Path, required=True)
    parser.add_argument("--rom-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    # Report only JSON status/booleans/numbers. Synthetic artifacts are all
    # discarded after probing, even if the emulator fails to create a window.
    report = probe(args.emulator, args.rom_root)
    out = args.out
    if out.exists() or out.is_symlink():
        raise ValueError("refusing to overwrite existing test-only report")
    out.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))
    # Stage295 requires ROM-loader verification, not a working GPU on a
    # possibly headless hosted Windows worker. The status must disclose a
    # blocked recording/playing path instead of falsely reporting success.
    return 0 if report["synthetic_minivader_rom_verification"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
