#!/usr/bin/env python3
"""Stage294: local-only content consistency gate for Stage290 Windows runtime.

Verifies private extracted GitHub Action *candidate* bundle SHA256SUMS,
source-pin metadata, PE32 architecture, count-trace patch and CLI texts.
The manifest is UNSIGNED and user-supplied: it cannot independently
authenticate GitHub origin, WolfMAME provenance or real gameplay.
Never export executable bytes, original ROMs, paths or SHA-256 values.
"""
import argparse
import hashlib
import re
import struct
from pathlib import Path

try:
    from . import wolfmame0106_private_binary_gate as gate
except ImportError:
    import wolfmame0106_private_binary_gate as gate

SCHEMA = "dino-private-mame0106-runtime-bundle-binding-v1"
STATUS = "CANDIDATE_RUNTIME_BUNDLE_CONTENT_CONSISTENT_UNAUTHENTICATED"
EXPECTED_FILES = (
    "mame0106.exe",
    "mame0106-source.zip",
    "mame0106-build-compat.patch",
    "mame0106-windowed-mng-capture.patch",
    "mame0106-inprocess-count-trace-combined.patch",
    "dino-driver.xml",
    "mame0106-help.txt",
    "mame0106-showconfig.txt",
)
EXPECTED_METADATA = {
    "source_repository": "https://github.com/mamedev/historic-mame",
    "source_tag": "mame0106",
    "source_commit": "0a83d596c83b4d1a72cb3a7b1d2835b809206f2f",
    "window_capture_patch": "mame0106-windowed-mng-capture.patch",
    "inprocess_counter_trace": "enabled_on_request",
    "build_compat_patch": "mame0106-build-compat.patch",
    "inprocess_counter_source_patch": "mame0106-inprocess-count-trace-combined.patch",
    "help_smoke_test": "passed",
    "playback_and_windowed_mng_options_smoke_test": "passed",
    "listxml_smoke_test": "passed",
    "dino_driver_listed": "yes",
}
MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  ([a-zA-Z0-9_.-]+)\Z")
MAX_BUNDLE_FILE_BYTES = 512 * 1024 * 1024
MAX_MANIFEST_BYTES = 4096
MAX_PIN_BYTES = 4096
MAX_SOURCE_TEXT_BYTES = 8 * 1024 * 1024


def _safe_regular(path, maximum):
    path = Path(path)
    if (not gate.outside_repo(path) or not gate.is_regular(path)
            or any(ancestor.is_symlink() for ancestor in path.parents)
            or not 1 <= path.stat().st_size <= maximum):
        raise ValueError("unsafe private bundle member or size")
    return path


def _private_folder(folder):
    folder = Path(folder)
    if (not gate.outside_repo(folder) or folder.is_symlink()
            or not folder.is_dir()
            or any(ancestor.is_symlink() for ancestor in folder.parents)):
        raise ValueError("invalid private runtime bundle directory")
    return folder


def _text(path, limit):
    raw = _safe_regular(path, limit).read_bytes()
    try:
        value = raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("binary data where text expected") from exc
    if "\r" in value or not value.endswith("\n"):
        raise ValueError("non-canonical runtime metadata line endings")
    return value


def _digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _manifest(bundle):
    lines = _text(bundle / "SHA256SUMS.txt", MAX_MANIFEST_BYTES).splitlines()
    parsed = {}
    for line in lines:
        m = MANIFEST_LINE.fullmatch(line)
        if not m:
            raise ValueError("invalid runtime SHA256SUMS record")
        value, name = m.groups()
        if name in parsed:
            raise ValueError("duplicate runtime SHA256SUMS record")
        parsed[name] = value
    if set(parsed) != set(EXPECTED_FILES):
        raise ValueError("missing or unexpected runtime SHA256SUMS names")
    return parsed


def _source_pin(bundle):
    lines = _text(bundle / "source-pin.txt", MAX_PIN_BYTES).splitlines()
    parsed = {}
    for line in lines:
        if line.count("=") != 1:
            raise ValueError("invalid source pin record")
        key, value = line.split("=", 1)
        if not key or key in parsed:
            raise ValueError("duplicate source-pin attribute")
        parsed[key] = value
    if parsed != EXPECTED_METADATA:
        raise ValueError("source pin lacks exact Stage290 instrumentation metadata")


