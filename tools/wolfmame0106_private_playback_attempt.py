#!/usr/bin/env python3
"""Stage281: bounded PRIVATE attempt to launch a historical 0.106 INP replay.

No ROM, original input, screenshots, emulator raw output or private paths
are uploaded. A started/exited emulator is NOT proof of decoded game frames,
complete INP replay, frame sync, or faithful original gameplay.
"""
import argparse
import hashlib
import os
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

try:
    from . import wolfmame0106_private_binary_gate as gate
except ImportError:
    import wolfmame0106_private_binary_gate as gate

MAX_INP_BYTES = 128 * 1024 * 1024
MAX_WLF_BYTES = 1024 * 1024
GAME = "dino"
PLAYBACK_ARGUMENTS = ("dino", "-playback", "dino")
STATUS_SCHEMA = "dino-wolfmame0106-private-playback-attempt-v1"


def _empty_report():
    return {
        "schema": STATUS_SCHEMA,
        "status": "BLOCKED_UNCHECKED",
        "recorded_input_frames": None,
        "paired_original_input_structure_checked": False,
        "historical_0_106_help_gate_passed": False,
        "dino_rom_verification_gate_passed": False,
        "private_input_staging_bytes_equal": False,
        "historical_playback_basename_without_extension": True,
        "emulator_process_spawned": False,
        "process_exit_code": None,
        "process_terminated_at_time_limit": False,
        "original_emulator_frames_observed": 0,
        "original_gameplay_recording_played_to_end": False,
        "actual_inp_playback_verified": False,
        "input_video_alignment_verified": False,
        "original_gameplay_parity_verified": False,
        "physical_nintendo_switch_tested": False,
        "private_paths_original_data_or_game_frames_exported": False,
    }


def _digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as inp:
        for block in iter(lambda: inp.read(1024 * 1024), b""):
            h.update(block)
    return h.digest()


def _private_copy(source, destination, maximum):
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError("private input is not a regular file")
    if not 0 < source.stat().st_size <= maximum:
        raise ValueError("private input exceeds bounded staging size")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(destination, flags, 0o600)
    with os.fdopen(fd, "wb") as output, source.open("rb") as inp:
        shutil.copyfileobj(inp, output, 1024 * 1024)
    if destination.stat().st_size != source.stat().st_size:
        raise ValueError("private staging size mismatch")
    if _digest(source) != _digest(destination):
        raise ValueError("private staging bytes mismatch")


def _run_process(emulator, rom_dir, staged_root, seconds):
    """Launch with stdout/stderr discarded; terminate at the hard time limit.

    Historical 0.106 usually searches <cwd>/inp/dino.inp for '-playback dino'.
    Actual binary identity and playback behavior remain unverified.
    """
    cmd = [
        str(Path(emulator).resolve()),
        *PLAYBACK_ARGUMENTS,
        "-rompath", str(Path(rom_dir).resolve()),
    ]
    kwargs = {"cwd": str(staged_root), "stdin": subprocess.DEVNULL,
              "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name != "nt":
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except OSError:
        return False, None, False
    try:
        code = proc.wait(timeout=seconds)
        return True, code, False
    except subprocess.TimeoutExpired:
        try:
            if os.name != "nt":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except ProcessLookupError:
            pass
        proc.wait()
        return True, None, True


def attempt(emulator, rom_dir, inp, wlf, *, seconds=10,
            verifier=gate.inspect, runner=_run_process):
    if type(seconds) is not int or not 1 <= seconds <= 120:
        raise ValueError("invalid bounded playback observation window")
    report = _empty_report()
    prereq = verifier(emulator, rom_dir, inp, wlf)
    report["recorded_input_frames"] = prereq["input_record_count"]
    report["paired_original_input_structure_checked"] = True
    report["historical_0_106_help_gate_passed"] = prereq[
        "emulator_help_reports_mame_0_106"]
    report["dino_rom_verification_gate_passed"] = prereq[
        "dino_rom_verifyroms_passed"]
    if not prereq["dino_rom_verifyroms_passed"]:
        report["status"] = "BLOCKED_PRIVATE_0_106_ROM_PREREQUISITE"
        return report
    try:
        with tempfile.TemporaryDirectory(prefix="dino281-private-session-") as folder:
            staging = Path(folder)
            if not gate.outside_repo(staging):
                raise ValueError("staging must be outside public repository")
            inputs = staging / "inp"
            inputs.mkdir(mode=0o700)
            for name in ("cfg", "nvram", "diff", "hi"):
                (staging / name).mkdir(mode=0o700)
            _private_copy(inp, inputs / "dino.inp", MAX_INP_BYTES)
            _private_copy(wlf, inputs / "dino.wlf", MAX_WLF_BYTES)
            report["private_input_staging_bytes_equal"] = True
            started, code, timed_out = runner(
                emulator, rom_dir, staging, seconds)
            report["emulator_process_spawned"] = bool(started)
            report["process_exit_code"] = code if type(code) is int else None
            report["process_terminated_at_time_limit"] = bool(timed_out)
            if not started:
                report["status"] = "BLOCKED_PLAYBACK_PROCESS_SPAWN_FAILED"
            elif timed_out:
                report["status"] = "PLAYBACK_PROCESS_TIME_LIMIT_UNVERIFIED"
            elif code == 0:
                report["status"] = "PLAYBACK_PROCESS_EXIT_ZERO_UNVERIFIED"
            else:
                report["status"] = "PLAYBACK_PROCESS_EXIT_NONZERO_UNVERIFIED"
    except (OSError, ValueError):
        report["status"] = "BLOCKED_PRIVATE_STAGING_FAILED"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator", required=True, type=Path)
    parser.add_argument("--rom-dir", required=True, type=Path)
    parser.add_argument("--inp", required=True, type=Path)
    parser.add_argument("--wlf", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=10)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = attempt(args.emulator, args.rom_dir, args.inp, args.wlf,
                         seconds=args.seconds)
    except (OSError, ValueError, KeyError):
        report = _empty_report()
        report["status"] = "BLOCKED_INVALID_PRIVATE_RECORDING_OR_ENVIRONMENT"
    gate.write_private_receipt(args.out, report)
    print(report["status"])
    return 0 if report["emulator_process_spawned"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
