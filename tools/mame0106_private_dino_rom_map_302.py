#!/usr/bin/env python3
"""Stage302: reconstruct only declared original dino CPS-1 ROM region loads.

Uses exact public MAME 0.106 ROM_START(dino) declarations and private
canonical dino.zip bytes. NEVER export ROM bytes, decoded pixels,
original filename paths, or private hashes. Mapping is structural
evidence, NOT MAME process execution or gameplay/INP replay.
"""
import argparse
import re
import zipfile
from pathlib import Path

try:
    from . import mame0106_private_dino_rom_canonicalize_299 as canon
    from . import wolfmame0106_private_binary_gate as gate
except ImportError:
    import mame0106_private_dino_rom_canonicalize_299 as canon
    import wolfmame0106_private_binary_gate as gate

SCHEMA = "dino-private-source-grounded-cps1-rom-layout-v1"
PASS = "PRIVATE_DINO_CPS1_REGION_LAYOUT_MATCHES_MAME0106_SOURCE_UNAUTHENTICATED"
REGION_LENGTHS = {
    "CPU1": 0x200000, "GFX1": 0x400000, "GFX2": 0x8000,
    "CPU2": 0x28000, "SOUND1": 0x200000,
}
EXPECTED_COVERAGE = {
    "CPU1": 0x180000, "GFX1": 0x400000, "GFX2": 0x8000,
    "CPU2": 0x20000, "SOUND1": 0x200000,
}
# Public MAME 0.106 REGION declarations in their original driver order.
# All filenames, sizes and checksums come from publicly available source.
ORDERED_FILES = (
    "cde_23a.rom", "cde_22a.rom", "cde_21a.rom",
    "cd_gfx01.rom", "cd_gfx03.rom", "cd_gfx02.rom", "cd_gfx04.rom",
    "cd_gfx05.rom", "cd_gfx07.rom", "cd_gfx06.rom", "cd_gfx08.rom",
    "cd_q.rom", "cd_q1.rom", "cd_q2.rom", "cd_q3.rom", "cd_q4.rom",
)
# (region, mode, filename, region offset, original bytes consumed).
# Group word + skip 6 means two byte source groups at 8-byte strides.
LOAD_PLAN = (
    ("CPU1", "swap16", "cde_23a.rom", 0x000000, 0x80000),
    ("CPU1", "swap16", "cde_22a.rom", 0x080000, 0x80000),
    ("CPU1", "swap16", "cde_21a.rom", 0x100000, 0x80000),
    ("GFX1", "groupword_skip6", "cd_gfx01.rom", 0x000000, 0x80000),
    ("GFX1", "groupword_skip6", "cd_gfx03.rom", 0x000002, 0x80000),
    ("GFX1", "groupword_skip6", "cd_gfx02.rom", 0x000004, 0x80000),
    ("GFX1", "groupword_skip6", "cd_gfx04.rom", 0x000006, 0x80000),
    ("GFX1", "groupword_skip6", "cd_gfx05.rom", 0x200000, 0x80000),
    ("GFX1", "groupword_skip6", "cd_gfx07.rom", 0x200002, 0x80000),
    ("GFX1", "groupword_skip6", "cd_gfx06.rom", 0x200004, 0x80000),
    ("GFX1", "groupword_skip6", "cd_gfx08.rom", 0x200006, 0x80000),
    ("CPU2", "plain", "cd_q.rom", 0x000000, 0x08000),
    ("SOUND1", "plain", "cd_q1.rom", 0x000000, 0x80000),
    ("SOUND1", "plain", "cd_q2.rom", 0x080000, 0x80000),
    ("SOUND1", "plain", "cd_q3.rom", 0x100000, 0x80000),
    ("SOUND1", "plain", "cd_q4.rom", 0x180000, 0x80000),
)
_EXPECTED_SHA = {name: (size, crc.lower(), sha.lower())
                 for name, size, crc, sha in canon.MANIFEST}
