"""Stage300 synthetic-only private real-MAME original dino ROM/boot gate tests.

The names and ROM paths are artificial; the tests stub actual emulator and
ROM-hash verification. No original ROM, INP, WLF or MNG enters public CI.
"""
import json
import tempfile
import unittest
from pathlib import Path

from tools import mame0106_private_dino_boot_probe_300 as boot
from tools import mame0106_private_dino_rom_canonicalize_299 as canonical
from tools import wolfmame0106_private_binary_gate as gate
from tools import wolfmame0106_private_runtime_bundle_gate as bundle_gate


class Stage300PrivateDinoBootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dino300-artificial-only-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.emulator = self.root / "invented-mame.exe"
        self.emulator.write_bytes(b"FAKE executable, never executed")
        self.emulator.chmod(0o700)
        self.rom_dir = self.root / "private-roms"
        self.rom_dir.mkdir()
        (self.rom_dir / "dino.zip").write_bytes(b"ARTIFICIAL only")
        self.probe_calls = []
        self.runner_calls = []
        self.fail_help = False
        self.fail_verify = False
        self.verify_timeout = False
        self.boot_exit = 0
        self.boot_spawn = True
        self.boot_timeout = False
        self.make_movie = True
        self.changed_pairs = 3
        self.frame_count = 24
        self.audit_valid = True

    @staticmethod
    def fake_archive(source):
        return {
            "status": canonical.MATCH,
            "required_rom_members_matched_by_crc32_sha1": len(canonical.MANIFEST),
            "required_payloads_crc_sha1_integrity_checked": True,
        }

    def fake_probe(self, exe, args, cwd, timeout):
        self.probe_calls.append(tuple(args))
        if args == ["-help"]:
            return (0, "M.A.M.E. v0.106 -- invented help only", False) if not self.fail_help else (
                0, "MAME v0.105", False)
        if args[0] == "-verifyroms":
            if self.verify_timeout:
                return None, "", True
            return (0, "romset dino is good\n", False) if not self.fail_verify else (
                0, "romset dino is bad\n", False)
        raise AssertionError("unexpected invoked command")

    def fake_runner(self, cmd, cwd, seconds):
        self.runner_calls.append((cmd, seconds))
        if self.make_movie:
            (Path(cwd) / "stage300-boot.mng").write_bytes(
                b"ARTIFICIAL MNG STUB, not copyrighted pixels")
        return self.boot_spawn, self.boot_exit, self.boot_timeout

    def fake_mng(self, path, minimum_frames):
        if not self.audit_valid:
            raise ValueError("malformed synthetic MNG")
        return {
            "mng_signature_header_end_and_chunk_crcs_valid": True,
            "embedded_png_scanlines_and_chunk_crcs_valid": True,
            "candidate_frame_count": self.frame_count,
            "changed_candidate_pairs": self.changed_pairs,
            "identical_candidate_pairs": self.frame_count - 1 - self.changed_pairs,
        }

    def run_gate(self, **overrides):
        options = dict(
            archive_verify=self.fake_archive,
            probe=self.fake_probe, runner=self.fake_runner,
            mng_audit=self.fake_mng,
        )
        options.update(overrides)
        return boot.verify(self.emulator, self.rom_dir, **options)

    def test_real_mame_0106_banner_dotted_and_plain_both_accepted(self):
        self.assertIsNotNone(gate.MAME.search("M.A.M.E. v0.106"))
        self.assertIsNotNone(gate.MAME.search("MAME 0.106"))
        self.assertIsNotNone(gate.MAME.search("WolfMAME 0.106"))
        self.assertIsNone(gate.MAME.search("SuperMAMEing game"))
        self.assertIsNotNone(gate.VERSION.search("M.A.M.E. v0.106"))
        self.assertIsNone(gate.VERSION.search("M.A.M.E. v0.1061"))

    def test_verified_rom_loader_is_not_automatically_a_game_boot(self):
        report = self.run_gate()
        self.assertEqual(report["status"], boot.ROM_ACCEPTED)
        self.assertTrue(report["real_mame_0106_verifyroms_dino_passed"])
        self.assertTrue(report["mame_executable_reports_0_106"])
        self.assertEqual(report["historical_dino_rom_members_hash_matched"], 16)
        self.assertEqual(len(self.probe_calls), 2)
        self.assertEqual(self.probe_calls[1][:2], ("-verifyroms", "dino"))
        self.assertEqual(self.runner_calls, [])
        self.assertFalse(report["boot_attempted"])
        for flag in ("wolfmame_provenance_independently_verified",
                     "original_dino_inp_replay_verified",
                     "video_callback_input_record_alignment_verified",
                     "original_gameplay_equivalence_verified",
                     "physical_nintendo_switch_tested"):
            self.assertFalse(report[flag])
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_local_boot_24_artificial_frames_is_only_candidate_evidence(self):
        report = self.run_gate(boot_frames=24, seconds=90)
        self.assertEqual(report["status"], boot.BOOT_CANDIDATE)
        self.assertTrue(report["boot_attempted"])
        self.assertTrue(report["boot_process_exited_zero"])
        self.assertTrue(report["boot_mng_decoded_and_validated"])
        self.assertEqual(report["boot_decoded_frames"], 24)
        self.assertEqual(report["boot_image_frame_pairs_changed"], 3)
        self.assertFalse(report["original_dino_inp_replay_verified"])
        self.assertFalse(report["original_gameplay_equivalence_verified"])
        cmd, timeout = self.runner_calls[0]
        self.assertEqual(timeout, 90)
        self.assertEqual(cmd[1], "dino")
        self.assertEqual(cmd[cmd.index("-mngstartframe") + 1], "0")
        self.assertEqual(cmd[cmd.index("-mngframes") + 1], "24")
        self.assertEqual(cmd[cmd.index("-frames_to_run") + 1], "24")
        self.assertNotIn("-playback", cmd)
        self.assertNotIn("-record", cmd)
        self.assertNotIn("-mngcounttrace", cmd)

    def test_bad_original_rom_hashes_block_any_process(self):
        def bad_rom(_archive):
            return {"status": canonical.MATCH,
                    "required_rom_members_matched_by_crc32_sha1": 15}
        report = self.run_gate(archive_verify=bad_rom, boot_frames=24)
        self.assertEqual(report["status"], "BLOCKED_DINO_ROM_CONTENT_NOT_CONFIRMED")
        self.assertEqual(self.probe_calls, [])
        self.assertEqual(self.runner_calls, [])

    def test_bad_mame_help_version_is_blocked(self):
        self.fail_help = True
        report = self.run_gate(boot_frames=24)
        self.assertEqual(report["status"], "BLOCKED_MAME_0106_HELP")
        self.assertFalse(report["real_mame_0106_verifyroms_dino_passed"])
        self.assertEqual(len(self.probe_calls), 1)
        self.assertFalse(self.runner_calls)

    def test_mame_rom_loader_rejection_is_not_success(self):
        self.fail_verify = True
        report = self.run_gate(boot_frames=24)
        self.assertEqual(report["status"], "BLOCKED_REAL_MAME_DINO_ROM_LOADER")
        self.assertTrue(report["private_original_rom_hashes_match_public_mame0106_source"])
        self.assertFalse(report["real_mame_0106_verifyroms_dino_passed"])
        self.assertFalse(report["boot_attempted"])

    def test_mame_rom_loader_timeout_is_not_success(self):
        self.verify_timeout = True
        report = self.run_gate(boot_frames=24)
        self.assertEqual(report["status"], "BLOCKED_REAL_MAME_DINO_ROM_LOADER")

    def test_boot_process_failure_and_timeout_block_video(self):
        for spawn, code, timeout, status in (
            (False, None, False, "BLOCKED_DINO_BOOT_PROCESS"),
            (True, None, True, "BLOCKED_DINO_BOOT_PROCESS"),
            (True, 5, False, "BLOCKED_DINO_BOOT_NONZERO_EXIT"),
        ):
            with self.subTest((spawn, code, timeout)):
                self.boot_spawn, self.boot_exit, self.boot_timeout = spawn, code, timeout
                result = self.run_gate(boot_frames=24)
                self.assertEqual(result["status"], status)
                self.assertFalse(result["boot_mng_decoded_and_validated"])
                self.assertFalse(result["original_dino_inp_replay_verified"])

    def test_missing_mng_and_invalid_audit_are_not_success(self):
        self.make_movie = False
        self.assertEqual(
            self.run_gate(boot_frames=24)["status"], "BLOCKED_DINO_BOOT_MNG_MISSING")
        self.make_movie = True
        self.audit_valid = False
        self.assertEqual(
            self.run_gate(boot_frames=24)["status"], "BLOCKED_DINO_BOOT_MNG_INVALID")

    def test_wrong_frame_count_and_unconfirmed_png_rejected(self):
        self.frame_count = 23
        self.assertEqual(
            self.run_gate(boot_frames=24)["status"], "BLOCKED_DINO_BOOT_FRAME_COUNT_OR_AUDIT")
        self.frame_count = 24
        self.changed_pairs = 24
        self.assertEqual(
            self.run_gate(boot_frames=24)["status"], "BLOCKED_DINO_BOOT_FRAME_COUNT_OR_AUDIT")

    def test_private_mng_retention_is_exclusive_and_off_repo(self):
        dest = self.root / "retained-original-boot.mng"
        first = self.run_gate(boot_frames=24, capture_out=dest)
        self.assertEqual(first["status"], boot.BOOT_CANDIDATE)
        self.assertTrue(dest.is_file())
        self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
        self.assertIn(b"ARTIFICIAL", dest.read_bytes())
        with self.assertRaises(ValueError):
            self.run_gate(boot_frames=24, capture_out=dest)
        self.assertFalse(first["original_dino_inp_replay_verified"])

    def test_optional_runtime_bundle_rejected_before_help_or_game(self):
        def wrong_bundle(_bundle, _exe):
            return {"status": "BLOCKED_PRIVATE_RUNTIME_BUNDLE_INCONSISTENT"}
        r = self.run_gate(boot_frames=24,
                          runtime_bundle=self.root / "invented-bundle",
                          runtime_audit=wrong_bundle)
        self.assertEqual(r["status"], "BLOCKED_MAME_RUNTIME_BUNDLE_INCONSISTENT")
        self.assertEqual(self.probe_calls, [])
        self.assertEqual(self.runner_calls, [])
        self.assertFalse(r["runtime_bundle_internal_consistency_verified"])

    def test_runtime_bundle_content_consistency_does_not_authenticate_wolfmame(self):
        r = self.run_gate(
            runtime_bundle=self.root / "invented-bundle",
            runtime_audit=lambda _bundle, _exe: {"status": bundle_gate.STATUS})
        self.assertEqual(r["status"], boot.ROM_ACCEPTED)
        self.assertTrue(r["runtime_bundle_internal_consistency_verified"])
        self.assertFalse(r["wolfmame_provenance_independently_verified"])

    def test_reject_invalid_frame_limit_before_touching_private_rom(self):
        for invalid in (-1, 1, 1201, True, 3.5, "24"):
            with self.subTest(invalid):
                with self.assertRaises(ValueError):
                    self.run_gate(boot_frames=invalid)
        with self.assertRaises(ValueError):
            self.run_gate(seconds=0)
        with self.assertRaises(ValueError):
            self.run_gate(capture_out=self.root / "unused.mng", boot_frames=0)
        self.assertFalse(self.probe_calls)

    def test_disallow_symlinked_private_rom_archive_and_directory(self):
        actual = self.rom_dir / "dino.zip"
        symlink_dest = self.root / "real-rom-placeholder"
        symlink_dest.write_bytes(actual.read_bytes())
        actual.unlink()
        actual.symlink_to(symlink_dest)
        with self.assertRaises(ValueError):
            self.run_gate()
        actual.unlink()
        actual.write_bytes(b"ARTIFICIAL only")
        link = self.root / "alias-rom-root"
        link.symlink_to(self.rom_dir, target_is_directory=True)
        with self.assertRaises(ValueError):
            boot.verify(
                self.emulator, link, archive_verify=self.fake_archive,
                probe=self.fake_probe)

    def test_private_cli_failed_setup_sanitizes_status_and_receipt(self):
        receipt = self.root / "private-stage300.json"
        result = boot.main([
            "--emulator", str(self.emulator),
            "--rom-dir", str(self.rom_dir), "--out", str(receipt),
            "--boot-frames", "24",
        ])
        self.assertEqual(result, 2)  # real hashes never match invented fixture
        content = receipt.read_text()
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(content)["status"], "BLOCKED_PRIVATE_DINO_BOOT_SETUP")
        self.assertNotIn(str(self.root), content)
        self.assertNotIn("ARTIFICIAL", content)


if __name__ == "__main__":
    unittest.main()
