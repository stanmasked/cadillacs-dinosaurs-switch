"""Stage307 ROM-free 14-case CPS1 native-Switch diagnostic sequence tests."""
import copy
import io
import json
import struct
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from tools import cps1_synthetic_scene_sequence_307 as diag
from tools import cps1_sequence_export as original
from tools import cps1_private_scene_compositor_parity as scenes


class Stage307SyntheticSequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.report = diag.build(fps=2)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="dino307-artificial-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_complete_14_case_sequence_has_consistent_versioned_envelope(self):
        self.assertEqual(self.report["status"], diag.PASS)
        self.assertEqual(self.report["scene_frames"], 14)
        self.assertEqual(self.report["scene_names_in_fixed_order"],
                         list(scenes.CASES))
        self.assertEqual(self.report["target_cps1_width"], 384)
        self.assertEqual(self.report["target_cps1_height"], 224)
        self.assertEqual(self.report["sequence_file_bytes"],
                         20 + 14 * 62510)
        self.assertEqual(len(self.data), diag.EXPECTED_SEQUENCE_BYTES)
        self.assertTrue(self.report["outer_sequence_crc_checked"])
        self.assertEqual(self.report["inner_scene_crc_checks_passed"], 14)

    def test_all_14_embedded_synthetic_frames_have_separate_crc(self):
        original_crcs = []
        for i in range(diag.SCENE_COUNT):
            off = original.HEADER_BYTES + i * diag.EXPECTED_SCENE_BYTES
            blob = self.data[off:off + diag.EXPECTED_SCENE_BYTES]
            self.assertEqual(blob[:8], b"CPS1SCN1")
            self.assertEqual(zlib.crc32(blob[16:]),
                             struct.unpack_from("<I", blob, 12)[0])
            original_crcs.append(zlib.crc32(blob))
        self.assertEqual(len(set(original_crcs)), 14)

    def test_deterministic_two_builds_have_identical_bytes(self):
        second, report = diag.build(fps=2)
        self.assertEqual(second, self.data)
        self.assertEqual(report, self.report)

    def test_custom_supported_fps_only_changes_header_not_gameplay(self):
        slow, meta = diag.build(fps=1)
        self.assertEqual(meta["frames_per_second"], 1)
        self.assertEqual(slow[20:], self.data[20:])
        self.assertNotEqual(slow[:20], self.data[:20])
        diag._inspect(slow, fps=1, frames=14)

    def test_invalid_fps_and_boolean_rejected_before_any_output(self):
        for fps in (0, 61, -1, 2.0, True, "2", None):
            with self.subTest(fps=fps):
                with self.assertRaises(ValueError):
                    diag.build(fps=fps)

    def test_missing_or_counterfeit_scene_provider_is_rejected(self):
        def empty(_name):
            return {"buffered_obj_source": "UNAVAILABLE_MAME_LUA"}
        with self.assertRaises(ValueError):
            diag.build(provider=empty)
        with self.assertRaises(ValueError):
            diag.build(provider=lambda _name: [])

    def test_incorrect_blob_length_rejected(self):
        with self.assertRaisesRegex(ValueError, "packed"):
            diag.build(pack=lambda _: b"not a scene")

    def test_tampered_outer_crc_is_rejected(self):
        changed = bytearray(self.data)
        changed[12] ^= 1
        with self.assertRaisesRegex(ValueError, "checksum"):
            diag._inspect(bytes(changed), fps=2, frames=14)

    def test_wrong_count_or_fps_or_reserved_does_not_pass(self):
        for at in (8, 10, 16):
            changed = bytearray(self.data)
            changed[at] ^= 1
            with self.subTest(index=at):
                with self.assertRaises(ValueError):
                    diag._inspect(bytes(changed), fps=2, frames=14)

    def test_tampered_scene_crc_is_detected_even_if_outer_recomputed(self):
        corrupted = bytearray(self.data)
        at = original.HEADER_BYTES + 16 + 500
        corrupted[at] ^= 1
        struct.pack_into("<I", corrupted, 12,
                         zlib.crc32(corrupted[original.HEADER_BYTES:]))
        with self.assertRaisesRegex(ValueError, "frame"):
            diag._inspect(bytes(corrupted), fps=2, frames=14)

    def test_repeated_scenes_rejected_even_with_valid_checksums(self):
        corrupted = bytearray(self.data)
        frame1 = original.HEADER_BYTES + diag.EXPECTED_SCENE_BYTES
        frame0 = original.HEADER_BYTES
        corrupted[frame1:frame1 + diag.EXPECTED_SCENE_BYTES] = (
            corrupted[frame0:frame0 + diag.EXPECTED_SCENE_BYTES])
        struct.pack_into("<I", corrupted, 12,
                         zlib.crc32(corrupted[original.HEADER_BYTES:]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            diag._inspect(bytes(corrupted), fps=2, frames=14)

    def test_exclusive_private_binary_write_and_no_overwrite(self):
        output = self.root / "sequence.bin"
        diag._write_exclusive(output, self.data)
        self.assertEqual(output.read_bytes(), self.data)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(ValueError):
            diag._write_exclusive(output, b"overwritten")
        self.assertEqual(output.read_bytes(), self.data)

    def test_symlinked_output_and_parent_rejected(self):
        target = self.root / "target"
        target.write_bytes(b"do not replace")
        link = self.root / "sequence-link.bin"
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            diag._write_exclusive(link, self.data)
        nested = self.root / "sub"
        nested.mkdir()
        outer = self.root / "link-dir"
        outer.symlink_to(nested, target_is_directory=True)
        with self.assertRaises(ValueError):
            diag._write_exclusive(outer / "scene.bin", self.data)

    def test_status_never_claims_gameplay_or_embeds_rom(self):
        for key in ("original_gfx_rom_is_not_embedded",
                    "frame_states_are_synthetic"):
            self.assertIs(self.report[key], True)
        for key in ("original_mame_gameplay_frame_captured",
                    "real_vram_palette_or_obj_captured",
                    "original_inp_wlf_replay_verified",
                    "switch_hardware_display_verified",
                    "private_game_paths_or_assets_exported"):
            self.assertIs(self.report[key], False)
        self.assertNotIn(str(self.root), json.dumps(self.report))

    def test_private_cli_writes_correct_binary_but_no_original_data(self):
        output = self.root / "sequence.bin"
        receipt = self.root / "report.json"
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            rc = diag.main(["--out", str(output),
                            "--report", str(receipt), "--fps", "2"])
        self.assertEqual(rc, 0)
        self.assertEqual(output.read_bytes(), self.data)
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(receipt.read_text())["status"], diag.PASS)
        self.assertNotIn(str(self.root), stdout.getvalue())
        self.assertNotIn(str(self.root), receipt.read_text())

    def test_existing_output_fail_closed_does_not_replace_user_file(self):
        output = self.root / "sequence.bin"
        output.write_bytes(b"preserve")
        with redirect_stdout(io.StringIO()):
            code = diag.main(["--out", str(output), "--fps", "2"])
        self.assertEqual(code, 2)
        self.assertEqual(output.read_bytes(), b"preserve")


if __name__ == "__main__":
    unittest.main()
