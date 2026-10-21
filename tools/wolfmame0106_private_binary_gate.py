#!/usr/bin/env python3
"""Stage279: private, read-only WolfMAME 0.106 executable and dino ROM gate.

This never runs gameplay or -playback, reads ROM bytes, records screenshots,
or authenticates WolfMAME provenance. It prints only a minimal local status.
"""
import argparse
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path

try:
    from .wolfmame0106_dino_input_reference import metadata
except ImportError:  # direct invocation: python3 tools/wolfmame0106_private_binary_gate.py
    from wolfmame0106_dino_input_reference import metadata

ROOT = Path(__file__).resolve().parents[1]
MAX_OUTPUT = 131072
VERSION = re.compile(r"(?<![0-9])0\.106(?![0-9])", re.I)
WOLF = re.compile(r"wolf[\s-]*mame", re.I)
ROM_GOOD = re.compile(
    r"^romset\s+dino(?:\s+\[[^\]\r\n]*\])?\s+is\s+(?:good|best available)\s*$",
    re.I | re.M,
)


def outside_repo(path):
    resolved = Path(path).resolve()
    return resolved != ROOT and ROOT not in resolved.parents


def is_regular(path):
    path = Path(path)
    try:
        return not path.is_symlink() and path.is_file() and stat.S_ISREG(path.stat().st_mode)
    except OSError:
        return False


def binary_ok(path):
    return is_regular(path) and os.access(path, os.X_OK)


def private_inputs(inp, wlf):
    if not all(outside_repo(x) and is_regular(x) for x in (inp, wlf)):
        raise ValueError("original input files must be private, regular, non-symlink files")
    frames, version, duration = metadata(Path(inp), Path(wlf))
    return frames, version, duration


def bounded_probe(binary, argv, cwd, timeout):
    """Capture no more than MAX_OUTPUT plus one byte; never forward raw output."""
    try:
        with tempfile.TemporaryFile() as captured:
            with subprocess.Popen(
                [str(Path(binary).resolve()), *argv], cwd=cwd, stdin=subprocess.DEVNULL,
                stdout=captured, stderr=subprocess.STDOUT,
            ) as proc:
                try:
                    code = proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    return None, "", True
            if captured.tell() > MAX_OUTPUT:
                return code, "", False
            captured.seek(0)
            data = captured.read(MAX_OUTPUT + 1)
            return code, data.decode("utf-8", errors="replace"), False
    except OSError:
        return None, "", False


def inspect(emulator, rom_dir, inp, wlf, *, probe=bounded_probe):
    frames, version, _ = private_inputs(inp, wlf)
    report = {
        "schema": "dino-wolfmame0106-private-binary-gate-v1",
        "input_record_count": frames,
        "recording_wolfmame_family_0_106": version.startswith("0.106 "),
        "emulator_help_reports_wolfmame_0_106": False,
        "dino_rom_verifyroms_passed": False,
        "emulator_binary_provenance_verified": False,
        "actual_inp_playback_verified": False,
        "original_gameplay_frames_captured": False,
        "input_video_alignment_verified": False,
        "original_gameplay_parity_verified": False,
        "physical_switch_tested": False,
        "private_paths_or_recorded_button_stream_exported": False,
    }
    if not binary_ok(emulator):
        report["status"] = "BLOCKED_NO_EXECUTABLE_WOLFMAME"
        return report
    rom = Path(rom_dir)
    if rom.is_symlink() or not rom.is_dir() or not outside_repo(rom):
        report["status"] = "BLOCKED_NO_PRIVATE_ROM_DIRECTORY"
        return report
    with tempfile.TemporaryDirectory(prefix="dino279-gate-") as work:
        code, help_text, timeout = probe(emulator, ["-help"], work, 10)
        if timeout:
            report["status"] = "BLOCKED_EMULATOR_HELP_TIMEOUT"
            return report
        if code != 0 or not WOLF.search(help_text) or not VERSION.search(help_text):
            report["status"] = "BLOCKED_WOLFMAME_VERSION_NOT_CONFIRMED"
            return report
        report["emulator_help_reports_wolfmame_0_106"] = True
        code, verify_text, timeout = probe(
            emulator, ["-verifyroms", "dino", "-rompath", str(rom.resolve())],
            work, 45,
        )
        if timeout:
            report["status"] = "BLOCKED_ROM_VERIFICATION_TIMEOUT"
            return report
        if code != 0 or not ROM_GOOD.search(verify_text):
            report["status"] = "BLOCKED_ROM_VERIFICATION_FAILED"
            return report
        report["dino_rom_verifyroms_passed"] = True
        report["status"] = "READY_FOR_MANUAL_PRIVATE_INP_PLAYBACK_NOT_VERIFIED"
        return report


def write_private_receipt(path, report):
    path = Path(path)
    if not outside_repo(path) or path.parent.is_symlink() or not path.parent.is_dir():
        raise ValueError("receipt location must be an existing private directory")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)
        handle.write("\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator", required=True, type=Path)
    parser.add_argument("--rom-dir", required=True, type=Path)
    parser.add_argument("--inp", required=True, type=Path)
    parser.add_argument("--wlf", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    report = inspect(args.emulator, args.rom_dir, args.inp, args.wlf)
    write_private_receipt(args.out, report)
    print(report["status"])
    return 0 if report["dino_rom_verifyroms_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
