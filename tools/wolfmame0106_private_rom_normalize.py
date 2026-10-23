#!/usr/bin/env python3
"""Stage334: normalize a private ROM archive to the pinned MAME dino manifest.

This reads user-provided local files and writes a private dino.zip outside the
repository. It never prints ROM bytes, names, paths, CRCs, or hashes.
"""
import argparse
import binascii
import hashlib
import os
import stat
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE_ZIP_BYTES = 64 * 1024 * 1024
MAX_DRIVER_XML_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_ZIP_ENTRIES = 1024
MAX_EXPECTED_ROMS = 128


def outside_repo(path):
    resolved = Path(path).resolve()
    return resolved != ROOT and ROOT not in resolved.parents


def _private_regular(path, maximum, description):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not outside_repo(path):
        raise ValueError(description + " must be a private regular non-symlink file")
    size = path.stat().st_size
    if not 1 <= size <= maximum:
        raise ValueError(description + " exceeds size budget")
    return path


def _safe_member_name(name):
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    pure = PurePosixPath(name)
    return (not pure.is_absolute() and len(pure.parts) == 1
            and name not in (".", "..") and ":" not in name)


def _read_manifest(driver_xml):
    raw = _private_regular(driver_xml, MAX_DRIVER_XML_BYTES, "driver XML").read_bytes()
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError("invalid driver XML") from exc
    game = root.find("./game[@name='dino']")
    if game is None:
        game = root.find("./machine[@name='dino']")
    if game is None:
        raise ValueError("driver XML does not contain dino")
    expected = []
    names = set()
    for entry in game.findall("rom"):
        name = entry.attrib.get("name", "")
        if not _safe_member_name(name) or name in names:
            raise ValueError("invalid or duplicate expected ROM name")
        names.add(name)
        try:
            size = int(entry.attrib["size"], 10)
        except (KeyError, ValueError) as exc:
            raise ValueError("invalid expected ROM size") from exc
        crc = entry.attrib.get("crc", "").lower()
        sha1 = entry.attrib.get("sha1", "").lower()
        if (size <= 0 or size > MAX_MEMBER_BYTES
                or len(crc) != 8 or any(c not in "0123456789abcdef" for c in crc)
                or len(sha1) != 40 or any(c not in "0123456789abcdef" for c in sha1)):
            raise ValueError("invalid expected ROM integrity fields")
        expected.append({"name": name, "size": size, "crc": crc, "sha1": sha1})
        if len(expected) > MAX_EXPECTED_ROMS:
            raise ValueError("too many expected ROM entries")
    if not expected:
        raise ValueError("dino driver has no ROM entries")
    return expected


def normalize(source_zip, driver_xml, output_zip):
    source = _private_regular(source_zip, MAX_SOURCE_ZIP_BYTES, "source archive")
    expected = _read_manifest(driver_xml)
    destination = Path(output_zip)
    if destination.is_symlink() or destination.exists():
        raise ValueError("output must be a new private path")
    if destination.parent.is_symlink() or not destination.parent.is_dir():
        raise ValueError("output parent must be an existing real directory")
    if not outside_repo(destination.parent):
        raise ValueError("output must remain outside repository")

    by_identity = {}
    source_count = 0
    total_bytes = 0
    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        if not 1 <= len(infos) <= MAX_ZIP_ENTRIES:
            raise ValueError("source archive entry count outside budget")
        seen_names = set()
        for info in infos:
            if info.is_dir():
                continue
            source_count += 1
            if (not _safe_member_name(info.filename) or info.filename in seen_names
                    or info.flag_bits & 0x1):
                raise ValueError("unsafe, duplicate, or encrypted source entry")
            seen_names.add(info.filename)
            if info.file_size < 1 or info.file_size > MAX_MEMBER_BYTES:
                raise ValueError("source ROM entry outside size budget")
            total_bytes += info.file_size
            if total_bytes > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise ValueError("source archive exceeds total expansion budget")
            data = archive.read(info)
            size = len(data)
            crc = f"{binascii.crc32(data) & 0xffffffff:08x}"
            sha1 = hashlib.sha1(data).hexdigest()
            by_identity.setdefault((size, crc, sha1), []).append((info.filename, data))
    if not source_count:
        raise ValueError("source archive has no regular entries")

    selected = []
    used_sources = set()
    for entry in expected:
        candidates = by_identity.get((entry["size"], entry["crc"], entry["sha1"]), [])
        if len(candidates) != 1:
            raise ValueError("expected ROM content is missing or ambiguous")
        original_name, data = candidates[0]
        if original_name in used_sources:
            raise ValueError("one source entry matched multiple manifest entries")
        used_sources.add(original_name)
        selected.append((entry["name"], data))

    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w+b") as output:
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=9, strict_timestamps=True) as normalized:
                for name, data in selected:
                    info = zipfile.ZipInfo(name, date_time=(2000, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = (stat.S_IFREG | 0o600) << 16
                    normalized.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED,
                                        compresslevel=9)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    try:
        with zipfile.ZipFile(destination, "r") as normalized:
            infos = normalized.infolist()
            if [x.filename for x in infos] != [x["name"] for x in expected]:
                raise ValueError("normalized ROM entry names differ from manifest")
            for info, entry, (_, source_data) in zip(infos, expected, selected):
                data = normalized.read(info)
                if (data != source_data or len(data) != entry["size"]
                        or f"{binascii.crc32(data) & 0xffffffff:08x}" != entry["crc"]
                        or hashlib.sha1(data).hexdigest() != entry["sha1"]):
                    raise ValueError("normalized ROM entry failed integrity check")
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return {
        "schema": "dino-private-rom-normalization-v1",
        "status": "PRIVATE_ROM_NORMALIZATION_PASS",
        "expected_rom_count": len(expected),
        "source_regular_entry_count": source_count,
        "normalized_entry_count": len(selected),
        "all_expected_content_matches_unique": True,
        "all_normalized_entry_integrity_checks_passed": True,
        "output_private_outside_repository": True,
        "raw_paths_or_rom_hashes_exported": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", required=True, type=Path)
    parser.add_argument("--driver-xml", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        report = normalize(args.source_zip, args.driver_xml, args.out)
    except (OSError, ValueError, zipfile.BadZipFile):
        print("BLOCKED_PRIVATE_ROM_NORMALIZATION")
        return 2
    print(report["status"], "expected_roms=" + str(report["expected_rom_count"]),
          "source_entries=" + str(report["source_regular_entry_count"]),
          "output_entries=" + str(report["normalized_entry_count"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
