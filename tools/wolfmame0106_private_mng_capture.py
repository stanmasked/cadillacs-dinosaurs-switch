#!/usr/bin/env python3
"""Stage286: bounded, local-only historical MAME INP playback and windowed MNG capture.

A successful process and valid candidate MNG are not proof of genuine
WolfMAME provenance, complete INP playback, input/video alignment or parity.
Never run this against public CI or store ROM/INP/WLF/MNG in the repository.
"""
import argparse
import hashlib
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

try:
    from . import wolfmame0106_private_binary_gate as gate
    from . import wolfmame0106_private_mng_audit as mng
except ImportError:
    import wolfmame0106_private_binary_gate as gate
    import wolfmame0106_private_mng_audit as mng

MAX_INP_BYTES = 128 * 1024 * 1024
MAX_WLF_BYTES = 1024 * 1024
MAX_FRAMES = 3601
MAX_SECONDS = 1800
CAPTURE_BASENAME = "stage286"
REPORT_SCHEMA = "dino-wolfmame0106-private-windowed-mng-capture-v1"


def _empty_report(frames, start_frame=0):
    return {
        "schema": REPORT_SCHEMA,
        "status": "BLOCKED_NOT_RUN",
        "requested_game_frames": frames,
        "requested_start_frame": start_frame,
        "requested_end_frame_exclusive": start_frame + frames if type(start_frame) is int and type(frames) is int else None,
        "capture_window_within_recording": False,
        "capture_frame_count_matches_request": False,
        "capture_start_frame_verified": False,
        "recorded_input_records": None,
        "recording_wolfmame_family_0_106": False,
        "emulator_help_reports_mame_0_106": False,
        "dino_rom_verifyroms_passed": False,
        "private_input_staging_byte_identical": False,
        "emulator_process_spawned": False,
        "process_exit_code": None,
        "process_timed_out": False,
        "candidate_mng_found": False,
        "candidate_mng_integrity_verified": False,
        "candidate_video_frames": 0,
        # Private receipt only; never print or commit this content fingerprint.
        "capture_mng_sha256": None,
        "capture_mng_byte_count": None,
        "changed_adjacent_pixel_pairs": 0,
        "identical_adjacent_pixel_pairs": 0,
        "candidate_capture_retained_privately": False,
        "emulator_binary_provenance_verified": False,
        "actual_inp_playback_verified": False,
        "complete_original_recording_played": False,
        "input_video_alignment_verified": False,
        "original_gameplay_parity_verified": False,
        "physical_nintendo_switch_tested": False,
        "private_paths_or_raw_game_frames_exported_to_public_repo": False,
    }


def _private_copy(source, destination, maximum):
    source = Path(source)
    if source.is_symlink() or not source.is_file():
        raise ValueError("private input must be a regular file")
    size = source.stat().st_size
    if not 0 < size <= maximum:
        raise ValueError("private input exceeds staging budget")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(destination, flags, 0o600)
    with os.fdopen(fd, "wb") as output, source.open("rb") as inp:
        shutil.copyfileobj(inp, output, 1024 * 1024)
    if destination.stat().st_size != size:
        raise ValueError("private staging size mismatch")
    if _sha256(source) != _sha256(destination):
        raise ValueError("private staging content mismatch")


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.digest()