DRIVER_PATH = "mame0106/src/drivers/cps1.c"
CODE_SIZE = re.compile(r"^\s*#\s*define\s+CODE_SIZE\s+0x200000\s*$", re.M)
BEGIN = re.compile(r"\bROM_START\(\s*dino\s*\)")
END = re.compile(r"\bROM_END\b")
REGION_RE = re.compile(r"ROM_REGION\(\s*(CODE_SIZE|0x[0-9a-fA-F]+)\s*,\s*REGION_(\w+)\s*,\s*0\s*\)")
LOAD_RE = re.compile(
    r'(ROM_LOAD16_WORD_SWAP|ROMX_LOAD|ROM_LOAD)\(\s*"([A-Za-z0-9_.-]+)"'
    r'\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)'
    r'\s*,\s*CRC\(([0-9a-fA-F]{8})\)\s*SHA1\(([0-9a-fA-F]{40})\)'
    r'\s*(?:,\s*(ROM_GROUPWORD\s*\|\s*ROM_SKIP\(6\)))?\s*\)')
CONT_RE = re.compile(r"ROM_CONTINUE\(\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*\)")
COPY_RE = re.compile(r"ROM_COPY\(\s*REGION_(\w+)\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*,\s*(0x[0-9a-fA-F]+)\s*\)")


def _driver_ops(text):
    """Read the public historical driver, reject changed memory semantics."""
    if not CODE_SIZE.search(text):
        raise ValueError("historical driver CODE_SIZE is incompatible")
    starts = list(BEGIN.finditer(text))
    if len(starts) != 1:
        raise ValueError("source does not declare exactly one original dino set")
    tail = text[starts[0].end():]
    end = END.search(tail)
    if end is None:
        raise ValueError("unterminated source ROM block")
    lines = tail[:end.start()].splitlines()
    ops = []
    selected = None
    seen = []
    for line in lines:
        # The original block uses only entire comment lines and trailing
        # C comments, no relevant macro arguments hidden inside comments.
        raw = line.split("/*", 1)[0].strip()
        if not raw or raw.startswith("//"):
            continue
        m = REGION_RE.fullmatch(raw)
        if m:
            size_text, region = m.groups()
            size = 0x200000 if size_text == "CODE_SIZE" else int(size_text, 16)
            if region not in REGION_LENGTHS or size != REGION_LENGTHS[region]:
                raise ValueError("unexpected CPS-1 region length")
            selected = region
            ops.append(("region", region, size))
            continue
        m = LOAD_RE.fullmatch(raw)
        if m and selected is not None:
            mode, name, addr, length, crc, sha, group = m.groups()
            mode = {"ROM_LOAD16_WORD_SWAP":"swap16", "ROMX_LOAD":"groupword_skip6",
                    "ROM_LOAD":"plain"}[mode]
            if (mode == "groupword_skip6") != (group is not None):
                raise ValueError("invalid CPS-1 graphic interleave directive")
            if (name not in _EXPECTED_SHA or
                    (int(length, 16), crc.lower(), sha.lower()) != _EXPECTED_SHA[name]):
                # cd_q.rom ROM_LOAD is 0x8000 then ROM_CONTINUE for 0x18000
                if not (name == "cd_q.rom" and int(length, 16) == 0x8000
                        and (crc.lower(), sha.lower()) == _EXPECTED_SHA[name][1:]):
                    raise ValueError("dino ROM identity changed from source")
            ops.append(("load", selected, mode, name, int(addr,16), int(length,16)))
            seen.append(name)
            continue
        m = CONT_RE.fullmatch(raw)
        if m:
            ops.append(("continue", selected, int(m.group(1),16), int(m.group(2),16)))
            continue
        m = COPY_RE.fullmatch(raw)
        if m:
            src, srcoff, destoff, length = m.groups()
            ops.append(("copy", selected, src, int(srcoff,16),
                        int(destoff,16), int(length,16)))
            continue
        raise ValueError("unrecognized or modified CPS-1 dino ROM directive")
    expected = []
    seen_region = None
    for region, mode, name, off, size in LOAD_PLAN:
        if region != seen_region:
            # GFX2 star ROM_COPY occurs between GFX1 and CPU2.
            if region == "CPU2":
                expected.extend([
                    ("region","GFX2",0x8000),
                    ("copy","GFX2","GFX1",0,0,0x8000),
                ])
            expected.append(("region", region, REGION_LENGTHS[region]))
            seen_region = region
        expected.append(("load",region,mode,name,off,size))
        if name == "cd_q.rom":
            expected.append(("continue","CPU2",0x10000,0x18000))
    if ops != expected or tuple(seen) != ORDERED_FILES:
        raise ValueError("dino ROM load layout differs from pinned CPS-1 contract")
    return ops


