"""Stage309 ROM-free native C acceptance of the exact Stage307/308 file pair."""
import ctypes
import io
import json
import shutil
import struct
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import cps1_rom_free_native_sequence_acceptance_309 as audit
from tools import cps1_synthetic_gfx_fixture_308 as graphics
from tools import cps1_synthetic_scene_sequence_307 as timeline
from tools import cps1_private_scene_compositor_parity as scenes


@unittest.skipUnless(shutil.which("gcc"), "host GCC required")
class Stage309NativeSequenceAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="dino309-tests-rom-free-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.library = Path(cls.tmp.name) / "native.so"
        audit.compile_native(cls.library)
        cls.decode, cls.frame, cls.render = audit.native_api(cls.library)
        cls.sequence, cls.evidence = timeline.build(fps=2)
        cls.fake_gfx, cls.gfx_evidence = graphics.build()

    def native_open(self, payload):
        raw = ctypes.create_string_buffer(payload, len(payload))
        state = audit.NativeSequence()
        allowed = self.decode(raw, len(payload), ctypes.byref(state))
        return allowed, raw, state

    def test_real_switch_portable_c_accepts_both_exact_synthetic_formats(self):
        allowed, raw, state = self.native_open(self.sequence)
        self.assertTrue(allowed)
        self.assertEqual(state.frame_count, 14)
        self.assertEqual(state.fps, 2)
        decoded_scene = ctypes.create_string_buffer(audit.SCENE_MEMORY_BYTES)
        for index in range(14):
            with self.subTest(frame=index):
                self.assertTrue(self.frame(ctypes.byref(state), index,
                                           decoded_scene))
        self.assertFalse(self.frame(ctypes.byref(state), 14, decoded_scene))
        self.assertTrue(self.gfx_evidence["graphics_are_artificial"])
        self.assertEqual(len(self.fake_gfx), 4194304)

    def test_native_header_corruption_rejected(self):
        # Flipping the FPS byte from 2 to 3 is still legal (range 1..60).
        # Check actual invalid boundaries rather than another valid rate.
        for position in (0, 8, 12, 16):
            modified = bytearray(self.sequence)
            modified[position] ^= 1
            with self.subTest(position=position):
                accepted, raw, state = self.native_open(bytes(modified))
                self.assertFalse(accepted)
        for bad_fps in (0, 61):
            modified = bytearray(self.sequence)
            struct.pack_into("<H", modified, 10, bad_fps)
            with self.subTest(fps=bad_fps):
                accepted, raw, state = self.native_open(bytes(modified))
                self.assertFalse(accepted)

    def test_native_rejects_nested_crc_even_if_outer_is_corrected(self):
        modified = bytearray(self.sequence)
        modified[20 + 200] ^= 1
        struct.pack_into("<I", modified, 12, zlib.crc32(modified[20:]))
        accepted, raw, state = self.native_open(bytes(modified))
        self.assertFalse(accepted)

    def test_native_rejects_noncanonical_flags_with_both_crc_correct(self):
        for bad_offset in (32, 33, 34, 35):
            modified = bytearray(self.sequence)
            modified[20 + bad_offset] = 2 if bad_offset < 35 else 1
            frame_end = 20 + timeline.EXPECTED_SCENE_BYTES
            struct.pack_into("<I", modified, 20 + 12,
                             zlib.crc32(modified[20 + 16:frame_end]))
            struct.pack_into("<I", modified, 12, zlib.crc32(modified[20:]))
            with self.subTest(offset=bad_offset):
                accepted, raw, state = self.native_open(bytes(modified))
                self.assertFalse(accepted)

    def test_native_60hz_step_and_pause_wrap_are_consistent(self):
        accepted, raw, seq = self.native_open(self.sequence)
        self.assertTrue(accepted)
        library = ctypes.CDLL(str(self.library))
        init = library.cps1_playback_init
        init.argtypes = (ctypes.POINTER(audit.Playback),)
        step = library.cps1_playback_step
        step.argtypes = (ctypes.POINTER(audit.Playback),
                         ctypes.POINTER(audit.NativeSequence), ctypes.c_int)
        step.restype = ctypes.c_bool
        advance = library.cps1_playback_advance
        advance.argtypes = (ctypes.POINTER(audit.Playback),
                            ctypes.POINTER(audit.NativeSequence), ctypes.c_uint32)
        advance.restype = ctypes.c_bool
        speed = library.cps1_playback_speed
        speed.argtypes = (ctypes.POINTER(audit.Playback), ctypes.c_int)
        play = audit.Playback()
        init(ctypes.byref(play))
        self.assertEqual((play.index, play.speed_num, play.paused), (0, 2, False))
        self.assertFalse(advance(ctypes.byref(play), ctypes.byref(seq), 29))
        self.assertEqual(play.index, 0)
        self.assertTrue(advance(ctypes.byref(play), ctypes.byref(seq), 1))
        self.assertEqual(play.index, 1)
        self.assertTrue(step(ctypes.byref(play), ctypes.byref(seq), -1))
        self.assertTrue(play.paused)
        self.assertEqual(play.index, 0)
        self.assertFalse(advance(ctypes.byref(play), ctypes.byref(seq), 60))
        self.assertTrue(step(ctypes.byref(play), ctypes.byref(seq), -1))
        self.assertEqual(play.index, 13)
        play.paused = False
        speed(ctypes.byref(play), 1)
        self.assertEqual(play.speed_num, 4)
        self.assertTrue(advance(ctypes.byref(play), ctypes.byref(seq), 15))
        self.assertEqual(play.index, 0)

    def test_all_14_frames_match_independent_python_and_controlled_effects(self):
        report = audit.verify()
        self.assertEqual(report["status"], audit.PASS)
        self.assertEqual(report["synthetic_sequence_frames_accepted_by_native_c"], 14)
        self.assertEqual(report["synthetic_cps1_rgba_pixels_compared"], 14 * 384 * 224)
        self.assertEqual(report["native_python_mismatching_rgba_pixels"], 0)
        self.assertEqual(report["isolated_priority_and_palette_effects_checked"], 10)
        self.assertTrue(report["differential_coverage_verified"])

    def test_injected_reference_mismatch_is_never_reported_as_success(self):
        with patch.object(audit.python_scene, "render_frame",
                          return_value=bytes(audit.RG_BYTES)):
            with self.assertRaisesRegex(ValueError, "parity"):
                audit.verify()

    def test_missing_case_is_refused_before_native_compile(self):
        with patch.object(scenes, "CASES", ("priority_sprite",)):
            with self.assertRaises(ValueError):
                audit.verify()

    def test_cli_returns_minimal_non_gameplay_receipt(self):
        with patch.object(audit, "verify", return_value={
                "schema": audit.SCHEMA, "status": audit.PASS,
                "original_rom_was_read": False,
                "physical_switch_framebuffer_verified": False}):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                rc = audit.main()
        self.assertEqual(rc, 0)
        receipt = json.loads(stdout.getvalue())
        self.assertIs(receipt["original_rom_was_read"], False)
        self.assertIs(receipt["physical_switch_framebuffer_verified"], False)

    def test_cli_refuses_build_failure_without_leaking_exception_text(self):
        with patch.object(audit, "compile_native",
                          side_effect=RuntimeError("PRIVATE ASSET SECRET")):
            out = io.StringIO()
            with redirect_stdout(out):
                rc = audit.main()
        self.assertEqual(rc, 2)
        self.assertEqual(json.loads(out.getvalue())["status"], audit.BLOCKED)
        self.assertNotIn("PRIVATE ASSET SECRET", out.getvalue())


if __name__ == "__main__":
    unittest.main()
