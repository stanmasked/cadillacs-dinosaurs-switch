#!/usr/bin/env python3
"""Stage300: verify private original dino ROM in real MAME 0.106, optionally boot.

This is a LOCAL-ONLY tool; never upload ROM, MNG, child-process output,
private hashes, or screenshots to public GitHub/CI. Accepted ROM bytes
and a decoded MNG are *candidate* evidence, NOT original INP playback,
WolfMAME provenance or physical Nintendo Switch parity.
"""
import argparse
from pathlib import Path
import tempfile

try:
    from . import wolfmame0106_private_binary_gate as gate
    from . import wolfmame0106_private_runtime_bundle_gate as bundle_gate
    from . import wolfmame0106_private_mng_capture as capture
    from . import wolfmame0106_private_mng_audit as mng
    from . import mame0106_private_dino_rom_canonicalize_299 as canonical
except ImportError:
    import wolfmame0106_private_binary_gate as gate
    import wolfmame0106_private_runtime_bundle_gate as bundle_gate
    import wolfmame0106_private_mng_capture as capture
    import wolfmame0106_private_mng_audit as mng
    import mame0106_private_dino_rom_canonicalize_299 as canonical

SCHEMA = "dino-private-real-mame0106-rom-loader-and-boot-probe-v1"
ROM_ACCEPTED = "REAL_MAME_DINO_ROM_LOADER_ACCEPTED_GAMEPLAY_NOT_VERIFIED"
BOOT_CANDIDATE = "CANDIDATE_REAL_DINO_MNG_BOOT_VALID_UNAUTHENTICATED"
MAX_FRAMES = 1200
MAX_SECONDS = 1800


def _empty():
    return {
        "schema": SCHEMA,
        "status": "BLOCKED_DINO_PROBE_NOT_RUN",
        "historical_dino_rom_members_hash_matched": 0,
        "private_original_rom_hashes_match_public_mame0106_source": False,
        "mame_executable_reports_0_106": False,
        "runtime_bundle_internal_consistency_verified": False,
        "real_mame_0106_verifyroms_dino_passed": False,
        "boot_attempted": False,
        "boot_process_spawned": False,
        "boot_process_exited_zero": False,
        "boot_process_timed_out": False,
        "boot_mng_exists": False,
        "boot_mng_decoded_and_validated": False,
        "boot_requested_frames": 0,
        "boot_decoded_frames": 0,
        "boot_image_frame_pairs_changed": 0,
        "original_dino_inp_replay_verified": False,
        "wolfmame_provenance_independently_verified": False,
        "video_callback_input_record_alignment_verified": False,
        "original_gameplay_equivalence_verified": False,
        "physical_nintendo_switch_tested": False,
        "private_rom_paths_bytes_hashes_or_video_exported_publicly": False,
    }