def _put(region, occupied, offset, payload, *, stride=1):
    if type(offset) is not int or offset < 0 or stride not in (1,8):
        raise ValueError("invalid source ROM placement")
    if not payload:
        raise ValueError("empty ROM memory region write")
    stop = offset + (len(payload) - 1) * stride + 1
    if stop > len(region) or any(occupied[offset:stop:stride]):
        raise ValueError("ROM write out of bounds or overlaps existing bytes")
    region[offset:stop:stride] = payload
    occupied[offset:stop:stride] = bytes([1]) * len(payload)


def _apply(ops, payloads, *, lengths=REGION_LENGTHS):
    """Generic mapper: no game bytes or mapped regions leave this function."""
    regions = {}
    masks = {}
    last = None
    src_position = 0
    for item in ops:
        opcode = item[0]
        if opcode == "region":
            _, region, size = item
            if region in regions or region not in lengths or size != lengths[region]:
                raise ValueError("duplicate or unrecognized ROM region")
            regions[region] = bytearray(size)
            masks[region] = bytearray(size)
        elif opcode == "load":
            _, region, mode, name, off, n = item
            if region not in regions or name not in payloads:
                raise ValueError("missing source ROM or destination region")
            data = payloads[name]
            if len(data) < n or n <= 0:
                raise ValueError("source ROM shorter than load declaration")
            part = data[:n]
            if mode == "plain":
                _put(regions[region], masks[region], off, part)
            elif mode == "swap16":
                if len(part) % 2 or off % 2:
                    raise ValueError("misaligned 68000 word-swapped ROM")
                swapped = bytearray(part)
                swapped[0::2] = part[1::2]
                swapped[1::2] = part[0::2]
                _put(regions[region], masks[region], off, swapped)
            elif mode == "groupword_skip6":
                if len(part) % 2 or off % 2:
                    raise ValueError("invalid CPS-1 groupword lane")
                _put(regions[region], masks[region], off, part[0::2], stride=8)
                _put(regions[region], masks[region], off+1, part[1::2], stride=8)
            else:
                raise ValueError("unknown ROM memory transform")
            last = (region, name)
            src_position = n
        elif opcode == "continue":
            _, region, off, n = item
            if last is None or last[0] != region:
                raise ValueError("ROM_CONTINUE without corresponding load")
            payload = payloads[last[1]]
            if n <= 0 or src_position+n > len(payload):
                raise ValueError("invalid ROM_CONTINUE source consumption")
            _put(regions[region], masks[region], off,
                 payload[src_position:src_position+n])
            src_position += n
        elif opcode == "copy":
            _, region, source, srcoff, destoff, n = item
            if region not in regions or source not in regions or n <= 0:
                raise ValueError("invalid ROM_COPY region")
            if (srcoff < 0 or srcoff+n > len(regions[source])
                    or not all(masks[source][srcoff:srcoff+n])):
                raise ValueError("ROM_COPY refers to unloaded source graphics")
            _put(regions[region], masks[region], destoff,
                 regions[source][srcoff:srcoff+n])
        else:
            raise ValueError("unknown historical dino ROM operation")
    return {
        region: {"region_bytes": len(data), "source_loaded_bytes": sum(masks[region]),
                 "unpopulated_bytes": len(data)-sum(masks[region])}
        for region,data in regions.items()
    }