def _pe32_i386(path):
    with Path(path).open("rb") as source:
        stub = source.read(64)
        if len(stub) != 64 or stub[:2] != b"MZ":
            raise ValueError("not a Windows PE executable")
        pe_offset = struct.unpack_from("<I", stub, 0x3c)[0]
        if not 64 <= pe_offset <= 1024 * 1024:
            raise ValueError("unreasonable PE header offset")
        source.seek(pe_offset)
        pe_head = source.read(26)
    if (len(pe_head) != 26 or pe_head[:4] != b"PE\x00\x00"
            or pe_head[4:6] != b"\x4c\x01"):
        raise ValueError("not a PE32 Intel i386 executable")
    optional_magic = struct.unpack_from("<H", pe_head, 24)[0]
    if optional_magic != 0x10b:
        raise ValueError("expected PE32 rather than PE32+ or missing optional header")


def _verify_patch(bundle):
    text = _text(bundle / "mame0106-inprocess-count-trace-combined.patch",
                 MAX_SOURCE_TEXT_BYTES)
    for item in (
        "diff --git a/src/inptport.c b/src/inptport.c",
        "diff --git a/src/video.c b/src/video.c",
        "diff --git a/src/video.h b/src/video.h",
        "diff --git a/src/windows/video.c b/src/windows/video.c",
        "diff --git a/src/windows/video.h b/src/windows/video.h",
        "stage290_note_playback_word",
        "mngcounttrace",
        "stage290-mng-counts.csv",
    ):
        if item not in text:
            raise ValueError("counter trace reproduction patch incomplete")


def _verify_cli(bundle):
    config = _text(bundle / "mame0106-showconfig.txt",
                   MAX_SOURCE_TEXT_BYTES).lower()
    for option in (
        "playback", "mngwrite", "mngstartframe", "mngframes",
        "mngcounttrace", "frames_to_run",
    ):
        if option not in config:
            raise ValueError("expected runtime command-line option absent")
    help_text = _text(bundle / "mame0106-help.txt",
                      MAX_SOURCE_TEXT_BYTES).lower()
    if "m.a.m.e. v0.106" not in help_text:
        raise ValueError("runtime help version inconsistent")
    drivers = _text(bundle / "dino-driver.xml", MAX_SOURCE_TEXT_BYTES)
    if '<game name="dino"' not in drivers:
        raise ValueError("historical runtime driver index lacks dino")


def _empty_report():
    return {
        "schema": SCHEMA,
        "status": "BLOCKED_RUNTIME_BUNDLE_NOT_AUDITED",
        "private_binary_matches_bundle_digest": False,
        "all_expected_artifacts_match_local_manifest": False,
        "exact_pinned_historical_source_metadata": False,
        "source_patch_declares_inprocess_trace": False,
        "candidate_cli_options_and_driver_list_present": False,
        "candidate_executable_is_pe32_i386": False,
        "github_artifact_origin_cryptographically_attested": False,
        "wolfmame_binary_provenance_independently_verified": False,
        "actual_original_inp_playback_verified": False,
        "input_video_causality_verified": False,
        "physical_nintendo_switch_tested": False,
        "private_binary_paths_hashes_rom_or_input_exported": False,
    }


def audit(bundle_dir, emulator):
    """Check the private candidate bundle against its unsigned manifest."""
    bundle = _private_folder(bundle_dir)
    emulator = _safe_regular(emulator, MAX_BUNDLE_FILE_BYTES)
    expected = _manifest(bundle)
    for name in EXPECTED_FILES:
        path = _safe_regular(bundle / name, MAX_BUNDLE_FILE_BYTES)
        if _digest(path) != expected[name]:
            raise ValueError("runtime artifact content does not match manifest")
    if _digest(emulator) != expected["mame0106.exe"]:
        raise ValueError("selected emulator differs from candidate bundle runtime")
    _pe32_i386(emulator)
    _source_pin(bundle)
    _verify_patch(bundle)
    _verify_cli(bundle)
    result = _empty_report()
    result.update({
        "status": STATUS,
        "private_binary_matches_bundle_digest": True,
        "all_expected_artifacts_match_local_manifest": True,
        "exact_pinned_historical_source_metadata": True,
        "source_patch_declares_inprocess_trace": True,
        "candidate_cli_options_and_driver_list_present": True,
        "candidate_executable_is_pe32_i386": True,
    })
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-bundle", type=Path, required=True)
    parser.add_argument("--emulator", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = audit(args.runtime_bundle, args.emulator)
    except (OSError, ValueError, UnicodeError, TypeError):
        report = _empty_report()
        report["status"] = "BLOCKED_PRIVATE_RUNTIME_BUNDLE_INCONSISTENT"
    gate.write_private_receipt(args.out, report)
    print(report["status"])
    return 0 if report["status"] == STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
