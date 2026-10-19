"""ROM-free host-C vs Python parity for all CPS-1 background tile sizes."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.cps1_gfx import LANES, ROM_SIZE
from tools.cps1_private_multisize_tile_parity import (
    LAYOUTS, sampled_codes, private_multisize_tile_parity, main,
)


@unittest.skipUnless(shutil.which('gcc'), 'gcc required for native tests')
class AllNativeLayerTileTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.zip = self.root / 'SYNTHETIC_NOT_A_GAME.zip'

    def write_synthetic(self, *, missing=(), bad_size=()):
        with zipfile.ZipFile(self.zip, 'w', zipfile.ZIP_DEFLATED) as z:
            for i, (name, _) in enumerate(LANES):
                if name in missing:
                    continue
                size = ROM_SIZE - 1 if name in bad_size else ROM_SIZE
                pattern = bytes(((i*53 + j*11) ^ (j >> 2)) & 255
                                for j in range(512))
                z.writestr(name, (pattern*((size+511)//512))[:size])

    def test_stratified_samples_span_all_bank_boundaries(self):
        for _, _, _, _, limit in LAYOUTS:
            with self.subTest(limit=limit):
                codes = sampled_codes(limit)
                self.assertEqual(codes[0], 0)
                self.assertEqual(codes[-1], limit-1)
                self.assertIn(limit//2, codes)
                self.assertEqual(len(codes), len(set(codes)))
                self.assertGreater(len(codes), 250)

    def test_four_layouts_native_decompressor_equals_python(self):
        self.write_synthetic()
        report = private_multisize_tile_parity(self.zip)
        self.assertEqual(report['status'], 'PRIVATE_MULTISIZE_TILE_PARITY_PASSED')
        self.assertEqual(report['layouts_checked'], 4)
        self.assertEqual(report['assembled_graphics_region_bytes'], 0x400000)
        self.assertEqual(report['mismatching_tiles_total'], 0)
        self.assertTrue(report['invalid_native_codes_rejected'])
        self.assertEqual(report['sampled_tiles_total'],
                         sum(row['sampled_tiles'] for row in report['layer_results']))
        self.assertEqual(report['compared_pen_indices_total'],
                         sum(row['compared_pen_indices'] for row in report['layer_results']))
        self.assertFalse(report['runtime_palette_verified'])
        self.assertFalse(report['nintendo_switch_screen_parity_verified'])
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_intentionally_wrong_python_32x32_decode_is_detected(self):
        self.write_synthetic()
        from tools import cps1_private_multisize_tile_parity as module
        original = module.decode_tile
        def broken(region, layout, code):
            pix = bytearray(original(region, layout, code))
            if layout == '32x32':
                pix[0] ^= 1
            return bytes(pix)
        with patch.object(module, 'decode_tile', side_effect=broken):
            report = private_multisize_tile_parity(self.zip)
        self.assertEqual(report['status'], 'PRIVATE_MULTISIZE_TILE_DECODE_MISMATCH')
        self.assertGreater(report['mismatching_tiles_total'], 0)
        self.assertEqual(report['layer_results'][0]['mismatching_tiles'], 0)
        self.assertEqual(report['layer_results'][1]['mismatching_tiles'], 0)

    def test_missing_original_lane_refused_without_printing_path(self):
        self.write_synthetic(missing={LANES[0][0]})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([str(self.zip)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())['status'],
                         'PRIVATE_MULTISIZE_TILE_INPUT_OR_BUILD_REFUSED')
        self.assertNotIn(str(self.zip), out.getvalue())

    def test_wrong_member_length_refused_without_any_game_dump(self):
        self.write_synthetic(bad_size={LANES[2][0]})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main([str(self.zip)])
        self.assertEqual(code, 2)
        self.assertNotIn(str(self.root), out.getvalue())
        self.assertEqual(json.loads(out.getvalue())['status'],
                         'PRIVATE_MULTISIZE_TILE_INPUT_OR_BUILD_REFUSED')

    def test_private_diagnostics_do_not_create_source_rom_outputs(self):
        self.write_synthetic()
        before = set(self.root.iterdir())
        result = private_multisize_tile_parity(self.zip)
        self.assertEqual(result['status'], 'PRIVATE_MULTISIZE_TILE_PARITY_PASSED')
        self.assertEqual(set(self.root.iterdir()), before)
        self.assertFalse(result['source_rom_or_gfx_bytes_persisted'])


if __name__ == '__main__':
    unittest.main()
