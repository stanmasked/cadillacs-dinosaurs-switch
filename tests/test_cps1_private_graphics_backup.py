"""Synthetic-only tests for the private graphics archive; no actual game files."""
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest
import zipfile
from tools.cps1_gfx import LANES, ROM_SIZE
from tools import cps1_private_graphics_backup as p


class PrivateCps1ArchiveTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix='gfx-synthetic-test-')
        self.addCleanup(t.cleanup)
        self.work=Path(t.name)
        self.source=self.work/'synthetic-input.zip'
        self.create_fixture()

    def create_fixture(self, extra=None, missing=None, corrupt=None):
        with zipfile.ZipFile(self.source,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for i,(name,_) in enumerate(LANES):
                if name==missing:continue
                data=(bytes(((k * 13 + i * 7) % 256 for k in range(256))) *
                      (ROM_SIZE//256))
                if corrupt==name:data=data[:-1]
                z.writestr(name,data)
            if extra:
                z.writestr(extra, b'not-original')
        self.sha=p.file_sha256(self.source)

    def audit_synthetic(self, sha=None):
        # Only synthetic fixtures bypass the actual private-processing guard.
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
            return p.source_audit(self.source, sha or self.sha)

    def test_graphics_eight_lanes_exact_roundtrip(self):
        region, result=self.audit_synthetic()
        self.assertEqual(len(region),4194304)
        self.assertTrue(result['graphics_roundtrip_complete'])
        self.assertEqual(result['source_lanes_count'],8)

    def test_palette_marked_diagnostic_not_real_gameplay(self):
        region, report=self.audit_synthetic()
        members=p.archive_payloads(region,report)
        self.assertEqual(set(members),set(p.NAMES))
        self.assertEqual(members['atlas-16x16-grayscale.png'][:8],b'\x89PNG\r\n\x1a\n')
        self.assertEqual(members['atlas-32x32-grayscale.png'][:8],b'\x89PNG\r\n\x1a\n')
        manifest=json.loads(members['manifest-private.json'])
        self.assertFalse(manifest['frames_are_original_gameplay'])
        self.assertFalse(manifest['palettes_are_original'])

    def test_fixed_wrong_source_sha_refused(self):
        with self.assertRaisesRegex(p.GraphicsArchiveError,'source_digest_mismatch'):
            self.audit_synthetic('0'*64)

    def test_missing_lane_fails_closed(self):
        self.create_fixture(missing=LANES[3][0])
        with self.assertRaisesRegex(p.GraphicsArchiveError,'missing_gfx_lanes'):
            self.audit_synthetic()

    def test_truncated_lane_fails_closed(self):
        self.create_fixture(corrupt=LANES[2][0])
        with self.assertRaisesRegex(p.GraphicsArchiveError,'unexpected_lane_length'):
            self.audit_synthetic()

    def test_public_ci_rejected_even_with_matching_synthetic_pin(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS':'true'}):
            with self.assertRaisesRegex(p.GraphicsArchiveError,'public_ci_private_asset_refused'):
                p.source_audit(self.source,self.sha)

    def test_duplicate_entry_fails_closed(self):
        with zipfile.ZipFile(self.source,'a') as z:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',UserWarning)
                z.writestr(LANES[0][0],b'duplicate')
        self.sha=p.file_sha256(self.source)
        with self.assertRaisesRegex(p.GraphicsArchiveError,'unsafe_zip_inventory'):
            self.audit_synthetic()

    def test_output_never_overwrites_existing(self):
        out=self.work/'already.zip';out.write_bytes(b'existing')
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
            with self.assertRaisesRegex(p.GraphicsArchiveError,'output_already_exists'):
                p.create_backup(self.source,out,self.work/'new.json',self.sha)
        self.assertEqual(out.read_bytes(),b'existing')

    def test_deterministic_backup_zip(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
            # Fixtures are not game data; outputs under external tempfile root.
            out1,out2=self.work/'one.zip',self.work/'two.zip'
            m1,m2=self.work/'one.json',self.work/'two.json'
            r1=p.create_backup(self.source,out1,m1,self.sha)
            r2=p.create_backup(self.source,out2,m2,self.sha)
        self.assertEqual(out1.read_bytes(),out2.read_bytes())
        self.assertEqual(m1.read_bytes(),m2.read_bytes())
        self.assertEqual(r1['archive_sha256'],r2['archive_sha256'])
        self.assertEqual(r1['entries_verified'],4)
        self.assertEqual(r1['gameplay_frames_captured'],0)

if __name__=='__main__':unittest.main()