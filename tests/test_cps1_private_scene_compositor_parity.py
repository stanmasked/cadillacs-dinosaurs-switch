"""ROM-free controlled CPS-1 native scene/Python pixel compositor tests."""
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
from tools.cps1_private_scene_compositor_parity import (
    CASES, PIXELS, synthetic_scene, compare_private_native_scene_compositor,
    main,
)


@unittest.skipUnless(shutil.which('gcc'), 'GCC required for ROM-free C parity')
class NativeSceneCompositorParityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.archive = self.root / 'SYNTHETIC_NOT_REAL_GAME.zip'

    def write_fake_archive(self, *, missing=(), short=()):
        with zipfile.ZipFile(
                self.archive, 'w', compression=zipfile.ZIP_DEFLATED) as out:
            for i, (name, _) in enumerate(LANES):
                if name in missing:
                    continue
                length = ROM_SIZE - 1 if name in short else ROM_SIZE
                pattern = bytes((((j * 17) ^ (j // 11) ^ (i * 31)) & 255)
                                for j in range(512))
                out.writestr(name, (pattern*((length+511)//512))[:length])

    def test_synthetic_priority_and_palette_scenarios_are_distinct(self):
        self.assertEqual(len(CASES), 4)
        a = synthetic_scene('priority_sprite')
        b = synthetic_scene('unmasked_sprite')
        c = synthetic_scene('rowscroll_flip')
        d = synthetic_scene('sprite_under_layers')
        self.assertEqual(a['priority_masks'], [0x00a6, 0x0f0f, 0x1111, 0x8000])
        self.assertEqual(b['priority_masks'], [0, 0, 0, 0])
        self.assertNotEqual(a['layer_control'], c['layer_control'])
        self.assertNotEqual(d['layer_control'], a['layer_control'])
        self.assertIn('rowscroll', c)
        self.assertEqual(len(c['rowscroll']), 1024)
        self.assertEqual(len(a['palette_rgb']), 3072)
        self.assertEqual(a['buffered_obj_words'][-1], 0xff00)
        self.assertNotIn('rowscroll', a)

    def test_actual_native_compositor_matches_python_on_fake_gfx(self):
        self.write_fake_archive()
        result = compare_private_native_scene_compositor(self.archive)
        self.assertEqual(result['status'], 'PRIVATE_NATIVE_SCENE_PARITY_PASSED')
        self.assertEqual(result['synthetic_cases'], 4)
        self.assertEqual(result['pixels_compared'], 4*PIXELS)
        self.assertEqual(result['mismatching_pixels_total'], 0)
        self.assertTrue(result['palette_scroll_obj_and_priority_are_synthetic'])
        self.assertFalse(result['original_game_frame_captured'])
        self.assertFalse(result['sprite_latch_timing_verified'])
        self.assertFalse(result['nintendo_switch_framebuffer_parity_verified'])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_tampered_python_reference_does_not_pass(self):
        self.write_fake_archive()
        from tools import cps1_private_scene_compositor_parity as mod
        original = mod.render_frame
        def wrong(gfx, palette, snapshot):
            pixels = bytearray(original(gfx, palette, snapshot))
            pixels[0] ^= 1
            return bytes(pixels)
        with patch.object(mod, 'render_frame', side_effect=wrong):
            report = compare_private_native_scene_compositor(self.archive)
        self.assertEqual(report['status'], 'PRIVATE_NATIVE_SCENE_PARITY_MISMATCH')
        self.assertEqual(report['mismatching_pixels_total'], 4)

    def test_rom_not_persisted_as_extracted_scene_or_rgba(self):
        self.write_fake_archive()
        before = set(self.root.iterdir())
        report = compare_private_native_scene_compositor(self.archive)
        self.assertEqual(report['status'], 'PRIVATE_NATIVE_SCENE_PARITY_PASSED')
        self.assertEqual(set(self.root.iterdir()), before)
        self.assertFalse(report['source_rom_or_derived_pixel_bytes_written_to_disk'])

    def test_missing_private_zip_lane_returns_fixed_refusal(self):
        self.write_fake_archive(missing={LANES[2][0]})
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            code = main([str(self.archive)])
        self.assertEqual(code, 2)
        out = json.loads(text.getvalue())
        self.assertEqual(out['status'], 'PRIVATE_NATIVE_SCENE_INPUT_OR_BUILD_REFUSED')
        self.assertNotIn(str(self.root), text.getvalue())

    def test_invalid_rom_lane_size_cannot_produce_game_frame(self):
        self.write_fake_archive(short={LANES[-1][0]})
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            code = main([str(self.archive)])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(text.getvalue())['original_game_frame_captured'])

    def test_nonexistent_original_path_and_exception_are_redacted(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main([str(self.root / 'PRIVATE_SECRET_OWNED_ROM.zip')])
        self.assertEqual(code, 2)
        self.assertNotIn('PRIVATE_SECRET_OWNED_ROM', stdout.getvalue())

    def test_native_compile_failure_does_not_expose_compiler_text(self):
        self.write_fake_archive()
        stdout = io.StringIO()
        with patch('tools.cps1_private_scene_compositor_parity._compile_scene',
                   side_effect=RuntimeError('PRIVATE ORIGINAL ROM SECRET')), \
             contextlib.redirect_stdout(stdout):
            code = main([str(self.archive)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())['status'],
                         'PRIVATE_NATIVE_SCENE_INPUT_OR_BUILD_REFUSED')
        self.assertNotIn('SECRET', stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
