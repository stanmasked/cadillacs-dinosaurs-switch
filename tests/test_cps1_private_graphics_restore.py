"""Entirely synthetic CPS-1 archive fixture; never reads original ROM bytes."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import zlib

from tools import cps1_private_graphics_restore as p


def chunk(tag, raw):
    return (struct.pack('>I', len(raw)) + tag + raw +
            struct.pack('>I', zlib.crc32(tag + raw) & 0xffffffff))


def png(size=256):
    rgba = bytes([0, 44, 55, 66, 255]) * (size * size)  # per-row filter is zero
    raw = b''.join(b'\0' + rgba[y * size * 5 + 1:y * size * 5 + 1 + size * 4]
                   for y in range(size))
    return (p.PNG_SIG + chunk(b'IHDR', struct.pack('>IIBBBBB',size,size,8,6,0,0,0)) +
            chunk(b'tEXt',b'Comment\0Artificial grayscale only') +
            chunk(b'IDAT',zlib.compress(raw)) + chunk(b'IEND',b''))


class RestorerTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.root = Path(self.t.name)
        self.archive = self.root / 'archive.zip'
        self.manifest = self.root / 'manifest.json'
        region = bytearray(p.GFX_BYTES)
        lanes = {}
        for i, (name, offset) in enumerate(p.LANES):
            sample = bytes([i+1]) * p.LANE_BYTES
            lanes[name] = p.sha256(sample)
            base = (i // 4) * p.BANK_BYTES + offset
            region[base:base+8*(p.LANE_BYTES//2):8] = sample[::2]
            region[base+1:base+1+8*(p.LANE_BYTES//2):8] = sample[1::2]
        self.content = {
            p.GRAPHICS: bytes(region),
            p.ATLASES[0]: png(),
            p.ATLASES[1]: png(),
        }
        self.obj = {
            'schema': 'dino-private-cps1-gfx-archive-v1',
            'graphics_roundtrip_complete':True,
            'frames_are_original_gameplay':False,
            'palettes_are_original':False,
            'graphics_region_size':p.GFX_BYTES,
            'source_lanes_count':8,
            'source_lane_sha256': lanes,
        }
        self.rewrite()

    def rewrite(self, extras=None, embedded_override=None):
        self.obj['files'] = {k:{'bytes':len(v),'sha256':p.sha256(v)}
                             for k,v in self.content.items()}
        self.obj['graphics_region_sha256'] = self.obj['files'][p.GRAPHICS]['sha256']
        self.manifest.write_text(json.dumps(self.obj, sort_keys=True), encoding='utf8')
        inner = (embedded_override if embedded_override is not None
                 else self.manifest.read_bytes())
        with zipfile.ZipFile(self.archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for k,v in self.content.items():
                z.writestr(k,v)
            z.writestr('manifest-private.json',inner)
            for k,v in (extras or {}).items():
                z.writestr(k,v)
        self.sha = p.checksum_file(self.archive)[0]
        self.msha = p.checksum_file(self.manifest)[0]

    def audit(self, **overrides):
        with patch.object(p,'guard_public_runner'):
            return p.audit(self.archive,self.manifest,archive_sha=overrides.get('archive_sha',self.sha),
                           manifest_sha=overrides.get('manifest_sha',self.msha))

    def restore(self, dest):
        with patch.object(p,'guard_public_runner'):
            return p.restore(self.archive,self.manifest,dest,
                             archive_sha=self.sha,manifest_sha=self.msha)

    def test_good_archived_graphics_round_trip(self):
        result = self.audit()
        self.assertEqual((result['source_lanes_verified'],result['members_verified'],
                          result['diagnostic_atlases_verified']),(8,4,2))
        self.assertEqual(result['gameplay_verified'],'no')

    def test_atomic_restoration_rechecks_bytes(self):
        dest = self.root / 'out'
        self.restore(dest)
        self.assertEqual({a.name for a in dest.iterdir()},p.MEMBERS)
        for name,raw in self.content.items():
            self.assertEqual((dest / name).read_bytes(),raw)

    def test_restore_refuses_existing_destination(self):
        dest = self.root / 'already'
        dest.mkdir()
        with self.assertRaisesRegex(p.RestoreError,'destination_already_exists'):
            self.restore(dest)
        self.assertEqual(list(dest.iterdir()),[])

    def test_public_runner_rejected_without_fixture_override(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            with self.assertRaisesRegex(p.RestoreError,'public_runner_forbidden'):
                p.audit(self.archive,self.manifest,archive_sha=self.sha,manifest_sha=self.msha)

    def test_outer_archive_digest_pin_refused(self):
        with self.assertRaisesRegex(p.RestoreError,'archive_digest_mismatch'):
            self.audit(archive_sha='f'*64)

    def test_outer_manifest_digest_pin_refused(self):
        with self.assertRaisesRegex(p.RestoreError,'manifest_digest_mismatch'):
            self.audit(manifest_sha='f'*64)

    def test_unexpected_archive_member_refused(self):
        self.rewrite(extras={'surplus.txt':b'This must be excluded'})
        with self.assertRaisesRegex(p.RestoreError,'unexpected_zip_inventory'):
            self.audit()

    def test_inner_manifest_must_match_external_pin(self):
        self.rewrite(embedded_override=b'{}')
        with self.assertRaisesRegex(p.RestoreError,'embedded_manifest_mismatch'):
            self.audit()

    def test_lane_inconsistency_refused_even_if_archive_and_manifest_repinned(self):
        data = bytearray(self.content[p.GRAPHICS]);data[0] ^= 1
        self.content[p.GRAPHICS] = bytes(data)
        self.rewrite()
        with self.assertRaisesRegex(p.RestoreError,'graphics_lane_roundtrip_mismatch'):
            self.audit()

    def test_png_dimensions_refused_even_with_new_checksums(self):
        self.content[p.ATLASES[0]] = png(128)
        self.rewrite()
        with self.assertRaisesRegex(p.RestoreError,'wrong_atlas_dimensions'):
            self.audit()

    def test_manifest_duplicate_top_level_field_refused(self):
        # Outer manifest pinned to these bytes; reject duplicate JSON keys.
        corrupt = b'{"schema":"a", "schema":"b"}'
        self.manifest.write_bytes(corrupt)
        self.msha = p.sha256(corrupt)
        with self.assertRaisesRegex(p.RestoreError,'duplicate_manifest_field'):
            self.audit()

    def test_private_sources_refuse_public_tree(self):
        with patch.object(p, 'REPO_ROOT', self.root):
            with patch.object(p, 'guard_public_runner'):
                with self.assertRaisesRegex(p.RestoreError, 'untrusted_source_file'):
                    p.audit(self.archive, self.manifest,
                            archive_sha=self.sha, manifest_sha=self.msha)

    def test_restore_target_must_stay_outside_public_tree(self):
        with patch.object(p, 'REPO_ROOT', self.root):
            with patch.object(p, 'guard_public_runner'):
                with self.assertRaisesRegex(p.RestoreError, 'invalid_destination_parent'):
                    p.restore(self.archive, self.manifest, self.root / 'target',
                              archive_sha=self.sha, manifest_sha=self.msha)

    def test_symlink_archive_refused(self):
        symlink = self.root/'linked.zip'
        symlink.symlink_to(self.archive)
        with patch.object(p,'guard_public_runner'):
            with self.assertRaisesRegex(p.RestoreError,'untrusted_source_file'):
                p.audit(symlink,self.manifest,archive_sha=self.sha,manifest_sha=self.msha)


if __name__ == '__main__':
    unittest.main()