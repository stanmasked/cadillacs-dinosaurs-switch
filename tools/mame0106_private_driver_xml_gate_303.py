#!/usr/bin/env python3
"""Stage303: compare compiled MAME 0.106 -listxml dino ROMs to private dino.zip.

Use only in private local workspace; never export original bytes, paths,
hashes or emulator output. Compiled XML is a *candidate catalog*, not
proof that the game booted or that WolfMAME was authenticated.
"""
import argparse
import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from . import wolfmame0106_private_binary_gate as gate
    from . import mame0106_private_dino_rom_canonicalize_299 as canon
    from . import mame0106_private_dino_rom_map_302 as source_map
except ImportError:
    import wolfmame0106_private_binary_gate as gate
    import mame0106_private_dino_rom_canonicalize_299 as canon
    import mame0106_private_dino_rom_map_302 as source_map

SCHEMA = "dino-stage303-compiled-driver-xml-private-rom-consistency-v1"
PASS = "PRIVATE_DINO_COMPILED_DRIVER_XML_AND_ROM_MATCH_UNAUTHENTICATED"
BLOCKED = "BLOCKED_PRIVATE_DINO_COMPILED_XML_ROM_MISMATCH"
MAX_XML_BYTES = 64 * 1024 * 1024


def _private_regular(path, limit):
    p = Path(path)
    if (not gate.outside_repo(p) or not gate.is_regular(p)
            or any(parent.is_symlink() for parent in p.parents)
            or not 1 <= p.stat().st_size <= limit):
        raise ValueError("unsafe or oversized private evidence input")
    return p


def _layout_from_source():
    return {
        name: (region.lower(), f"{offset:x}")
        for region, _mode, name, offset, _length in source_map.LOAD_PLAN
    }


def _read_dino_xml(xml_path):
    """Parse bounded MAME XML, retaining only the one dino game entry."""
    data = _private_regular(xml_path, MAX_XML_BYTES).read_bytes()
    # Standard MAME DTD uses ELEMENT/ATTLIST, never entity expansion.
    if b"<!ENTITY" in data.upper():
        raise ValueError("XML entities forbidden")
    matches = []
    for _, element in ET.iterparse(io.BytesIO(data), events=("end",)):
        if element.tag != "game":
            continue
        if element.attrib.get("name") == "dino":
            if (element.attrib.get("sourcefile") != "cps1.c"
                    or element.attrib.get("runnable", "yes") != "yes"
                    or any(k in element.attrib for k in ("cloneof", "romof"))):
                raise ValueError("unexpected compiled dino driver identity")
            rows = [dict(child.attrib) for child in element.findall("rom")]
            matches.append(rows)
        element.clear()
        if len(matches) > 1:
            raise ValueError("duplicate compiled dino driver")
    if len(matches) != 1:
        raise ValueError("compiled MAME catalog lacks unique dino driver")
    return matches[0]


def audit(xml_file, rom_file, *, manifest=canon.MANIFEST,
          layout=None):
    """Verify compiled catalog AND private original ROM digests independently."""
    layout = _layout_from_source() if layout is None else dict(layout)
    expected = {name: (size, crc.lower(), sha.lower())
                for name, size, crc, sha in manifest}
    if not expected or len(expected) != len(manifest) or set(expected) != set(layout):
        raise ValueError("incomplete expected public source ROM contract")
    xml_entries = _read_dino_xml(xml_file)
    if len(xml_entries) != len(expected):
        raise ValueError("compiled dino ROM count differs from public source")
    seen = set()
    regions = {}
    for row in xml_entries:
        name = row.get("name")
        if name in seen or name not in expected:
            raise ValueError("duplicate or unknown compiled dino ROM")
        seen.add(name)
        size, crc, sha = expected[name]
        try:
            xml_size = int(row["size"])
        except (KeyError, ValueError, TypeError) as err:
            raise ValueError("invalid compiled ROM byte size") from err
        if (xml_size != size or row.get("crc", "").lower() != crc
                or row.get("sha1", "").lower() != sha
                or row.get("status", "good") != "good"
                or row.get("region") != layout[name][0]
                or row.get("offset", "").lower() != layout[name][1]):
            raise ValueError("compiled ROM hash, placement or status disagrees")
        region = row["region"]
        regions[region] = regions.get(region, 0) + 1
    if seen != set(expected):
        raise ValueError("compiled MAME driver missing original ROM")
    rom = _private_regular(rom_file, canon.MAX_ZIP_BYTES)
    with zipfile.ZipFile(rom) as archive:
        files = archive.namelist()
        if len(files) != len(expected) or set(files) != set(expected):
            raise ValueError("private dino.zip has extra/missing/duplicate names")
    checked = canon.verify_archive(rom, manifest=manifest)
    if (checked.get("status") != canon.MATCH or
            checked.get("required_rom_members_matched_by_crc32_sha1") != len(expected)):
        raise ValueError("private ROM bytes do not match compiled catalog")
    return {
        "schema": SCHEMA,
        "status": PASS,
        "private_rom_members_confirmed": len(expected),
        "compiled_dino_rom_entries_confirmed": len(xml_entries),
        "compiled_region_entry_counts": dict(sorted(regions.items())),
        "compiled_mame_driver_source_identity_checked": True,
        "compiled_mame_rom_hashes_and_offsets_agree_with_source": True,
        "private_rom_crc32_and_sha1_both_checked": True,
        "mame_original_rom_loader_executed": False,
        "mame_original_dino_gameplay_verified": False,
        "original_inp_wlf_replay_verified": False,
        "wolfmame_binary_provenance_authenticated": False,
        "physical_switch_tested": False,
        "private_game_bytes_hashes_paths_exported": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--driver-xml", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.driver_xml, args.rom)
    except (OSError, ValueError, TypeError, ET.ParseError, zipfile.BadZipFile):
        result = {"schema": SCHEMA, "status": BLOCKED,
                  "mame_original_rom_loader_executed": False,
                  "mame_original_dino_gameplay_verified": False,
                  "original_inp_wlf_replay_verified": False,
                  "private_game_bytes_hashes_paths_exported": False}
    gate.write_private_receipt(args.out, result)
    print(result["status"])
    return 0 if result["status"] == PASS else 2


if __name__ == "__main__":
    raise SystemExit(main())
