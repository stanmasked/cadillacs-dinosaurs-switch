"""Stage285 local-only capture orchestration tests; no ROM or game images."""
import os
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import Mock

from tools import wolfmame0106_private_mng_capture as capture
from tools import wolfmame0106_private_mng_audit as mng


def chunk(kind, body=b""):
    return (struct.pack(">I", len(body)) + kind + body +
            struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def rgb_png(rgb):
    row = b"\x00" + bytes(rgb) * 2
    raw = row + row
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    return (mng.png.PNG_SIG + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND"))


def candidate_mng():
    mhdr = struct.pack(">7I", 2, 2, 60, 0, 0, 0, 0x41)
    frames = [rgb_png((1, 2, 3)), rgb_png((4, 5, 6)), rgb_png((4, 5, 6))]
    body = mng.MNG_SIGNATURE + chunk(b"MHDR", mhdr)
    body += b"".join(frame[len(mng.png.PNG_SIG):] for frame in frames)
    return body + chunk(b"MEND")


class PrivateCaptureRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dino285-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inp = self.root / "original.inp"
        self.wlf = self.root / "original.wlf"
        self.roms = self.root / "roms"
        self.roms.mkdir()
        self.emulator = self.root / "mame0106.exe"
        self.emulator.write_bytes(b"synthetic executable placeholder")
        self.inp.write_bytes(b"synthetic private INP structure")
        self.wlf.write_bytes(b"synthetic private WLF structure")
        self.prerequisites = {
            "input_record_count": 314951,
            "recording_wolfmame_family_0_106": True,
            "emulator_help_reports_mame_0_106": True,
            "dino_rom_verifyroms_passed": True,
        }

    def run_capture(self, *, runner=None, verifier=None, audit_fn=None,
                    **kwargs):
        inp = kwargs.pop("inp", self.inp)
        wlf = kwargs.pop("wlf", self.wlf)
        return capture.capture(
            self.emulator, self.roms, inp, wlf,
            verifier=verifier or (lambda *args: dict(self.prerequisites)),
            runner=runner or self.good_runner,
            audit_fn=audit_fn or mng.audit,
            **kwargs,
        )

    def good_runner(self, cmd, cwd, seconds):
        work = Path(cwd)
        self.assertEqual((work / "inp" / "dino.inp").read_bytes(), self.inp.read_bytes())
        self.assertEqual((work / "inp" / "dino.wlf").read_bytes(), self.wlf.read_bytes())
        self.assertTrue((work / "cfg").is_dir())
        self.assertTrue((work / "nvram").is_dir())
        self.assertTrue((work / "diff").is_dir())
        self.assertTrue((work / "hi").is_dir())
        self.assertIn("dino", cmd)
        self.assertIn("-playback", cmd)
        self.assertEqual(cmd[cmd.index("-playback") + 1], "dino")
        self.assertEqual(Path(cmd[cmd.index("-rompath") + 1]), self.roms.resolve())
        self.assertEqual(cmd[cmd.index("-frames_to_run") + 1], "121")
        self.assertIn("-mngwrite", cmd)
        self.assertEqual(cmd[cmd.index("-mngwrite") + 1], "stage285")
        self.assertEqual(seconds, 120)
        self.assertFalse(any(str(self.root) in item for item in cmd if item == "stage285"))
        self.staging_path = work
        (work / "stage285.mng").write_bytes(candidate_mng())
        return True, 0, False

    def test_valid_capture_is_only_candidate_evidence(self):
        result = self.run_capture()
        self.assertEqual(result["status"], "CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED")
        self.assertTrue(result["private_input_staging_byte_identical"])
        self.assertTrue(result["candidate_mng_integrity_verified"])
        self.assertEqual(result["recorded_input_records"], 314951)
        self.assertEqual(result["candidate_video_frames"], 3)
        self.assertEqual(result["changed_adjacent_pixel_pairs"], 1)
        self.assertEqual(result["identical_adjacent_pixel_pairs"], 1)
        self.assertFalse(result["actual_inp_playback_verified"])
        self.assertFalse(result["complete_original_recording_played"])
        self.assertFalse(result["input_video_alignment_verified"])
        self.assertFalse(result["emulator_binary_provenance_verified"])
        self.assertFalse(result["physical_nintendo_switch_tested"])
        self.assertFalse(self.staging_path.exists())

    def test_prerequisite_failure_never_spawns_emulator(self):
        runner = Mock()
        bad = dict(self.prerequisites, dino_rom_verifyroms_passed=False)
        result = self.run_capture(runner=runner, verifier=lambda *a: bad)
        self.assertEqual(result["status"], "BLOCKED_PRIVATE_PLAYBACK_PREREQUISITE")
        runner.assert_not_called()
        self.assertFalse(result["emulator_process_spawned"])

    def test_non_0106_recording_blocks_capture(self):
        runner = Mock()
        bad = dict(self.prerequisites, recording_wolfmame_family_0_106=False)
        result = self.run_capture(runner=runner, verifier=lambda *a: bad)
        self.assertEqual(result["status"], "BLOCKED_PRIVATE_PLAYBACK_PREREQUISITE")
        runner.assert_not_called()

    def test_missing_candidate_video_is_not_success(self):
        def no_file(cmd, cwd, seconds):
            return True, 0, False
        result = self.run_capture(runner=no_file)
        self.assertEqual(result["status"], "CAPTURE_FILE_NOT_CREATED")
        self.assertFalse(result["candidate_mng_integrity_verified"])

    def test_spawn_failure_is_not_success(self):
        result = self.run_capture(runner=lambda *a: (False, None, False))
        self.assertEqual(result["status"], "BLOCKED_PRIVATE_PROCESS_SPAWN_FAILED")
        self.assertFalse(result["candidate_mng_found"])

    def test_nonzero_exit_with_valid_video_is_qualified(self):
        def failed_but_video(cmd, cwd, seconds):
            (Path(cwd) / "stage285.mng").write_bytes(candidate_mng())
            return True, 1, False
        result = self.run_capture(runner=failed_but_video)
        self.assertEqual(result["status"], "CANDIDATE_MNG_VALID_BUT_PROCESS_EXIT_NONZERO")
        self.assertTrue(result["candidate_mng_integrity_verified"])
        self.assertFalse(result["actual_inp_playback_verified"])

    def test_timeout_with_valid_video_is_qualified(self):
        def timed_out_but_video(cmd, cwd, seconds):
            (Path(cwd) / "stage285.mng").write_bytes(candidate_mng())
            return True, None, True
        result = self.run_capture(runner=timed_out_but_video)
        self.assertEqual(result["status"], "CANDIDATE_MNG_VALID_BUT_PROCESS_TIMED_OUT")
        self.assertTrue(result["candidate_mng_integrity_verified"])

    def test_malformed_candidate_is_not_accepted(self):
        def bad_video(cmd, cwd, seconds):
            (Path(cwd) / "stage285.mng").write_bytes(b"not an MNG")
            return True, 0, False
        result = self.run_capture(runner=bad_video)
        self.assertEqual(result["status"], "BLOCKED_PRIVATE_STAGING_OR_CAPTURE_AUDIT_FAILED")
        self.assertTrue(result["candidate_mng_found"])
        self.assertFalse(result["candidate_mng_integrity_verified"])

    def test_capture_can_be_retained_only_to_explicit_private_path(self):
        target = self.root / "retained.mng"
        result = self.run_capture(capture_out=target)
        self.assertTrue(result["candidate_capture_retained_privately"])
        self.assertEqual(target.read_bytes(), candidate_mng())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertFalse(result["private_paths_or_raw_game_frames_exported_to_public_repo"])

    def test_capture_destination_inside_repo_is_refused(self):
        target = mng.gate.ROOT / "should-not-be-created-stage285.mng"
        result = self.run_capture(capture_out=target)
        self.assertEqual(result["status"], "BLOCKED_PRIVATE_STAGING_OR_CAPTURE_AUDIT_FAILED")
        self.assertFalse(target.exists())
        self.assertFalse(result["candidate_capture_retained_privately"])

    def test_existing_capture_destination_is_refused(self):
        target = self.root / "existing.mng"
        target.write_bytes(b"do not overwrite")
        result = self.run_capture(capture_out=target)
        self.assertEqual(target.read_bytes(), b"do not overwrite")
        self.assertFalse(result["candidate_capture_retained_privately"])

    def test_invalid_frame_or_timeout_limits_refused(self):
        for frames, seconds in ((1, 5), (3602, 5), (True, 5), (121, 0), (121, 301)):
            with self.subTest(frames=frames, seconds=seconds), self.assertRaises(ValueError):
                self.run_capture(frames=frames, seconds=seconds)

    def test_symlink_input_is_refused(self):
        alias = self.root / "alias.inp"
        alias.symlink_to(self.inp)
        result = self.run_capture(inp=alias)
        self.assertEqual(result["status"], "BLOCKED_PRIVATE_STAGING_OR_CAPTURE_AUDIT_FAILED")
        self.assertFalse(result["private_input_staging_byte_identical"])

    def test_report_has_no_private_path(self):
        result = self.run_capture()
        self.assertNotIn(str(self.root), str(result))
        self.assertNotIn("original.inp", str(result))
        self.assertNotIn("original.wlf", str(result))

    def test_real_subprocess_runner_returns_exit_code_without_logs(self):
        spawned, exit_code, timed_out = capture._run(
            [sys.executable, "-c",
             "import sys; print('PRIVATE_SENTINEL'); sys.exit(7)"],
            self.root, 5,
        )
        self.assertTrue(spawned)
        self.assertEqual(exit_code, 7)
        self.assertFalse(timed_out)

    def test_real_subprocess_runner_enforces_hard_timeout(self):
        spawned, exit_code, timed_out = capture._run(
            [sys.executable, "-c", "import time; time.sleep(10)"],
            self.root, 1,
        )
        self.assertTrue(spawned)
        self.assertIsNone(exit_code)
        self.assertTrue(timed_out)


if __name__ == "__main__":
    unittest.main()
