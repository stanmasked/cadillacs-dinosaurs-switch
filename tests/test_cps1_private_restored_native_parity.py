"""Strictly synthesized CPS-1 graphics only. No real assets in public CI."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import cps1_private_restored_native_parity as p


class PrivateRecoveredGfxNativeParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='stage365-synthetic-')
        cls.gfx = Path(cls.tmp.name)/'fixture_gfx.bin'
        # Four deterministic 4-bit patterns in deliberately non-game 4-MiB bytes.
        cls.gfx.write_bytes(bytes(range(256)) * (p.GFX_BYTES // 256))
        cls.gfxsha = p.sha_file(cls.gfx)
        cls.src = p.REPO_ROOT/'source'/'cps1_tile.c'
        cls.hdr = p.REPO_ROOT/'source'/'cps1_tile.h'
        cls.srcsha = p.sha_file(cls.src)
        cls.hdrsha = p.sha_file(cls.hdr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def safe(self, action, *args, **kwargs):
        with patch.object(p, 'guard_private'):
            return action(*args, **kwargs)

    def test_public_actions_denied_before_read(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS':'true'}):
            with self.assertRaisesRegex(p.PrivateParityError, 'public_runner_forbidden'):
                p.verify_gfx(self.gfx, self.gfxsha)

    def test_synthetic_sha_pinned_fixture(self):
        self.assertEqual(self.safe(p.verify_gfx, self.gfx, self.gfxsha)[:4], b'\0\1\2\3')

    def test_corrupted_file_refused_without_repin(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td)/'gfx.bin'
            raw = bytearray(self.gfx.read_bytes())
            raw[1234] ^= 0x40
            bad.write_bytes(raw)
            with self.assertRaisesRegex(p.PrivateParityError, 'gfx_digest_mismatch'):
                self.safe(p.verify_gfx, bad, self.gfxsha)

    def test_short_gfx_refused(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td)/'gfx.bin'
            bad.write_bytes(b'synthetic' * 17)
            with self.assertRaisesRegex(p.PrivateParityError, 'wrong_gfx_length'):
                self.safe(p.verify_gfx, bad, p.sha_file(bad))

    def test_bad_digest_pin_refused(self):
        with self.assertRaisesRegex(p.PrivateParityError, 'invalid_gfx_pin'):
            self.safe(p.verify_gfx, self.gfx, 'fake')

    def test_gfx_symlink_refused(self):
        with tempfile.TemporaryDirectory() as td:
            link = Path(td)/'link.bin'
            link.symlink_to(self.gfx)
            with self.assertRaisesRegex(p.PrivateParityError, 'invalid_gfx_source'):
                self.safe(p.verify_gfx, link, self.gfxsha)

    def test_native_source_pin_and_tamper_rejection(self):
        p.verify_native_sources(self.src, self.hdr, self.srcsha, self.hdrsha)
        with self.assertRaisesRegex(p.PrivateParityError, 'native_source_digest_mismatch'):
            p.verify_native_sources(self.src, self.hdr, '0'*64, self.hdrsha)

    def test_sample_code_repeatability_and_sentinels(self):
        for cap in (8192,32768,65536):
            a = p.sample_codes(cap, count=1024)
            self.assertEqual(a, p.sample_codes(cap, count=1024))
            self.assertEqual(len(a), 1024)
            self.assertEqual((a[0],a[-1]),(0,cap-1))
            self.assertIn(cap//2, a)
            self.assertEqual(len(set(a)),len(a))

    def test_invalid_sample_count_refused(self):
        for count in (0,4097,-5):
            with self.assertRaises(p.PrivateParityError):
                p.sample_codes(32768, count=count)

    def test_independent_reference_planar_decode(self):
        region = bytes([255,0,0,0,0,255,0,0] * 16)
        self.assertEqual(p.reference(region,16,0,0)[:8],b'\x08'*8)
        self.assertEqual(p.reference(region,16,0,0)[8:16],b'\x04'*8)
        with self.assertRaises(p.PrivateParityError):
            p.reference(region,24,0,0)

    def test_native_vs_reference_synthetic_all_four_layouts(self):
        synthetic = self.safe(p.verify_gfx, self.gfx, self.gfxsha)
        summary = self.safe(p.parity, synthetic, self.src, self.hdr, samples=16)
        self.assertEqual(summary['status'], 'pass')
        self.assertEqual(summary['layouts_checked'],4)
        self.assertEqual(summary['tiles_compared'],64)
        self.assertEqual(summary['mismatching_tiles'],0)
        self.assertTrue(summary['invalid_native_codes_rejected'])
        self.assertFalse(summary['gameplay_frames_captured'])

    def test_forced_reference_mismatch_detected(self):
        synthetic = self.safe(p.verify_gfx, self.gfx, self.gfxsha)
        original = p.reference
        def poisoned(*args):
            data = original(*args)
            return bytes([data[0]^1])+data[1:]
        with patch.object(p, 'reference', side_effect=poisoned):
            summary = self.safe(p.parity, synthetic, self.src, self.hdr, samples=16)
        self.assertEqual(summary['status'],'fail')
        self.assertEqual(summary['mismatching_tiles'],64)

    def test_no_raw_game_data_in_aggregates(self):
        synthetic = self.safe(p.verify_gfx, self.gfx, self.gfxsha)
        summary = self.safe(p.parity, synthetic, self.src, self.hdr, samples=16)
        self.assertNotIn('sha256', str(summary).lower())
        self.assertNotIn(str(self.gfx), str(summary))
        self.assertNotIn('pixel_samples', str(summary))


if __name__ == '__main__':
    unittest.main()