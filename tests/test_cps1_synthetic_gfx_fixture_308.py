"""Stage308: full ROM-free CPS-1 graphics plus Stage307 Switch scenes."""
import ctypes
import io
import json
import shutil
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from pathlib import Path

from tools import cps1_synthetic_gfx_fixture_308 as fixture
from tools import cps1_synthetic_scene_sequence_307 as timeline
from tools import cps1_private_scene_compositor_parity as scenes
from tools import cps1_private_native_tile_parity as tiles
from tools import cps1_sequence_export as packing
from tools.cps1_frame import render_frame


class Stage308SyntheticGraphicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gfx, cls.report = fixture.build()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="dino308-artificial-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_exact_native_region_length_and_unmistakable_fake_marker(self):
        self.assertEqual(len(self.gfx), 0x400000)
        self.assertEqual(self.gfx[:len(fixture.MARKER)], fixture.MARKER)
        self.assertEqual(self.gfx[fixture.PERIOD_BYTES:
                                  fixture.PERIOD_BYTES + len(fixture.MARKER)],
                         fixture.MARKER)

    def test_repeated_period_is_explicit_and_exact(self):
        self.assertEqual(self.gfx, self.gfx[:fixture.PERIOD_BYTES] *
                         (fixture.REGION_BYTES // fixture.PERIOD_BYTES))
        self.assertNotEqual(self.gfx[:128], self.gfx[128:256])

    def test_deterministic_independent_generation(self):
        regenerated, report = fixture.build()
        self.assertEqual(regenerated, self.gfx)
        self.assertEqual(report, self.report)

    def test_artificial_16x16_tiles_use_all_four_bit_pens(self):
        pens = set()
        for code in range(10):
            pixels = tiles.python_reference_tile(self.gfx, code)
            self.assertEqual(len(pixels), 256)
            pens.update(pixels)
        self.assertEqual(pens, set(range(16)))

    def test_private_exclusive_write_and_readback(self):
        target = self.root / "gfx.bin"
        timeline._write_exclusive(target, self.gfx)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.read_bytes(), self.gfx)
        with self.assertRaises(ValueError):
            timeline._write_exclusive(target, b"corrupt")
        self.assertEqual(target.read_bytes(), self.gfx)

    def test_symlinked_target_and_parent_are_refused(self):
        sentinel = self.root / "sentinel"
        sentinel.write_bytes(b"preserve")
        symlink = self.root / "gfx-link.bin"
        symlink.symlink_to(sentinel)
        with self.assertRaises(ValueError):
            timeline._write_exclusive(symlink, self.gfx)
        actual_dir = self.root / "real"
        actual_dir.mkdir()
        link_dir = self.root / "linked"
        link_dir.symlink_to(actual_dir, target_is_directory=True)
        with self.assertRaises(ValueError):
            timeline._write_exclusive(link_dir / "gfx.bin", self.gfx)
        self.assertEqual(sentinel.read_bytes(), b"preserve")

    def test_cli_produces_only_private_fake_graphics_and_receipt(self):
        dest = self.root / "gfx.bin"
        receipt = self.root / "receipt.json"
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = fixture.main(["--out", str(dest), "--report", str(receipt)])
        self.assertEqual(result, 0)
        self.assertEqual(dest.read_bytes(), self.gfx)
        self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(receipt.read_text()), self.report)
        self.assertEqual(stdout.getvalue().strip(), fixture.PASS)
        self.assertNotIn(str(self.root), receipt.read_text())

    def test_existing_gfx_refused_without_overwrite(self):
        path = self.root / "gfx.bin"
        path.write_bytes(b"private file")
        with redirect_stdout(io.StringIO()):
            rc = fixture.main(["--out", str(path)])
        self.assertEqual(rc, 2)
        self.assertEqual(path.read_bytes(), b"private file")

    def test_existing_receipt_refused_before_creating_gfx(self):
        path = self.root / "gfx.bin"
        receipt = self.root / "receipt.json"
        receipt.write_bytes(b"keep receipt")
        with redirect_stdout(io.StringIO()):
            rc = fixture.main(["--out", str(path), "--report", str(receipt)])
        self.assertEqual(rc, 2)
        self.assertFalse(path.exists())
        self.assertEqual(receipt.read_bytes(), b"keep receipt")

    def test_same_output_and_receipt_refused(self):
        path = self.root / "gfx.bin"
        with redirect_stdout(io.StringIO()):
            rc = fixture.main(["--out", str(path), "--report", str(path)])
        self.assertEqual(rc, 2)
        self.assertFalse(path.exists())

    def test_stage307_fourteen_scene_envelope_remains_rom_free(self):
        sequence, evidence = timeline.build(fps=2)
        self.assertEqual(len(sequence), 875160)
        self.assertEqual(evidence["scene_frames"], 14)
        self.assertEqual(sequence[:8], b"CPS1SEQ1")
        self.assertTrue(self.report["graphics_are_artificial"])

    def test_receipt_explicitly_denies_original_gameplay_and_hardware(self):
        for key in ("original_rom_was_read",
                    "original_rom_or_derived_graphics_embedded",
                    "original_mame_execution_verified",
                    "original_inp_wlf_playback_verified",
                    "switch_hardware_display_verified",
                    "private_game_paths_or_assets_exported"):
            self.assertIs(self.report[key], False)

    @unittest.skipUnless(shutil.which("gcc"), "GCC required for native host integration")
    def test_native_switch_c_compositor_handles_all_fourteen_fake_frames(self):
        sequence, evidence = timeline.build(fps=2)
        with tempfile.TemporaryDirectory(prefix="dino308-native-host-") as tmp:
            dll_path = Path(tmp) / "scene.so"
            scenes._compile_scene(dll_path)
            native = ctypes.CDLL(str(dll_path))
            decode = native.cps1_scene_decode
            decode.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                               ctypes.c_void_p]
            decode.restype = ctypes.c_bool
            render = native.cps1_scene_render
            render.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                               ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.c_size_t]
            render.restype = ctypes.c_bool
            region = (ctypes.c_uint8 * fixture.REGION_BYTES).from_buffer_copy(
                self.gfx)
            state = ctypes.create_string_buffer(70000)
            output = ctypes.create_string_buffer(scenes.FRAME_BYTES)
            native_frames = {}
            for i, name in enumerate(scenes.CASES):
                start = packing.HEADER_BYTES + i * timeline.EXPECTED_SCENE_BYTES
                blob = sequence[start:start + timeline.EXPECTED_SCENE_BYTES]
                self.assertTrue(decode(blob, len(blob), state), name)
                self.assertTrue(render(region, len(self.gfx), state,
                                       output, scenes.FRAME_BYTES), name)
                native_frames[name] = output.raw
            self.assertEqual(len(native_frames), 14)
            self.assertGreaterEqual(len({zlib.crc32(x)
                                        for x in native_frames.values()}), 4)
            self.assertNotEqual(native_frames["priority_sprite"],
                                native_frames["unmasked_sprite"])
            self.assertEqual(native_frames["unmasked_sprite"],
                             native_frames["transparent_palette_unused"])
            self.assertNotEqual(native_frames["unmasked_sprite"],
                                native_frames["palette_channels_shift"])
            # Compare identical native C used by the Switch against the
            # separately implemented Python scene renderer on two scenes.
            for name in ("priority_sprite", "rowscroll_flip"):
                snapshot = scenes.synthetic_scene(name)
                expected = render_frame(
                    self.gfx, [tuple(v) for v in snapshot["palette_rgb"]],
                    snapshot)
                self.assertEqual(native_frames[name], expected, name)


if __name__ == "__main__":
    unittest.main()