def _run(cmd, cwd, seconds):
    """Run without shell, network setup or captured logs; enforce hard timeout."""
    kwargs = {
        "cwd": str(cwd),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name != "nt":
        kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(cmd, **kwargs)
    except OSError:
        return False, None, False
    try:
        return True, proc.wait(timeout=seconds), False
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


def _retain_capture(source, destination):
    destination = Path(destination)
    if (not gate.outside_repo(destination) or destination.is_symlink()
            or not destination.parent.is_dir() or destination.exists()):
        raise ValueError("capture destination must be a new private path outside repository")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(destination, flags, 0o600)
    with os.fdopen(fd, "wb") as output, Path(source).open("rb") as inp:
        shutil.copyfileobj(inp, output, 1024 * 1024)
    if _sha256(source) != _sha256(destination):
        destination.unlink(missing_ok=True)
        raise ValueError("retained capture checksum mismatch")


def capture(emulator, rom_dir, inp, wlf, *, frames=121, start_frame=0, seconds=120,
            capture_out=None, verifier=gate.inspect, runner=_run,
            audit_fn=mng.audit):
    if type(frames) is not int or not 2 <= frames <= MAX_FRAMES:
        raise ValueError("requested frames outside allowed bound")
    if type(start_frame) is not int or not 0 <= start_frame <= 10000000:
        raise ValueError("capture start frame outside allowed bound")
    if type(seconds) is not int or not 1 <= seconds <= MAX_SECONDS:
        raise ValueError("timeout outside allowed bound")
    report = _empty_report(frames, start_frame)
    prerequisites = verifier(emulator, rom_dir, inp, wlf)
    report["recorded_input_records"] = prerequisites.get("input_record_count")
    report["recording_wolfmame_family_0_106"] = bool(
        prerequisites.get("recording_wolfmame_family_0_106"))
    report["emulator_help_reports_mame_0_106"] = bool(
        prerequisites.get("emulator_help_reports_mame_0_106"))
    report["dino_rom_verifyroms_passed"] = bool(
        prerequisites.get("dino_rom_verifyroms_passed"))
    if not all((report["recording_wolfmame_family_0_106"],
                report["emulator_help_reports_mame_0_106"],
                report["dino_rom_verifyroms_passed"])):
        report["status"] = "BLOCKED_PRIVATE_PLAYBACK_PREREQUISITE"
        return report

    recorded_frames = prerequisites.get("input_record_count")
    if (type(recorded_frames) is not int or recorded_frames <= 0
            or start_frame + frames > recorded_frames):
        report["status"] = "BLOCKED_CAPTURE_WINDOW_OUTSIDE_RECORDING"
        return report
    report["capture_window_within_recording"] = True

    try:
        with tempfile.TemporaryDirectory(prefix="dino286-private-capture-") as temp:
            work = Path(temp)
            if not gate.outside_repo(work):
                raise ValueError("staging must be outside repository")
            inp_dir = work / "inp"
            inp_dir.mkdir(mode=0o700)
            # Historical MAME 0.106 has no mng_directory option. Its
            # FILETYPE_MOVIE path defaults to the current working directory,
            # which is this isolated temporary workspace.
            for folder in ("cfg", "nvram", "diff", "hi"):
                (work / folder).mkdir(mode=0o700)
            _private_copy(inp, inp_dir / "dino.inp", MAX_INP_BYTES)
            _private_copy(wlf, inp_dir / "dino.wlf", MAX_WLF_BYTES)
            report["private_input_staging_byte_identical"] = True

            cmd = [
                str(Path(emulator).resolve()),
                "dino", "-playback", "dino",
                "-rompath", str(Path(rom_dir).resolve()),
                "-nothrottle",
                "-noautoframeskip", "-frameskip", "0",
                "-skip_gameinfo",
                "-frames_to_run", str(start_frame + frames),
                "-mngstartframe", str(start_frame),
                "-mngframes", str(frames),
                "-mngwrite", CAPTURE_BASENAME,
            ]
            spawned, exit_code, timed_out = runner(cmd, work, seconds)
            report["emulator_process_spawned"] = bool(spawned)
            report["process_exit_code"] = exit_code if type(exit_code) is int else None
            report["process_timed_out"] = bool(timed_out)
            if not spawned:
                report["status"] = "BLOCKED_PRIVATE_PROCESS_SPAWN_FAILED"
                return report

            # FILETYPE_MOVIE's path list is empty by default in the
            # historical Windows OSD, so the MNG is created in cwd; the
            # writer appends the .mng extension to the supplied basename.
            candidate = work / (CAPTURE_BASENAME + ".mng")
            if candidate.is_symlink() or not candidate.is_file():
                report["status"] = "CAPTURE_FILE_NOT_CREATED"
                return report
            report["candidate_mng_found"] = True
            result = audit_fn(candidate, minimum_frames=2)
            # A well-formed MNG is candidate evidence only. A custom audit
            # function must not be able to mark an unverified container valid.
            container_valid = (
                result.get("mng_signature_header_end_and_chunk_crcs_valid") is True
                and result.get("embedded_png_scanlines_and_chunk_crcs_valid") is True
            )
            if not container_valid:
                report["status"] = "CAPTURE_AUDIT_DID_NOT_CONFIRM_CONTAINER"
                return report
            frame_count = result["candidate_frame_count"]
            if type(frame_count) is not int or not 2 <= frame_count <= MAX_FRAMES:
                raise ValueError("invalid audited candidate frame count")
            report["candidate_mng_integrity_verified"] = True
            report["candidate_video_frames"] = frame_count
            report["changed_adjacent_pixel_pairs"] = result["changed_candidate_pairs"]
            report["identical_adjacent_pixel_pairs"] = result["identical_candidate_pairs"]
            report["capture_frame_count_matches_request"] = (
                result["candidate_frame_count"] == frames)
            if not report["capture_frame_count_matches_request"]:
                report["status"] = "CAPTURE_FRAME_COUNT_MISMATCH"
                return report

            # Bind the private candidate MNG to this receipt. The fingerprint
            # is written only to the caller's exclusive private JSON path.
            report["capture_mng_byte_count"] = candidate.stat().st_size
            report["capture_mng_sha256"] = _sha256(candidate).hex()

            if capture_out is not None:
                _retain_capture(candidate, capture_out)
                report["candidate_capture_retained_privately"] = True

            if not result.get("mng_signature_header_end_and_chunk_crcs_valid", False):
                report["status"] = "CAPTURE_AUDIT_DID_NOT_CONFIRM_CONTAINER"
            elif timed_out:
                report["status"] = "CANDIDATE_MNG_VALID_BUT_PROCESS_TIMED_OUT"
            elif exit_code != 0:
                report["status"] = "CANDIDATE_MNG_VALID_BUT_PROCESS_EXIT_NONZERO"
            else:
                report["status"] = "CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED"
    except (OSError, ValueError, KeyError):
        report["status"] = "BLOCKED_PRIVATE_STAGING_OR_CAPTURE_AUDIT_FAILED"
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator", required=True, type=Path)
    parser.add_argument("--rom-dir", required=True, type=Path)
    parser.add_argument("--inp", required=True, type=Path)
    parser.add_argument("--wlf", required=True, type=Path)
    parser.add_argument("--frames", type=int, default=121,
                        help="number of frames to retain in the MNG window")
    parser.add_argument("--start-frame", type=int, default=0,
                        help="zero-based candidate video-frame offset; not proof of INP alignment")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--capture-out", type=Path,
                        help="optional private retained MNG path, outside repository")
    parser.add_argument("--out", required=True, type=Path,
                        help="exclusive private JSON receipt path")
    args = parser.parse_args(argv)
    try:
        report = capture(args.emulator, args.rom_dir, args.inp, args.wlf,
                         frames=args.frames, start_frame=args.start_frame,
                         seconds=args.seconds, capture_out=args.capture_out)
    except (OSError, ValueError, KeyError):
        report = _empty_report(
            args.frames if type(args.frames) is int else 0,
            args.start_frame if type(args.start_frame) is int else 0)
        report["status"] = "BLOCKED_INVALID_PRIVATE_ENVIRONMENT"
    gate.write_private_receipt(args.out, report)
    print(report["status"])
    # A valid container alone is not a successful capture run: reject
    # truncated windows, nonzero emulator exits, and timeouts at the CLI.
    return 0 if (
        report["status"] == "CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED"
        and report["candidate_mng_integrity_verified"]
        and report["capture_frame_count_matches_request"]
        and report["process_exit_code"] == 0
        and not report["process_timed_out"]
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
