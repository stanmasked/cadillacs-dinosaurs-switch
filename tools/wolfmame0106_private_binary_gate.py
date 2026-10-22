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
import signal
import selectors
import subprocess
import tempfile
import time
from pathlib import Path

try:
    from .wolfmame0106_dino_input_reference import metadata
except ImportError:  # direct invocation: python3 tools/wolfmame0106_private_binary_gate.py
    from wolfmame0106_dino_input_reference import metadata

ROOT = Path(__file__).resolve().parents[1]
MAX_OUTPUT = 131072
VERSION = re.compile(r"(?<![0-9])0\.106(?![0-9])", re.I)
MAME = re.compile(r"(?<![a-z])(?:wolf[\s-]*)?(?:mame|m\.a\.m\.e\.)(?![a-z])", re.I)
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


def _terminate_probe_group(proc):
    """Stop a timed-out or short-lived emulator probe and its child processes."""
    try:
        os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        if proc.poll() is None:
            proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        return False
    return proc.poll() is not None


def bounded_probe(binary, argv, cwd, timeout):
    """Stream output under a strict memory cap and never leave probe children running."""
    try:
        timeout_value=float(timeout)
    except (TypeError,ValueError):
        return None,"",False
    deadline=time.monotonic()+max(0.0,timeout_value)
    try:
        proc = subprocess.Popen(
            [str(Path(binary).resolve()), *argv], cwd=cwd,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, start_new_session=True, bufsize=0,
        )
    except OSError:
        return None,"",False
    output=bytearray()
    overflow=False
    timed_out=False
    read_error=False
    code=None
    selector=None
    cleanup_ok=False
    try:
        try:
            selector=selectors.DefaultSelector()
            selector.register(proc.stdout,selectors.EVENT_READ)
            while selector.get_map():
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    timed_out=True
                    break
                events=selector.select(min(remaining,0.1))
                if not events:
                    if proc.poll() is not None:
                        break
                    if time.monotonic()>=deadline:
                        timed_out=True
                        break
                    continue
                for key,_ in events:
                    try:
                        chunk=os.read(key.fd,65536)
                    except OSError:
                        read_error=True
                        break
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if not overflow:
                        capacity=MAX_OUTPUT+1-len(output)
                        if capacity>0:
                            output.extend(chunk[:capacity])
                        if len(output)>MAX_OUTPUT:
                            overflow=True
                if read_error:
                    break
            if not timed_out and not read_error:
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    timed_out=True
                else:
                    try:
                        code=proc.wait(timeout=remaining)
                    except subprocess.TimeoutExpired:
                        timed_out=True
        except (OSError,ValueError):
            read_error=True
    finally:
        if selector is not None:
            selector.close()
        cleanup_ok=_terminate_probe_group(proc)
        if proc.stdout is not None:
            proc.stdout.close()
    if timed_out or not cleanup_ok:
        return None,"",True
    if read_error or code is None:
        return None,"",False
    if overflow:
        return code,"",False
    return code,output.decode("utf-8",errors="replace"),False

def inspect(emulator, rom_dir, inp, wlf, *, probe=bounded_probe):
    frames, version, _ = private_inputs(inp, wlf)
    report = {
        "schema": "dino-wolfmame0106-private-binary-gate-v1",
        "input_record_count": frames,
        "recording_wolfmame_family_0_106": version.startswith("0.106 "),
        "emulator_help_reports_mame_0_106": False,
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
        if code != 0 or not MAME.search(help_text) or not VERSION.search(help_text):
            report["status"] = "BLOCKED_WOLFMAME_VERSION_NOT_CONFIRMED"
            return report
        report["emulator_help_reports_mame_0_106"] = True
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
