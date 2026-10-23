"""Audit and atomically restore owner-held CPS-1 GFX backups, OFFLINE ONLY.

The complete graphics region and atlas pixels are private owner assets.
No archive content, private path, or member digests may be logged publicly.
Synthetic fixture tests are allowed; real data MUST NOT enter GitHub Actions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import tempfile
import zipfile
import zlib

MEMBERS = frozenset((
    'graphics-region-4MiB.bin', 'atlas-16x16-grayscale.png',
    'atlas-32x32-grayscale.png', 'manifest-private.json',
))
GRAPHICS = 'graphics-region-4MiB.bin'
ATLASES = ('atlas-16x16-grayscale.png', 'atlas-32x32-grayscale.png')
LANES = (
    ('cd-1m.3a', 0), ('cd-3m.5a', 2), ('cd-2m.4a', 4), ('cd-4m.6a', 6),
    ('cd-5m.7a', 0), ('cd-7m.9a', 2), ('cd-6m.8a', 4), ('cd-8m.10a', 6),
)
LANE_BYTES = 524288
BANK_BYTES = 0x200000
GFX_BYTES = BANK_BYTES * 2
MAX_ZIP_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 32 * 1024
MAX_UNCOMPRESSED_BYTES = GFX_BYTES + 4 * 1024 * 1024
SHA = re.compile(r'[a-f0-9]{64}\Z')
PNG_SIG = b'\x89PNG\r\n\x1a\n'
REPO_ROOT = Path(__file__).resolve().parents[1]


class RestoreError(Exception):
    """Only fixed private-data-safe identifiers are included in error messages."""


def guard_public_runner() -> None:
    if os.getenv('GITHUB_ACTIONS', '').lower() == 'true':
        raise RestoreError('public_runner_forbidden')


def outside_public_tree(path: Path) -> bool:
    resolved = path.resolve()
    return resolved != REPO_ROOT and REPO_ROOT not in resolved.parents


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def checksum_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def pairs_unique(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise RestoreError('duplicate_manifest_field')
        obj[k] = v
    return obj


def validate_manifest(raw: bytes, expected_manifest_sha: str) -> dict:
    if sha256(raw) != expected_manifest_sha:
        raise RestoreError('manifest_digest_mismatch')
    try:
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs_unique)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise RestoreError('invalid_manifest') from exc
    if (not isinstance(data, dict) or data.get('schema') != 'dino-private-cps1-gfx-archive-v1'
            or data.get('graphics_roundtrip_complete') is not True
            or data.get('frames_are_original_gameplay') is not False
            or data.get('palettes_are_original') is not False
            or data.get('source_lanes_count') != 8
            or data.get('graphics_region_size') != GFX_BYTES):
        raise RestoreError('invalid_archive_provenance')
    records = data.get('files')
    lanes = data.get('source_lane_sha256')
    if (not isinstance(records, dict) or set(records) != MEMBERS - {'manifest-private.json'}
            or not isinstance(lanes, dict) or set(lanes) != {n for n, _ in LANES}):
        raise RestoreError('invalid_manifest_inventory')
    for item in records.values():
        if (not isinstance(item, dict) or type(item.get('bytes')) is not int
                or not 1 <= item['bytes'] <= GFX_BYTES
                or not isinstance(item.get('sha256'), str)
                or SHA.fullmatch(item['sha256']) is None):
            raise RestoreError('invalid_manifest_member')
    if (records[GRAPHICS]['bytes'] != GFX_BYTES
            or data.get('graphics_region_sha256') != records[GRAPHICS]['sha256']
            or any(not isinstance(d, str) or SHA.fullmatch(d) is None
                   for d in lanes.values())):
        raise RestoreError('invalid_manifest_graphics')
    return data


def verify_png(raw: bytes) -> None:
    """Bounds-checked PNG container/scanline checks, not proof of real palette."""
    if len(raw) < 45 or raw[:8] != PNG_SIG:
        raise RestoreError('invalid_png')
    pos = 8
    names = []
    idat = []
    while pos + 12 <= len(raw):
        n = struct.unpack_from('>I', raw, pos)[0]
        tag = raw[pos + 4:pos + 8]
        if n > 1024 * 1024 or pos + 12 + n > len(raw):
            raise RestoreError('invalid_png_chunk')
        content = raw[pos + 8:pos + 8 + n]
        crc = struct.unpack_from('>I', raw, pos + 8 + n)[0]
        if zlib.crc32(tag + content) & 0xffffffff != crc:
            raise RestoreError('invalid_png_crc')
        names.append(tag)
        if len(names) == 1:
            if tag != b'IHDR' or n != 13:
                raise RestoreError('invalid_png_header')
            w, h, depth, color, comp, filt, interlace = struct.unpack('>IIBBBBB', content)
            if (w, h, depth, color, comp, filt, interlace) != (256, 256, 8, 6, 0, 0, 0):
                raise RestoreError('wrong_atlas_dimensions')
        if tag == b'IDAT':
            idat.append(content)
        if tag == b'IEND':
            if n != 0 or pos + 12 != len(raw):
                raise RestoreError('invalid_png_end')
            break
        pos += 12 + n
    if (names.count(b'IHDR') != 1 or names.count(b'IEND') != 1
            or not idat or any(x not in (b'IHDR', b'tEXt', b'IDAT', b'IEND') for x in names)):
        raise RestoreError('invalid_png_layout')
    limit = 256 * (256 * 4 + 1)
    try:
        dec = zlib.decompressobj()
        out = dec.decompress(b''.join(idat), limit + 1)
        if (len(out) != limit or dec.unconsumed_tail or dec.unused_data or not dec.eof
                or any(out[row * (1 + 1024)] > 4 for row in range(256))):
            raise RestoreError('invalid_png_scanlines')
    except zlib.error as exc:
        raise RestoreError('invalid_png_deflate') from exc


def verify_lanes(region: bytes, checksums: dict[str, str]) -> int:
    if len(region) != GFX_BYTES:
        raise RestoreError('wrong_graphics_region_size')
    for i, (name, lane) in enumerate(LANES):
        base = (i // 4) * BANK_BYTES + lane
        restored = bytearray(LANE_BYTES)
        restored[::2] = region[base:base + 8 * (LANE_BYTES // 2):8]
        restored[1::2] = region[base + 1:base + 1 + 8 * (LANE_BYTES // 2):8]
        if len(restored) != LANE_BYTES or sha256(restored) != checksums[name]:
            raise RestoreError('graphics_lane_roundtrip_mismatch')
    return 8


def audit(archive: Path, manifest: Path, *, archive_sha: str, manifest_sha: str) -> dict[str, int | str]:
    guard_public_runner()
    if (not isinstance(archive_sha, str) or not isinstance(manifest_sha, str)
            or SHA.fullmatch(archive_sha) is None or SHA.fullmatch(manifest_sha) is None):
        raise RestoreError('invalid_external_digest_pin')
    if (not outside_public_tree(archive) or not outside_public_tree(manifest)
            or archive.is_symlink() or manifest.is_symlink() or not archive.is_file()
            or not manifest.is_file() or not 0 < archive.stat().st_size <= MAX_ZIP_BYTES
            or not 0 < manifest.stat().st_size <= MAX_MANIFEST_BYTES):
        raise RestoreError('untrusted_source_file')
    actual_sha, zipbytes = checksum_file(archive)
    if actual_sha != archive_sha:
        raise RestoreError('archive_digest_mismatch')
    manifest_data = manifest.read_bytes()
    parsed = validate_manifest(manifest_data, manifest_sha)
    try:
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            if (len(infos) != len(MEMBERS) or {x.filename for x in infos} != MEMBERS):
                raise RestoreError('unexpected_zip_inventory')
            if sum(x.file_size for x in infos) > MAX_UNCOMPRESSED_BYTES:
                raise RestoreError('archive_uncompressed_limit')
            result = {}
            for item in infos:
                if (item.is_dir() or item.flag_bits & 1 or item.file_size < 1
                        or item.file_size > GFX_BYTES
                        or stat.S_IFMT(item.external_attr >> 16) == stat.S_IFLNK):
                    raise RestoreError('unsafe_zip_entry')
                raw = z.read(item)
                if len(raw) != item.file_size:
                    raise RestoreError('zip_entry_length_mismatch')
                if item.filename == 'manifest-private.json':
                    if raw != manifest_data:
                        raise RestoreError('embedded_manifest_mismatch')
                else:
                    expected = parsed['files'][item.filename]
                    if len(raw) != expected['bytes'] or sha256(raw) != expected['sha256']:
                        raise RestoreError('zip_member_digest_mismatch')
                result[item.filename] = raw
            verified_lanes = verify_lanes(result[GRAPHICS], parsed['source_lane_sha256'])
            for name in ATLASES:
                verify_png(result[name])
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError, ValueError) as exc:
        raise RestoreError('corrupt_private_archive') from exc
    return {'schema': 'dino-cps1-private-graphics-restore-v1',
            'archive_bytes': zipbytes, 'members_verified': len(MEMBERS),
            'graphics_region_bytes': GFX_BYTES, 'source_lanes_verified': verified_lanes,
            'diagnostic_atlases_verified': len(ATLASES), 'result': 'pass',
            'gameplay_verified': 'no'}


def restore(archive: Path, manifest: Path, destination: Path, *, archive_sha: str,
            manifest_sha: str) -> dict[str, int | str]:
    if destination.exists() or destination.is_symlink():
        raise RestoreError('destination_already_exists')
    parent = destination.parent.resolve(strict=True)
    if not parent.is_dir() or not outside_public_tree(parent):
        raise RestoreError('invalid_destination_parent')
    info = audit(archive, manifest, archive_sha=archive_sha, manifest_sha=manifest_sha)
    with tempfile.TemporaryDirectory(dir=parent, prefix='.cps1-gfx-restore-') as staging:
        ready = Path(staging) / 'graphics'
        ready.mkdir(mode=0o700)
        with zipfile.ZipFile(archive) as z:
            for name in sorted(MEMBERS):
                with z.open(name) as read, (ready / name).open('xb') as write:
                    shutil.copyfileobj(read, write, 1024 * 1024)
        # Mandatory second check after extract; don't publish failed scratch.
        for name in MEMBERS - {'manifest-private.json'}:
            expected = json.loads(manifest.read_text(encoding='utf-8'))['files'][name]
            checksum, size = checksum_file(ready / name)
            if checksum != expected['sha256'] or size != expected['bytes']:
                raise RestoreError('restored_data_mismatch')
        if (ready / 'manifest-private.json').read_bytes() != manifest.read_bytes():
            raise RestoreError('restored_manifest_mismatch')
        os.replace(ready, destination)
    return info


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--archive', type=Path, required=True)
    ap.add_argument('--manifest', type=Path, required=True)
    ap.add_argument('--archive-sha256', required=True)
    ap.add_argument('--manifest-sha256', required=True)
    ap.add_argument('--restore-to', type=Path)
    args = ap.parse_args(argv)
    try:
        opts = {'archive_sha': args.archive_sha256, 'manifest_sha': args.manifest_sha256}
        result = (restore(args.archive, args.manifest, args.restore_to, **opts)
                  if args.restore_to else audit(args.archive, args.manifest, **opts))
        for key, value in result.items():
            print(f'{key}={value}')
        print('restored=' + ('yes' if args.restore_to else 'no'))
        return 0
    except (RestoreError, OSError) as exc:
        print('schema=dino-cps1-private-graphics-restore-v1')
        print('result=fail')
        print('failure_class=' + (str(exc) if isinstance(exc, RestoreError) else 'filesystem_failure'))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())