def verify(rom, source, *, source_member=DRIVER_PATH):
    """Independent private ROM mapping from *actual* CPS-1 source text."""
    rom = canon._private_regular(rom, canon.MAX_ZIP_BYTES)
    source = canon._private_regular(source, canon.MAX_ZIP_BYTES)
    manifest = canon.verify_archive(rom)
    if (manifest.get("status") != canon.MATCH
            or manifest.get("required_rom_members_matched_by_crc32_sha1") != 16):
        raise ValueError("private ROM hash source manifest not satisfied")
    with zipfile.ZipFile(source) as z:
        infos=z.infolist()
        if len(infos)>4000 or source_member not in z.namelist():
            raise ValueError("unexpected historical MAME source ZIP")
        driver = z.read(source_member)
        if len(driver)>6*1024*1024:
            raise ValueError("CPS-1 source is too large")
        ops = _driver_ops(driver.decode("latin-1"))
    with zipfile.ZipFile(rom) as z:
        if (len(z.namelist()) != len(ORDERED_FILES) or
                set(z.namelist()) != set(ORDERED_FILES)):
            raise ValueError("dino ZIP is not the exact canonical game set")
        payloads = {name:z.read(name) for name in ORDERED_FILES}
    mapped = _apply(ops,payloads)
    if (set(mapped)!=set(REGION_LENGTHS)
            or any(mapped[k]["source_loaded_bytes"]!=EXPECTED_COVERAGE[k]
                   for k in REGION_LENGTHS)):
        raise ValueError("original ROM regions do not cover declared CPS-1 memory")
    if (mapped["GFX1"]["unpopulated_bytes"] or
            mapped["GFX2"]["unpopulated_bytes"] or
            mapped["SOUND1"]["unpopulated_bytes"]):
        raise ValueError("CPS-1 graphic or sound region incomplete")
    return {
        "schema": SCHEMA, "status": PASS,
        "original_dino_rom_hash_matched_members": 16,
        "source_grounded_rom_declarations": len(LOAD_PLAN),
        "mame0106_cps1_regions": mapped,
        "gfx_lane_groupword_skip6_integrity_checked": True,
        "code_68000_word_swap_checked": True,
        "qsound_continue_mapping_checked": True,
        "copied_stars_graphics_region_checked": True,
        "original_game_rom_or_derived_region_bytes_exported": False,
        "historical_mame_executable_ran": False,
        "original_dino_gameplay_verified": False,
        "original_inp_wlf_replay_verified": False,
        "wolfmame_provenance_independently_verified": False,
        "physical_nintendo_switch_tested": False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom",type=Path,required=True,
                        help="local private canonical original dino.zip")
    parser.add_argument("--mame-source",type=Path,required=True,
                        help="private copy of code-only source-pinned mame0106-source.zip")
    parser.add_argument("--out",type=Path,required=True,
                        help="fresh aggregate-only private receipt")
    args=parser.parse_args(argv)
    try:
        report=verify(args.rom,args.mame_source)
    except (OSError,ValueError,UnicodeError,KeyError,zipfile.BadZipFile):
        report={"schema":SCHEMA,"status":"BLOCKED_PRIVATE_DINO_CPS1_MAP",
                "original_dino_gameplay_verified":False,
                "original_inp_wlf_replay_verified":False,
                "original_game_rom_or_derived_region_bytes_exported":False}
    gate.write_private_receipt(args.out,report)
    print(report["status"])
    return 0 if report["status"]==PASS else 2


if __name__=="__main__":
    raise SystemExit(main())
