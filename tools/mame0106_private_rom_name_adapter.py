"""Offline, lossless, checksum-based MAME ROM archive naming adapter.

Publish only code and synthetic tests. Output ZIP and JSON manifest are PRIVATE.
This utility never executes MAME or claims playback compatibility.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import xml.etree.ElementTree as ET
import zipfile

SAFE_NAME = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
HEX_SHA1 = re.compile(r"[0-9a-fA-F]{40}\Z")
HEX_CRC32 = re.compile(r"[0-9a-fA-F]{8}\Z")
HEX_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")
MAX_INPUT_BYTES = 128 * 1024 * 1024
MAX_MEMBERS = 512
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_UNPACKED_BYTES = 128 * 1024 * 1024


class AdapterError(Exception):
    """Fail closed and keep private paths/ROM bytes out of error messages."""


def digest_path(path: Path, algo: str = "sha256") -> str:
    h = hashlib.new(algo)
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require_source(path: Path, expected_sha256: str) -> int:
    if (not path.is_file() or path.is_symlink() or
            not HEX_SHA256.fullmatch(expected_sha256) or
            path.stat().st_size > MAX_INPUT_BYTES):
        raise AdapterError('untrusted_input')
    if digest_path(path) != expected_sha256.lower():
        raise AdapterError('input_hash_mismatch')
    return path.stat().st_size


def expected_roms(driver_xml: Path, game: str):
    """Parse a source-pinned MAME -listxml, accepting only exact named driver."""
    if not SAFE_NAME.fullmatch(game):
        raise AdapterError('invalid_game')
    roms = None
    found = 0
    try:
        with driver_xml.open('rb') as xml_stream:
            for event, elem in ET.iterparse(xml_stream, events=('end',)):
                if elem.tag != 'game':
                    continue
                if elem.get('name') == game:
                    found += 1
                    if found > 1 or elem.get('runnable') != 'yes':
                        raise AdapterError('duplicate_or_nonrunnable_driver')
                    roms = []
                    for rom in elem.findall('rom'):
                        name, size, crc, sha1 = (rom.get(k) for k in ('name','size','crc','sha1'))
                        if (not isinstance(name, str) or not SAFE_NAME.fullmatch(name)
                                or not isinstance(size, str) or not size.isascii() or not size.isdigit()
                                or not isinstance(crc, str) or not HEX_CRC32.fullmatch(crc)
                                or not isinstance(sha1, str) or not HEX_SHA1.fullmatch(sha1)):
                            raise AdapterError('unsupported_driver_rom_entry')
                        n = int(size)
                        if n <= 0 or n > MAX_MEMBER_BYTES:
                            raise AdapterError('oversized_driver_rom')
                        roms.append((name, n, crc.lower(), sha1.lower()))
                    if not roms or len(roms) > MAX_MEMBERS or len({r[0] for r in roms}) != len(roms):
                        raise AdapterError('invalid_driver_inventory')
                    break
                elem.clear()
    except (ET.ParseError, OSError, UnicodeError, ValueError) as exc:
        raise AdapterError('unreadable_driver_xml') from exc
    if roms is None or found != 1:
        raise AdapterError('game_driver_missing')
    return roms


def source_members(archive: Path) -> dict[tuple[int,str,str], list[tuple[str,bytes]]]:
    """CRC-check every source ZIP member and fingerprint payloads; no extraction."""
    index: dict[tuple[int,str,str], list[tuple[str,bytes]]] = {}
    try:
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            if not infos or len(infos) > MAX_MEMBERS or len({i.filename for i in infos}) != len(infos):
                raise AdapterError('invalid_source_inventory')
            total = 0
            for info in infos:
                mode = info.external_attr >> 16
                if (not SAFE_NAME.fullmatch(info.filename) or info.is_dir()
                        or info.flag_bits & 0x1 or stat.S_IFMT(mode) == stat.S_IFLNK
                        or info.file_size <= 0 or info.file_size > MAX_MEMBER_BYTES):
                    raise AdapterError('unsafe_source_entry')
                total += info.file_size
                if total > MAX_UNPACKED_BYTES:
                    raise AdapterError('unpacked_size_limit')
                data = z.read(info)  # zipfile checks CRC before returning bytes
                key = (len(data), f'{zipfile.crc32(data) & 0xffffffff:08x}',
                       hashlib.sha1(data).hexdigest())
                index.setdefault(key, []).append((info.filename, data))
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
        raise AdapterError('unreadable_source_zip') from exc
    return index


def adapt(*, source: Path, driver_xml: Path, game: str,
          expected_source_sha256: str, expected_xml_sha256: str,
          output_zip: Path, manifest_json: Path) -> dict:
    """Write a private canonical ROM ZIP and manifest only after complete validation."""
    if output_zip == manifest_json or output_zip.exists() or manifest_json.exists():
        raise AdapterError('output_already_exists')
    if output_zip.is_symlink() or manifest_json.is_symlink():
        raise AdapterError('unsafe_output')
    parent = output_zip.parent.resolve(strict=True)
    if parent != manifest_json.parent.resolve(strict=True) or not parent.is_dir():
        raise AdapterError('output_parents_must_match')
    source_bytes = require_source(source, expected_source_sha256)
    xml_bytes = require_source(driver_xml, expected_xml_sha256)
    expected = expected_roms(driver_xml, game)
    index = source_members(source)
    mapping = []
    used = set()
    for target, size, crc, sha1 in expected:
        candidates = index.get((size, crc, sha1), [])
        if len(candidates) != 1:
            raise AdapterError('missing_or_ambiguous_rom_payload')
        actual, payload = candidates[0]
        if actual in used:
            raise AdapterError('duplicate_source_reuse')
        used.add(actual)
        mapping.append((target, actual, payload, size, crc, sha1))
    if sum(i[3] for i in mapping) > MAX_UNPACKED_BYTES:
        raise AdapterError('output_size_limit')
    with tempfile.TemporaryDirectory(prefix='.mame-private-adapter-', dir=parent) as temp:
        scratch = Path(temp)
        zip_tmp, manifest_tmp = scratch / 'dino.zip', scratch / 'manifest.json'
        with zipfile.ZipFile(zip_tmp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9,
                             allowZip64=False) as out:
            for target, _, payload, _, _, _ in mapping:
                info = zipfile.ZipInfo(filename=target, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                out.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        # Independent output readback; no filename-only matching.
        with zipfile.ZipFile(zip_tmp) as z:
            if set(z.namelist()) != {r[0] for r in mapping} or z.testzip() is not None:
                raise AdapterError('output_validation_failed')
            for target, _, _, size, crc, sha1 in mapping:
                data = z.read(target)
                if (len(data) != size or f'{zipfile.crc32(data)&0xffffffff:08x}' != crc or
                        hashlib.sha1(data).hexdigest() != sha1):
                    raise AdapterError('output_digest_mismatch')
        manifest = {
            'schema': 'mame0106-private-rom-archive-v1', 'game': game,
            'source_zip_sha256': expected_source_sha256.lower(), 'source_zip_bytes': source_bytes,
            'mame_driver_xml_sha256': expected_xml_sha256.lower(), 'driver_xml_bytes': xml_bytes,
            'source_members': sum(map(len,index.values())), 'selected_rom_count': len(mapping),
            'selected_rom_bytes': sum(x[3] for x in mapping),
            'output_zip_sha256': digest_path(zip_tmp), 'output_zip_bytes': zip_tmp.stat().st_size,
            'files': [{'original_name':src, 'mame0106_name':dst, 'size':size,
                       'crc32':crc, 'sha1':sha1} for dst,src,_,size,crc,sha1 in mapping],
            'method': 'exact SHA1 + CRC32 + size; names only; no ROM data changes',
            'tool': 'tools/mame0106_private_rom_name_adapter.py',
            'command': 'python -m tools.mame0106_private_rom_name_adapter --source <private-source-zip> --driver-xml <pinned-listxml> --game dino --source-sha256 <pinned-sha256> --xml-sha256 <pinned-sha256> --output-zip <private-new-dino.zip> --manifest <private-new-manifest.json>',
            'evidence': 'content matched; ROM verification and recording replay not performed',
        }
        manifest_tmp.write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        # Atomically refuse overwrite. Files always reside in scratch, never synced Drive.
        installed = []
        try:
            for src, dst in ((zip_tmp, output_zip), (manifest_tmp, manifest_json)):
                os.link(src, dst)
                installed.append(dst)
        except OSError as exc:
            # Do not automatically erase or replace an interrupted output.
            raise AdapterError('private_output_install_failed') from exc
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--driver-xml', type=Path, required=True)
    parser.add_argument('--game', default='dino')
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--xml-sha256', required=True)
    parser.add_argument('--output-zip', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    a = parser.parse_args(argv)
    try:
        data = adapt(source=a.source,driver_xml=a.driver_xml,game=a.game,
                     expected_source_sha256=a.source_sha256,
                     expected_xml_sha256=a.xml_sha256,output_zip=a.output_zip,
                     manifest_json=a.manifest)
        print('schema=mame0106-private-name-adapter-summary-v1')
        print('private_data_used=yes')
        print('sha1_crc32_size_matches=' + str(data['selected_rom_count']))
        print('source_member_count=' + str(data['source_members']))
        print('result=pass')
        return 0
    except (AdapterError, OSError, ValueError) as exc:
        print('schema=mame0106-private-name-adapter-summary-v1')
        print('result=fail')
        print('failure_class=' + type(exc).__name__)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())