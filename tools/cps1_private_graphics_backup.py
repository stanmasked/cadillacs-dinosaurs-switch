"""Create a private, reproducible archive of locally owned CPS-1 graphics.

The derived tiles, binary GFX region and full manifests are game content:
NEVER send them to public GitHub or GitHub Actions. No network operations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile

from tools.cps1_gfx import assemble_gfx, LANES, ROM_SIZE, BANK_SIZE
from tools.cps1_tiles import diagnostic_atlas

SOURCE_SHA_PATTERN = re.compile(r'[0-9a-fA-F]{64}\Z')
MAX_SOURCE_SIZE = 128 * 1024 * 1024
NAMES = ('graphics-region-4MiB.bin', 'atlas-16x16-grayscale.png',
         'atlas-32x32-grayscale.png', 'manifest-private.json')
ROM_REGION_BYTES = 4 * 1024 * 1024
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


class GraphicsArchiveError(Exception):
    """Never format private path names or bytes into the error message."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def source_audit(path: Path, expected_sha: str) -> tuple[bytes, dict]:
    if os.getenv('GITHUB_ACTIONS', '').lower() == 'true':
        raise GraphicsArchiveError('public_ci_private_asset_refused')
    if not SOURCE_SHA_PATTERN.fullmatch(expected_sha):
        raise GraphicsArchiveError('invalid_source_pin')
    if (path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_SOURCE_SIZE):
        raise GraphicsArchiveError('unsafe_source')
    if file_sha256(path) != expected_sha.lower():
        raise GraphicsArchiveError('source_digest_mismatch')
    lane_names = [name for name, _ in LANES]
    if len(lane_names) != len(set(lane_names)) or len(lane_names) != 8:
        raise GraphicsArchiveError('unsafe_layout_configuration')
    try:
        with zipfile.ZipFile(path) as src:
            info = src.infolist()
            if (len(info) > 512 or len(info) != len({a.filename for a in info}) or
                    any(a.is_dir() or (a.flag_bits & 1) or
                        stat.S_IFMT(a.external_attr >> 16) == stat.S_IFLNK or
                        a.file_size > 32*1024*1024 for a in info)):
                raise GraphicsArchiveError('unsafe_zip_inventory')
            available = set(src.namelist())
            if not set(lane_names).issubset(available):
                raise GraphicsArchiveError('missing_gfx_lanes')
            lanes = {}
            for name in lane_names:
                if src.getinfo(name).file_size != ROM_SIZE:
                    raise GraphicsArchiveError('unexpected_lane_length')
                content = src.read(name)
                if len(content) != ROM_SIZE:
                    raise GraphicsArchiveError('unexpected_lane_length')
                lanes[name] = content
    except (zipfile.BadZipFile, EOFError, RuntimeError, OSError) as exc:
        raise GraphicsArchiveError('corrupt_source_zip') from exc
    region = assemble_gfx(lanes.__getitem__)
    if len(region) != ROM_REGION_BYTES:
        raise GraphicsArchiveError('unexpected_gfx_region_size')
    for i, (name, lane) in enumerate(LANES):
        pos = (i // 4) * BANK_SIZE + lane
        recovered = bytearray(ROM_SIZE)
        recovered[::2] = region[pos:pos + 8*(ROM_SIZE//2):8]
        recovered[1::2] = region[pos+1:pos+1 + 8*(ROM_SIZE//2):8]
        if bytes(recovered) != lanes[name]:
            raise GraphicsArchiveError('gfx_lane_roundtrip_mismatch')
    report = {'schema':'dino-private-cps1-gfx-archive-v1',
              'source_archive_sha256':expected_sha.lower(),
              'source_archive_bytes':path.stat().st_size,
              'source_lanes_count':len(lanes),
              'source_lane_sha256':{name:sha256(lanes[name]) for name in lane_names},
              'graphics_region_size':len(region),
              'graphics_region_sha256':sha256(region),
              'graphics_roundtrip_complete':True,
              'palettes_are_original':False,
              'frames_are_original_gameplay':False,
              'storage':'private_owner_only_google_drive'}
    return region, report


def archive_payloads(region: bytes, manifest: dict) -> dict[str, bytes]:
    png16 = diagnostic_atlas(region, '16x16', start=0, count=64, columns=8, scale=2)
    png32 = diagnostic_atlas(region, '32x32', start=0, count=64, columns=8, scale=1)
    payloads = dict(zip(NAMES[:3], (region, png16, png32)))
    manifest = {**manifest, 'files': {name: {'bytes':len(b), 'sha256':sha256(b)}
                                      for name,b in payloads.items()},
                'extraction_method':'tools.cps1_gfx.assemble_gfx + tools.cps1_tiles.diagnostic_atlas',
                'options':{'layouts':['16x16','32x32'], 'count':64, 'columns':8,
                           'scale16':2, 'scale32':1}}
    payloads[NAMES[3]] = (json.dumps(manifest, sort_keys=True, indent=2)+'\n').encode()
    return payloads


def create_backup(source: Path, archive: Path, manifest_path: Path,
                  source_sha: str) -> dict:
    if os.getenv('GITHUB_ACTIONS', '').lower() == 'true':
        raise GraphicsArchiveError('public_ci_private_asset_refused')
    root = Path(__file__).resolve().parents[1]
    for dest in (archive, manifest_path):
        if dest.exists() or dest.is_symlink():
            raise GraphicsArchiveError('output_already_exists')
        if root == dest.resolve() or root in dest.resolve().parents:
            raise GraphicsArchiveError('output_inside_public_source_tree')
        if not dest.parent.exists() or dest.parent.is_symlink() or not dest.parent.is_dir():
            raise GraphicsArchiveError('invalid_output_parent')
    if archive == manifest_path:
        raise GraphicsArchiveError('output_paths_duplicate')
    region, manifest = source_audit(source, source_sha)
    payloads = archive_payloads(region, manifest)
    parent = archive.parent.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='private-cps1-backup-', dir=parent) as temporary:
        staged_zip = Path(temporary)/'backup.zip'
        with zipfile.ZipFile(staged_zip, 'x') as out:
            for name in NAMES:
                entry = zipfile.ZipInfo(name, FIXED_TIME)
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.external_attr = 0o600 << 16
                out.writestr(entry, payloads[name], compress_type=zipfile.ZIP_DEFLATED,
                             compresslevel=9)
        with zipfile.ZipFile(staged_zip) as verify:
            if verify.namelist() != list(NAMES):
                raise GraphicsArchiveError('archive_inventory_mismatch')
            for name in NAMES:
                if verify.read(name) != payloads[name]:
                    raise GraphicsArchiveError('archive_member_readback_mismatch')
        archive_sha = file_sha256(staged_zip)
        staged_manifest = Path(temporary) / 'private-manifest.json'
        staged_manifest.write_bytes(payloads[NAMES[3]])
        # Both outputs are published with exclusive create; never overwrite.
        try:
            with archive.open('xb') as target, staged_zip.open('rb') as src:
                for block in iter(lambda: src.read(1024 * 1024), b''):
                    target.write(block)
            with manifest_path.open('xb') as dest:
                dest.write(payloads[NAMES[3]])
        except OSError as exc:
            # Retain .pending or partial copies for manual investigation.
            raise GraphicsArchiveError('publication_interrupted_inspect_outputs') from exc
    return {'status':'verified_private_archive', 'archive_bytes':archive.stat().st_size,
            'archive_sha256':archive_sha,
            'entries_verified':len(NAMES),'gfx_region_bytes':len(region),
            'grayscale_atlas_count':2, 'gameplay_frames_captured':0}


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-zip', required=True, type=Path)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--archive', required=True,type=Path)
    parser.add_argument('--manifest', required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        report=create_backup(args.source_zip,args.archive,args.manifest,args.source_sha256)
        print(json.dumps(report,sort_keys=True))
        return 0
    except (GraphicsArchiveError,OSError,ValueError) as exc:
        print('result=fail')
        print('failure_class='+type(exc).__name__)
        return 1

if __name__=='__main__':
    sys.exit(main())