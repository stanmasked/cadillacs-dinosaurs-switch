"""Stage385: independently repeat owner-private Stage384 ROM content evidence.

Offline integrity only, never executes emulator, INP playback or Switch.
No ROM, XML, extracted binary, private path or original capture in output.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import zipfile

from tools import mame0106_private_verifyroms as romcheck
from tools import mame0106_private_windows_capsule as capsule
from tools import mame0106_romfree_native_windows_probe as golden

SCHEMA = "cadillacs-stage385-private-offline-rom-reproduction-v1"
STAGE384_SCHEMA = "cadillacs-stage384-owner-only-private-dino-rom-content-offline-v1"
STAGE384_REPORT_SHA256 = "8aa4b3e71bdb70150abf9a8ed38287fe4c7471ba994324cf953cbdfbcb5fe47f"
CAPSULE_SHA256 = "fa6ff589b109db70c8231bf7713ec50cf5b9a15b58e43bb3b6705bc25e4bd19d"
GOLDEN_ZIP_SHA256 = "c9296bcc2608dae2ab82494ea89ad6a5f3850a3e145fce620272b798858bb53a"
ROM_ZIP_SHA256 = romcheck.PINNED_ROM_SHA256
DRIVER_SHA256 = romcheck.PINNED_XML_SHA256
EXE_SHA256 = golden.EXE_SHA
MAX_REPORT_BYTES = 4096
MAX_GOLDEN_UNPACKED = 256 * 1024 * 1024
MAX_GOLDEN_ZIP = 60 * 1024 * 1024
MAX_CAPSULE = capsule.MAX_OUTPUT_BYTES


class RepeatError(Exception):
    """Fixed refusal identifiers without leaking private file paths."""


def _sha_path(path: Path, max_size: int) -> str:
    capsule.guard_private()
    if path.is_symlink() or not path.is_file():
        raise RepeatError("missing_or_linked_input")
    size = path.stat().st_size
    if not 0 < size <= max_size:
        raise RepeatError("private_input_size_refused")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _private_output(output: Path) -> None:
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise RepeatError("output_must_be_new")
    if any(parent.is_symlink() or bool(getattr(parent.lstat(), "st_file_attributes", 0) &
                                     getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))
           for parent in output.parents):
        raise RepeatError("linked_output_parent")
    real = output.resolve(strict=False)
    root = capsule.REPO_ROOT.resolve()
    if real == root or root in real.parents:
        raise RepeatError("output_in_public_repo")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RepeatError("duplicate_json_key")
        result[key] = value
    return result


def _no_nan(_value):
    raise RepeatError("nonfinite_json_number")


def _read_stage384(path: Path) -> dict:
    if _sha_path(path, MAX_REPORT_BYTES) != STAGE384_REPORT_SHA256:
        raise RepeatError("stage384_evidence_sha_mismatch")
    try:
        report = json.loads(path.read_bytes().decode("utf-8"),
                            object_pairs_hook=_unique_pairs, parse_constant=_no_nan)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise RepeatError("stage384_evidence_invalid") from exc
    if type(report) is not dict or set(report) != {
        "schema", "capsule_sha256", "created_utc", "evidence_grade",
        "helper_v2_zip_sha256", "historical_driver_xml_sha256",
        "integrity_status", "mame_executable_sha256",
        "mame_inp_playback_executed", "native_mame_verifyroms_executed",
        "physical_nintendo_switch_executed", "private_rom_sha256",
        "private_source_bytes_in_report", "rom_inventory_expected",
        "rom_payload_bytes_checked", "rom_payloads_verified",
        "runtime_host", "technical_source_zip_sha256",
    }:
        raise RepeatError("stage384_evidence_inventory_refused")
    expected = {
        "schema": STAGE384_SCHEMA,
        "capsule_sha256": CAPSULE_SHA256,
        "evidence_grade": "private_offline_rom_crc_sha1_only",
        "historical_driver_xml_sha256": DRIVER_SHA256,
        "integrity_status": "pass",
        "mame_executable_sha256": EXE_SHA256,
        "mame_inp_playback_executed": False,
        "native_mame_verifyroms_executed": False,
        "physical_nintendo_switch_executed": False,
        "private_rom_sha256": ROM_ZIP_SHA256,
        "private_source_bytes_in_report": False,
        "rom_inventory_expected": 16,
        "rom_payload_bytes_checked": 7995392,
        "rom_payloads_verified": 16,
        "runtime_host": "linux_private_offline_no_emulator",
        "technical_source_zip_sha256": GOLDEN_ZIP_SHA256,
    }
    if any(type(report[key]) is not type(val) or report[key] != val
           for key, val in expected.items()):
        raise RepeatError("stage384_evidence_conflict")
    if type(report["created_utc"]) is not str or not report["created_utc"].endswith("+00:00"):
        raise RepeatError("stage384_timestamp_refused")
    return report


def _verify_golden(archive: Path) -> None:
    if _sha_path(archive, MAX_GOLDEN_ZIP) != GOLDEN_ZIP_SHA256:
        raise RepeatError("golden_archive_digest_mismatch")
    try:
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            allowed = golden.FROZEN_COMPONENT_SHA256
            if len(infos) != len(allowed) or {i.filename for i in infos} != set(allowed):
                raise RepeatError("golden_inventory_refused")
            total = 0
            for entry in infos:
                if (entry.is_dir() or entry.flag_bits & 1 or
                        stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK or
                        entry.file_size <= 0):
                    raise RepeatError("golden_member_type_refused")
                total += entry.file_size
                if total > MAX_GOLDEN_UNPACKED:
                    raise RepeatError("golden_unpacked_size_refused")
                h = hashlib.sha256()
                with z.open(entry) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(block)
                if h.hexdigest() != allowed[entry.filename]:
                    raise RepeatError("golden_member_checksum_mismatch")
            if z.testzip() is not None:
                raise RepeatError("golden_crc_mismatch")
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError) as exc:
        raise RepeatError("golden_zip_invalid") from exc


def _stage(source: zipfile.ZipFile, member: str, target: Path, max_size: int) -> None:
    info = source.getinfo(member)
    if not 0 < info.file_size <= max_size:
        raise RepeatError("temporary_member_size_refused")
    with source.open(info) as stream, target.open("xb") as writer:
        shutil.copyfileobj(stream, writer, 1024 * 1024)
    if target.stat().st_size != info.file_size:
        raise RepeatError("temporary_member_size_mismatch")


def reproduce(original_capsule: Path, golden_zip: Path, stage384_report: Path) -> dict:
    """Recompute all ROM CRC/SHA1 against frozen driver, keeping results private."""
    capsule.guard_private()
    _read_stage384(stage384_report)
    _verify_golden(golden_zip)
    try:
        capsule.validate_capsule(
            original_capsule, archive_sha=CAPSULE_SHA256,
            rom_sha=ROM_ZIP_SHA256, exe_sha=EXE_SHA256,
            xml_sha=DRIVER_SHA256)
    except (capsule.CapsuleError, OSError, ValueError) as exc:
        raise RepeatError("private_capsule_validation_refused") from exc
    with tempfile.TemporaryDirectory(prefix="cadillacs-stage385-private-") as temp:
        root = Path(temp)
        rom = root / "owner-original-rom.zip"
        xml = root / "original-driver.xml"
        with zipfile.ZipFile(original_capsule) as private:
            _stage(private, "roms/dino.zip", rom, capsule.MAX_ROM_BYTES)
        with zipfile.ZipFile(golden_zip) as public:
            _stage(public, "dino-driver.xml", xml, 40 * 1024 * 1024)
        measured = romcheck.offline_audit(rom, xml)
        if (measured["offline_audit"] != "pass" or
                measured["verified_roms"] != 16 or
                measured["expected_roms"] != 16 or
                measured["verified_rom_payload_bytes"] != 7995392):
            raise RepeatError("reproduced_rom_evidence_conflict")
    return {
        "schema": SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "verified_offline_only",
        "original_capsule_sha256": CAPSULE_SHA256,
        "historical_golden_archive_sha256": GOLDEN_ZIP_SHA256,
        "stage384_report_sha256": STAGE384_REPORT_SHA256,
        "original_rom_sha256": ROM_ZIP_SHA256,
        "driver_sha256": DRIVER_SHA256,
        "exe_sha256_pinned_not_executed": EXE_SHA256,
        "rom_members_verified_crc32_sha1": 16,
        "rom_payload_bytes_verified": measured["verified_rom_payload_bytes"],
        "native_mame_process_executed": False,
        "inp_playback_executed": False,
        "physical_switch_executed": False,
        "independent_windows_attestation": False,
        "private_game_bytes_in_report": False,
        "owner_only_archive_required": True,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capsule", type=Path, required=True)
    parser.add_argument("--golden-zip", type=Path, required=True)
    parser.add_argument("--stage384-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        capsule.guard_private()
        _private_output(args.output)
        report = reproduce(args.capsule, args.golden_zip, args.stage384_report)
        data = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode()
        if len(data) > MAX_REPORT_BYTES:
            raise RepeatError("report_size_refused")
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        if args.output.read_bytes() != data:
            raise RepeatError("report_readback_mismatch")
        print("status=verified_offline_only")
        print("rom_members_verified_crc32_sha1=16")
        print("native_mame_process_executed=False")
        print("original_inp_playback_executed=False")
        return 0
    except (RepeatError, capsule.CapsuleError, romcheck.PrivateProbeError,
            OSError, ValueError, zipfile.BadZipFile, RuntimeError):
        print("status=stage385_private_reproduction_refused")
        return 2


if __name__ == "__main__":
    sys.exit(main())