def _safe_romdir(path):
    path = Path(path)
    if (not gate.outside_repo(path) or path.is_symlink()
            or not path.is_dir()
            or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError("unsafe private ROM directory")
    return path


def _safe_emulator(path):
    path = Path(path)
    if (not gate.outside_repo(path) or not gate.binary_ok(path)
            or any(parent.is_symlink() for parent in path.parents)):
        raise ValueError("unsafe private MAME executable")
    return path


def _safe_capture_target(path):
    path = Path(path)
    if (not gate.outside_repo(path) or path.exists() or path.is_symlink()
            or not path.parent.is_dir() or path.parent.is_symlink()
            or any(parent.is_symlink() for parent in path.parent.parents)):
        raise ValueError("capture must be an unused private path")
    return path


def _valid_audit(audit, frames):
    return (
        type(audit) is dict
        and audit.get("mng_signature_header_end_and_chunk_crcs_valid") is True
        and audit.get("embedded_png_scanlines_and_chunk_crcs_valid") is True
        and type(audit.get("candidate_frame_count")) is int
        and audit["candidate_frame_count"] == frames
        and type(audit.get("changed_candidate_pairs")) is int
        and 0 <= audit["changed_candidate_pairs"] < frames
        and type(audit.get("identical_candidate_pairs")) is int
        and audit["changed_candidate_pairs"] + audit["identical_candidate_pairs"] == frames - 1
    )


def verify(emulator, rom_dir, *, boot_frames=0, seconds=120,
           runtime_bundle=None, capture_out=None,
           archive_verify=canonical.verify_archive,
           probe=gate.bounded_probe, runner=capture._run, mng_audit=mng.audit,
           runtime_audit=bundle_gate.audit):
    """Run local original ROM loader, and optionally capture boot MNG.

    This is NOT evidence of input playback; the ROM contains the original
    arcade program but no user-provided INP or WLF is supplied here.
    A failed boot preserves the verified ROM-loader result in a private
    boolean, but a nonzero process exit can never be a successful boot.
    """
    if (type(boot_frames) is not int or not 0 <= boot_frames <= MAX_FRAMES
            or boot_frames == 1 or type(seconds) is not int
            or not 1 <= seconds <= MAX_SECONDS):
        raise ValueError("invalid bounded private MAME boot request")
    if capture_out is not None and boot_frames == 0:
        raise ValueError("cannot retain a boot movie without requesting boot")
    report = _empty()
    report["boot_requested_frames"] = boot_frames
    emulator = _safe_emulator(emulator)
    rom_dir = _safe_romdir(rom_dir)
    if capture_out is not None:
        capture_out = _safe_capture_target(capture_out)
    source = canonical._private_regular(
        rom_dir / "dino.zip", canonical.MAX_ZIP_BYTES)
    if source.name != "dino.zip":
        raise ValueError("expected exactly private dino.zip")
    contents = archive_verify(source)
    if (type(contents) is not dict or contents.get("status") != canonical.MATCH
            or contents.get("required_rom_members_matched_by_crc32_sha1")
            != len(canonical.MANIFEST)
            or contents.get("required_payloads_crc_sha1_integrity_checked") is not True):
        report["status"] = "BLOCKED_DINO_ROM_CONTENT_NOT_CONFIRMED"
        return report
    report["historical_dino_rom_members_hash_matched"] = len(canonical.MANIFEST)
    report["private_original_rom_hashes_match_public_mame0106_source"] = True
    if runtime_bundle is not None:
        candidate = runtime_audit(runtime_bundle, emulator)
        if (type(candidate) is not dict
                or candidate.get("status") != bundle_gate.STATUS):
            report["status"] = "BLOCKED_MAME_RUNTIME_BUNDLE_INCONSISTENT"
            return report
        report["runtime_bundle_internal_consistency_verified"] = True

    with tempfile.TemporaryDirectory(prefix="dino300-private-real-mame-") as folder:
        cwd = Path(folder)
        for name in ("cfg", "nvram", "inp", "hi", "diff"):
            (cwd / name).mkdir(mode=0o700)
        rc, output, timeout = probe(emulator, ["-help"], cwd, 12)
        if (timeout or rc != 0 or not gate.VERSION.search(output)
                or not gate.MAME.search(output)):
            report["status"] = "BLOCKED_MAME_0106_HELP"
            return report
        report["mame_executable_reports_0_106"] = True
        rc, output, timeout = probe(
            emulator, ["-verifyroms", "dino", "-rompath", str(rom_dir.resolve())],
            cwd, 90)
        if timeout or rc != 0 or not gate.ROM_GOOD.search(output):
            report["status"] = "BLOCKED_REAL_MAME_DINO_ROM_LOADER"
            return report
        report["real_mame_0106_verifyroms_dino_passed"] = True
        if boot_frames == 0:
            report["status"] = ROM_ACCEPTED
            return report

        report["boot_attempted"] = True
        cmd = [
            str(emulator.resolve()),
            "dino", "-rompath", str(rom_dir.resolve()),
            "-window", "-noddraw", "-nodirect3d",
            "-nothrottle", "-noautoframeskip", "-frameskip", "0",
            "-skip_gameinfo", "-frames_to_run", str(boot_frames),
            "-mngstartframe", "0", "-mngframes", str(boot_frames),
            "-mngwrite", "stage300-boot",
        ]
        spawned, exit_code, timed_out = runner(cmd, cwd, seconds)
        report["boot_process_spawned"] = spawned is True
        report["boot_process_exited_zero"] = (type(exit_code) is int and exit_code == 0)
        report["boot_process_timed_out"] = timed_out is True
        if not report["boot_process_spawned"] or report["boot_process_timed_out"]:
            report["status"] = "BLOCKED_DINO_BOOT_PROCESS"
            return report
        if not report["boot_process_exited_zero"]:
            report["status"] = "BLOCKED_DINO_BOOT_NONZERO_EXIT"
            return report
        movie = cwd / "stage300-boot.mng"
        if movie.is_symlink() or not movie.is_file():
            report["status"] = "BLOCKED_DINO_BOOT_MNG_MISSING"
            return report
        report["boot_mng_exists"] = True
        try:
            audited = mng_audit(movie, minimum_frames=boot_frames)
        except (OSError, ValueError, KeyError, TypeError):
            report["status"] = "BLOCKED_DINO_BOOT_MNG_INVALID"
            return report
        if not _valid_audit(audited, boot_frames):
            report["status"] = "BLOCKED_DINO_BOOT_FRAME_COUNT_OR_AUDIT"
            return report
        report["boot_mng_decoded_and_validated"] = True
        report["boot_decoded_frames"] = boot_frames
        report["boot_image_frame_pairs_changed"] = audited["changed_candidate_pairs"]
        if capture_out is not None:
            capture._retain_capture(movie, capture_out)
        report["status"] = BOOT_CANDIDATE
        return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--emulator", required=True, type=Path)
    parser.add_argument("--rom-dir", required=True, type=Path)
    parser.add_argument("--runtime-bundle", type=Path,
                        help="optional source-pinned Stage290 candidate runtime bundle")
    parser.add_argument("--boot-frames", type=int, default=0,
                        help="0 means ROM loader only; 2..1200 requests boot movie")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--capture-out", type=Path,
                        help="fresh private MNG path outside repository")
    parser.add_argument("--out", required=True, type=Path,
                        help="fresh private status receipt")
    args = parser.parse_args(argv)
    try:
        result = verify(
            args.emulator, args.rom_dir, boot_frames=args.boot_frames,
            seconds=args.seconds, runtime_bundle=args.runtime_bundle,
            capture_out=args.capture_out)
    except (OSError, ValueError, KeyError, TypeError):
        result = _empty()
        result["status"] = "BLOCKED_PRIVATE_DINO_BOOT_SETUP"
    gate.write_private_receipt(args.out, result)
    print(result["status"])
    return 0 if result["status"] in (ROM_ACCEPTED, BOOT_CANDIDATE) else 2


if __name__ == "__main__":
    raise SystemExit(main())
