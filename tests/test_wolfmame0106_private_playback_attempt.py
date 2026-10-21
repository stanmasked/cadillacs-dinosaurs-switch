"""Stage281 synthetic-only local playback launch tests; no Capcom data."""
import json
import os
import stat
import struct
import tempfile
import unittest
from pathlib import Path

from tools import wolfmame0106_private_playback_attempt as p


class PrivatePlaybackAttemptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dino281-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.roms = self.root / "roms"
        self.roms.mkdir()
        self.inp = self.root / "recording.inp"
        self.wlf = self.root / "recording.wlf"
        hdr = bytearray(32)
        hdr[:4] = b"dino"
        hdr[16:20] = b"TEST"
        self.inp.write_bytes(hdr + bytes([255]) * (124 * 5))
        companion = bytearray(598)
        companion[:4] = b"WLF\0"
        struct.pack_into("<I", companion, 4, 9)
        companion[148:153] = b"dino\0"
        companion[157:167] = b"0.106 mock"
        companion[248:252] = b"TEST"
        struct.pack_into("<II", companion, 256, 1, 5)
        struct.pack_into("<I", companion, 264, 5)
        self.wlf.write_bytes(companion)
        self.binary = self.root / "mamep106"
        self._program(0)

    def _program(self, exit_code=0, sleep=False):
        command = (
            '#!/bin/sh\n'
            'if [ "$1" = "-help" ]; then echo "WolfMAME 0.106"; exit 0; fi\n'
            'if [ "$1" = "-verifyroms" ]; then echo "romset dino is good"; exit 0; fi\n'
            'if [ "$1" != "dino" ] || [ "$2" != "-playback" ] || '
            '[ "$3" != "dino" ] || [ "$4" != "-rompath" ]; '
            'then exit 71; fi\n'
            'if [ ! -f inp/dino.inp ] || [ ! -f inp/dino.wlf ]; '
            'then exit 72; fi\n'
            'if [ "$(wc -c < inp/dino.inp)" != "652" ]; '
            'then exit 73; fi\n'
            + ('sleep 3\n' if sleep else '') +
            f'exit {exit_code}\n'
        )
        self.binary.write_text(command)
        self.binary.chmod(0o700)

    def run_attempt(self, **kwargs):
        return p.attempt(self.binary, self.roms, self.inp, self.wlf, **kwargs)

    def test_faux_emulator_process_runs_with_legacy_basename(self):
        report = self.run_attempt()
        self.assertEqual(report["status"], "PLAYBACK_PROCESS_EXIT_ZERO_UNVERIFIED")
        self.assertEqual(report["recorded_input_frames"], 5)
        self.assertTrue(report["private_input_staging_bytes_equal"])
        self.assertTrue(report["historical_playback_basename_without_extension"])
        self.assertTrue(report["emulator_process_spawned"])
        self.assertEqual(report["process_exit_code"], 0)
        self.assertFalse(report["actual_inp_playback_verified"])
        self.assertFalse(report["original_gameplay_recording_played_to_end"])
        self.assertFalse(report["input_video_alignment_verified"])
        self.assertFalse(report["original_gameplay_parity_verified"])
        self.assertFalse(report["physical_nintendo_switch_tested"])
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_emulator_nonzero_exit_is_never_replay_proof(self):
        self._program(15)
        result = self.run_attempt()
        self.assertEqual(result["status"], "PLAYBACK_PROCESS_EXIT_NONZERO_UNVERIFIED")
        self.assertEqual(result["process_exit_code"], 15)
        self.assertFalse(result["actual_inp_playback_verified"])

    def test_wolfmame_absence_blocks_before_staging(self):
        self.binary.unlink()
        result = self.run_attempt()
        self.assertEqual(result["status"], "BLOCKED_PRIVATE_0_106_ROM_PREREQUISITE")
        self.assertFalse(result["private_input_staging_bytes_equal"])
        self.assertFalse(result["emulator_process_spawned"])

    def test_wrong_rom_directory_blocks(self):
        self.roms.rmdir()
        result = self.run_attempt()
        self.assertEqual(result["status"], "BLOCKED_PRIVATE_0_106_ROM_PREREQUISITE")
        self.assertFalse(result["dino_rom_verification_gate_passed"])

    def test_mutated_pair_fails_validation(self):
        bad = bytearray(self.wlf.read_bytes())
        bad[248] ^= 1
        self.wlf.write_bytes(bad)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.run_attempt()

    def test_symlink_inp_rejected_without_copy(self):
        link = self.root / "alias.inp"
        link.symlink_to(self.inp)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            p.attempt(self.binary, self.roms, link, self.wlf)

    def test_observation_window_strictly_bounded(self):
        for value in (0, 121, -5, True, False, "10", 2.5):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "bounded"):
                self.run_attempt(seconds=value)

    def test_fake_runner_can_inspect_private_staging_then_auto_cleanup(self):
        seen = []
        def fake_runner(binary, rom_dir, staged, seconds):
            self.assertEqual(binary, self.binary)
            self.assertEqual(rom_dir, self.roms)
            inp = staged / "inp" / "dino.inp"
            wlf = staged / "inp" / "dino.wlf"
            self.assertEqual(inp.read_bytes(), self.inp.read_bytes())
            self.assertEqual(wlf.read_bytes(), self.wlf.read_bytes())
            self.assertEqual(inp.stat().st_mode & 0o777, 0o600)
            self.assertEqual(wlf.stat().st_mode & 0o777, 0o600)
            self.assertEqual((staged / "inp").stat().st_mode & 0o777, 0o700)
            seen.append(staged)
            return True, 0, False
        result = self.run_attempt(runner=fake_runner)
        self.assertTrue(result["private_input_staging_bytes_equal"])
        self.assertEqual(len(seen), 1)
        self.assertFalse(seen[0].exists())

    def test_runner_exception_releases_staging_without_exposing_paths(self):
        seen = []
        def broken_runner(binary, rom_dir, staged, seconds):
            seen.append(staged)
            raise OSError("private operation failed")
        result = self.run_attempt(runner=broken_runner)
        self.assertEqual(result["status"], "BLOCKED_PRIVATE_STAGING_FAILED")
        self.assertFalse(seen[0].exists())
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_mock_spawn_failure_does_not_claim_run(self):
        result = self.run_attempt(runner=lambda *args: (False, None, False))
        self.assertEqual(result["status"], "BLOCKED_PLAYBACK_PROCESS_SPAWN_FAILED")
        self.assertFalse(result["emulator_process_spawned"])

    def test_mock_time_limit_is_explicit_and_unverified(self):
        result = self.run_attempt(runner=lambda *args: (True, None, True))
        self.assertEqual(result["status"], "PLAYBACK_PROCESS_TIME_LIMIT_UNVERIFIED")
        self.assertTrue(result["process_terminated_at_time_limit"])
        self.assertIsNone(result["process_exit_code"])
        self.assertFalse(result["actual_inp_playback_verified"])

    def test_private_receipt_has_exclusive_permissions(self):
        out = self.root / "attempt.json"
        result = self.run_attempt()
        p.gate.write_private_receipt(out, result)
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(out.read_text()), result)
        with self.assertRaises(FileExistsError):
            p.gate.write_private_receipt(out, result)

    def test_cli_summary_no_paths_or_recording_bytes(self):
        out = self.root / "cli.json"
        code = p.main([
            "--emulator", str(self.binary), "--rom-dir", str(self.roms),
            "--inp", str(self.inp), "--wlf", str(self.wlf),
            "--seconds", "1", "--out", str(out)
        ])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(out.read_text())["actual_inp_playback_verified"])
        self.assertNotIn(str(self.root), out.read_text())

    def test_cli_rejects_malformed_recording_without_traceback_leak(self):
        out = self.root / "blocked.json"
        self.inp.unlink()
        code = p.main([
            "--emulator", str(self.binary), "--rom-dir", str(self.roms),
            "--inp", str(self.inp), "--wlf", str(self.wlf),
            "--out", str(out)
        ])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.read_text())["status"],
                         "BLOCKED_INVALID_PRIVATE_RECORDING_OR_ENVIRONMENT")
        self.assertNotIn(str(self.root), out.read_text())

    @unittest.skipIf(os.name == "nt", "requires POSIX shell fake emulator")
    def test_actual_timeout_kills_faux_game_without_recording_proof(self):
        self._program(0, sleep=True)
        result = self.run_attempt(seconds=1)
        self.assertEqual(result["status"], "PLAYBACK_PROCESS_TIME_LIMIT_UNVERIFIED")
        self.assertTrue(result["emulator_process_spawned"])
        self.assertFalse(result["actual_inp_playback_verified"])


if __name__ == "__main__":
    unittest.main()
