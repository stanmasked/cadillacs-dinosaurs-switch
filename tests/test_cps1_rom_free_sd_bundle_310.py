"""Stage310 ROM-free local SD staging tests; no original dino assets."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools import cps1_rom_free_sd_bundle_310 as bundle
from tools import cps1_synthetic_scene_sequence_307 as timeline
from tools import cps1_synthetic_gfx_fixture_308 as graphics


class Stage310RomFreeSdBundleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="dino310-artificial-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.staging = self.root / "diagnostic-new"

    def test_two_correct_files_and_last_written_ready_receipt(self):
        receipt = bundle.stage(self.staging)
        self.assertEqual(receipt["schema"], bundle.SCHEMA)
        self.assertEqual(receipt["status"], bundle.PASS)
        self.assertEqual(receipt["local_sd_relative_directory"],
                         "switch/cadillacs-dinosaurs-switch")
        folder = self.staging / bundle.APP_RELATIVE
        gfx, _ = graphics.build()
        sequence, _ = timeline.build(fps=2)
        self.assertEqual((folder / "gfx.bin").read_bytes(), gfx)
        self.assertEqual((folder / "sequence.bin").read_bytes(), sequence)
        self.assertEqual(set(folder.iterdir()),
                         {folder / "gfx.bin", folder / "sequence.bin"})
        self.assertEqual((self.staging / bundle.RECEIPT_NAME).exists(), True)
        local_receipt = json.loads(
            (self.staging / bundle.RECEIPT_NAME).read_text())
        self.assertEqual(local_receipt, receipt)
        self.assertEqual(receipt["total_synthetic_data_bytes"], 5069464)

    def test_private_folder_and_file_modes(self):
        bundle.stage(self.staging)
        for path in (self.staging, self.staging / "switch",
                     self.staging / bundle.APP_RELATIVE):
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        for path in (
                self.staging / bundle.APP_RELATIVE / "gfx.bin",
                self.staging / bundle.APP_RELATIVE / "sequence.bin",
                self.staging / bundle.RECEIPT_NAME):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_receipt_only_identifies_synthetic_inputs_and_denies_gameplay(self):
        receipt = bundle.stage(self.staging)
        for name in ("original_rom_or_original_graphics_read",
                     "original_gameplay_captured",
                     "original_inp_wlf_playback_verified",
                     "host_c_test_run_by_this_command",
                     "nintendo_switch_or_emulator_execution_verified",
                     "physical_switch_framebuffer_verified",
                     "private_paths_or_game_assets_exported"):
            self.assertIs(receipt[name], False)
        self.assertTrue(receipt["graphics_and_scenes_are_artificial"])
        self.assertTrue(receipt["all_14_scene_envelopes_validated"])
        self.assertTrue(receipt["ready_for_manual_local_sd_copy"])
        self.assertNotIn(str(self.root), json.dumps(receipt))

    def test_check_synthetic_digests_are_based_on_local_fake_files(self):
        receipt = bundle.stage(self.staging)
        location = self.staging / bundle.APP_RELATIVE
        self.assertEqual(receipt["synthetic_graphics_sha256"],
                         bundle._sha256_file(location / "gfx.bin"))
        self.assertEqual(receipt["synthetic_sequence_sha256"],
                         bundle._sha256_file(location / "sequence.bin"))
        self.assertNotEqual(receipt["synthetic_graphics_sha256"],
                            receipt["synthetic_sequence_sha256"])

    def test_existing_folder_never_overwritten(self):
        self.staging.mkdir()
        original = self.staging / "original.bin"
        original.write_bytes(b"DO NOT TOUCH PRIVATE FILE")
        with self.assertRaises(ValueError):
            bundle.stage(self.staging)
        self.assertEqual(original.read_bytes(), b"DO NOT TOUCH PRIVATE FILE")
        self.assertFalse((self.staging / bundle.RECEIPT_NAME).exists())

    def test_repeat_stage_is_refused_without_mutation(self):
        receipt = bundle.stage(self.staging)
        original_bytes = (
            self.staging / bundle.APP_RELATIVE / "sequence.bin").read_bytes()
        with self.assertRaises(ValueError):
            bundle.stage(self.staging)
        self.assertEqual(
            (self.staging / bundle.APP_RELATIVE / "sequence.bin").read_bytes(),
            original_bytes)

    def test_symlink_parent_and_symlink_destination_refused(self):
        real = self.root / "real"
        real.mkdir()
        link = self.root / "linked"
        link.symlink_to(real, target_is_directory=True)
        with self.assertRaises(ValueError):
            bundle.stage(link / "new")
        with self.assertRaises(ValueError):
            bundle.stage(link)
        self.assertEqual(list(real.iterdir()), [])

    def test_refuse_destination_inside_public_repository(self):
        internal = Path(__file__).resolve().parents[1] / "never-write-gfx.bin"
        with self.assertRaises(ValueError):
            bundle.stage(internal)
        self.assertFalse(internal.exists())

    def test_reject_non_synthetic_fake_graphics_even_if_size_matches(self):
        gfx, _ = graphics.build()
        seq, _ = timeline.build()
        bad = bytearray(gfx)
        bad[0] ^= 1
        with self.assertRaises(ValueError):
            bundle._validate(bytes(bad), seq)
        with self.assertRaises(ValueError):
            bundle._validate(bytes(gfx[:-1]), seq)
        bad = bytearray(gfx)
        bad[graphics.PERIOD_BYTES + 512] ^= 1
        with self.assertRaises(ValueError):
            bundle._validate(bytes(bad), seq)

    def test_counterfeit_repeating_graphics_pattern_is_rejected(self):
        # An arbitrary period still meets length, marker, and repetition
        # requirements; Stage310 must never label such data synthetic.
        gfx, _ = graphics.build()
        seq, _ = timeline.build()
        counterfeit_period = bytearray(gfx[:graphics.PERIOD_BYTES])
        counterfeit_period[512] ^= 1
        forged = bytes(counterfeit_period) * (
            graphics.REGION_BYTES // graphics.PERIOD_BYTES)
        self.assertEqual(len(forged), graphics.REGION_BYTES)
        self.assertTrue(forged.startswith(graphics.MARKER))
        self.assertEqual(forged, forged[:graphics.PERIOD_BYTES] *
                         (graphics.REGION_BYTES // graphics.PERIOD_BYTES))
        with self.assertRaises(ValueError):
            bundle._validate(forged, seq)

    def test_crc_repaired_modified_scene_is_not_called_synthetic(self):
        import struct
        import zlib
        gfx, _ = graphics.build()
        seq, _ = timeline.build()
        forged = bytearray(seq)
        # Mutate one arbitrary palette payload byte while keeping exact
        # frame count, FPS, format, all framing and both CRCs valid.
        payload_offset = timeline.sequence.HEADER_BYTES + 16 + 100
        forged[payload_offset] ^= 1
        start = timeline.sequence.HEADER_BYTES
        end = start + timeline.EXPECTED_SCENE_BYTES
        struct.pack_into("<I", forged, start + 12,
                         zlib.crc32(forged[start + 16:end]))
        struct.pack_into("<I", forged, 12,
                         zlib.crc32(forged[start:]))
        # A structural validator properly accepts it; provenance must NOT.
        self.assertEqual(
            timeline._inspect(bytes(forged), fps=2, frames=14)["status"],
            timeline.PASS)
        with self.assertRaises(ValueError):
            bundle._validate(gfx, bytes(forged))

    def test_reject_scene_checksum_and_noncanonical_flags(self):
        gfx, _ = graphics.build()
        seq, _ = timeline.build()
        corrupted = bytearray(seq)
        corrupted[20 + 120] ^= 1
        with self.assertRaises(ValueError):
            bundle._validate(gfx, bytes(corrupted))
        corrupted = bytearray(seq)
        corrupted[20 + 32] = 2
        with self.assertRaises(ValueError):
            bundle._validate(gfx, bytes(corrupted))

    def test_failure_before_staging_has_no_directories_or_ready_manifest(self):
        gfx, original = graphics.build()
        fake_report = {**original, "original_rom_was_read": True}
        with patch.object(bundle.graphics, "build", return_value=(gfx, fake_report)):
            with self.assertRaises(ValueError):
                bundle.stage(self.staging)
        self.assertFalse(self.staging.exists())

    def test_partial_write_has_no_ready_receipt(self):
        original_write = bundle.timeline._write_exclusive
        def fail_sequence(path, data):
            if path.name == "sequence.bin":
                raise OSError("simulated write failure")
            return original_write(path, data)
        with patch.object(bundle.timeline, "_write_exclusive",
                          side_effect=fail_sequence):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                result = bundle.main(["--out-dir", str(self.staging)])
        self.assertEqual(result, 2)
        self.assertEqual(stdout.getvalue().strip(), bundle.BLOCKED)
        self.assertTrue(self.staging.exists())
        self.assertFalse((self.staging / bundle.RECEIPT_NAME).exists())
        # Partial installation must never be mistaken for a ready kit.

    def test_readback_corruption_never_writes_success_receipt(self):
        with patch.object(bundle, "_sha256_file", return_value="bad"):
            with self.assertRaises(ValueError):
                bundle.stage(self.staging)
        self.assertFalse((self.staging / bundle.RECEIPT_NAME).exists())

    def test_success_cli_prints_status_without_any_private_paths(self):
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = bundle.main(["--out-dir", str(self.staging)])
        self.assertEqual(code, 0)
        self.assertEqual(stdout.getvalue().strip(), bundle.PASS)
        self.assertNotIn(str(self.root), stdout.getvalue())
        with redirect_stdout(io.StringIO()) as second:
            code2 = bundle.main(["--out-dir", str(self.staging)])
        self.assertEqual(code2, 2)
        self.assertEqual(second.getvalue().strip(), bundle.BLOCKED)


if __name__ == "__main__":
    unittest.main()
