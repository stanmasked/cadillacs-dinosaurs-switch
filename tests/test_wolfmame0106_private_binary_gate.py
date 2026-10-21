"""Stage279 synthetic ROM-free emulator gate tests; never use real game assets."""
import json
import os
import stat
import struct
import tempfile
import unittest
from pathlib import Path

from tools import wolfmame0106_private_binary_gate as gate


class WolfMameBinaryGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dino279-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inp = self.root / "sample.inp"
        self.wlf = self.root / "sample.wlf"
        self.roms = self.root / "roms"
        self.roms.mkdir()
        header = bytearray(32)
        header[:4] = b"dino"
        header[16:20] = b"ABCD"
        self.inp.write_bytes(header + bytes([255]) * (124 * 2))
        companion = bytearray(598)
        companion[:4] = b"WLF\0"
        struct.pack_into("<I", companion, 4, 9)
        companion[148:153] = b"dino\0"
        companion[157:167] = b"0.106 test"
        companion[248:252] = b"ABCD"
        struct.pack_into("<II", companion, 256, 100, 120)
        struct.pack_into("<I", companion, 264, 2)
        self.wlf.write_bytes(companion)
        self.exe = self.root / "wolfmame"
        self.exe.write_text("#!/bin/sh\nexit 0\n")
        self.exe.chmod(self.exe.stat().st_mode | stat.S_IXUSR)

    @staticmethod
    def response(version=True, roms=True, timeout=False):
        def probe(_exe, args, _cwd, _seconds):
            if timeout:
                return None, "", True
            if args == ["-help"]:
                return 0, "WolfMAME 0.106 command line\n" if version else "MAME 0.289\n", False
            if args[:2] == ["-verifyroms", "dino"]:
                return (0, "romset dino is good\n1 romsets found, 1 were OK.\n", False) if roms \
                    else (1, "romset dino is bad\n", False)
            raise AssertionError("unexpected command")
        return probe

    def inspect(self, **kw):
        return gate.inspect(self.exe, self.roms, self.inp, self.wlf, **kw)

    def test_success_checks_only_readiness_not_playback(self):
        receipt = self.inspect(probe=self.response())
        self.assertEqual(receipt["status"], "READY_FOR_MANUAL_PRIVATE_INP_PLAYBACK_NOT_VERIFIED")
        self.assertEqual(receipt["input_record_count"], 2)
        self.assertTrue(receipt["dino_rom_verifyroms_passed"])
        for name in ("actual_inp_playback_verified", "original_gameplay_frames_captured",
                     "input_video_alignment_verified", "original_gameplay_parity_verified",
                     "emulator_binary_provenance_verified"):
            self.assertFalse(receipt[name], name)
        self.assertNotIn(str(self.root), json.dumps(receipt))

    def test_wrong_version_rejected_before_rom_check(self):
        receipt = self.inspect(probe=self.response(version=False))
        self.assertEqual(receipt["status"], "BLOCKED_WOLFMAME_VERSION_NOT_CONFIRMED")
        self.assertFalse(receipt["dino_rom_verifyroms_passed"])

    def test_rom_failure_never_claims_ready(self):
        receipt = self.inspect(probe=self.response(roms=False))
        self.assertEqual(receipt["status"], "BLOCKED_ROM_VERIFICATION_FAILED")
        self.assertFalse(receipt["dino_rom_verifyroms_passed"])

    def test_missing_executable_and_private_rom_directory(self):
        self.exe.unlink()
        self.assertEqual(self.inspect(probe=self.response())["status"],
                         "BLOCKED_NO_EXECUTABLE_WOLFMAME")
        self.exe.write_text("#!/bin/sh\nexit 0\n")
        self.exe.chmod(0o700)
        self.roms.rmdir()
        self.assertEqual(self.inspect(probe=self.response())["status"],
                         "BLOCKED_NO_PRIVATE_ROM_DIRECTORY")

    def test_probe_timeout_is_reported_not_success(self):
        self.assertEqual(self.inspect(probe=self.response(timeout=True))["status"],
                         "BLOCKED_EMULATOR_HELP_TIMEOUT")

    def test_reject_symlink_original_input(self):
        link = self.root / "link.inp"
        link.symlink_to(self.inp)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            gate.inspect(self.exe, self.roms, link, self.wlf, probe=self.response())

    def test_reject_bad_inp_wlf_pair(self):
        raw = bytearray(self.wlf.read_bytes())
        raw[248] ^= 1
        self.wlf.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.inspect(probe=self.response())

    def test_receipt_is_exclusive_and_private(self):
        receipt = self.inspect(probe=self.response())
        dest = self.root / "receipt.json"
        gate.write_private_receipt(dest, receipt)
        written = json.loads(dest.read_text())
        self.assertEqual(written, receipt)
        self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            gate.write_private_receipt(dest, receipt)
        self.assertNotIn(str(self.inp), dest.read_text())

    def test_public_repository_receipt_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "private"):
            gate.write_private_receipt(gate.ROOT / "unsafe.json", {})

    def test_real_subprocess_probe_with_fake_emulator_is_synthetic(self):
        self.exe.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = '-help' ]; then echo 'WolfMAME 0.106 mock'; exit 0; fi\n"
            "if [ \"$1\" = '-verifyroms' ]; then echo 'romset dino is good'; exit 0; fi\n"
            "exit 4\n"
        )
        self.exe.chmod(0o700)
        receipt = self.inspect()
        self.assertTrue(receipt["dino_rom_verifyroms_passed"])
        self.assertFalse(receipt["actual_inp_playback_verified"])

    def test_symlink_binary_is_blocked_before_execution(self):
        link = self.root / "emulator-link"
        link.symlink_to(self.exe)
        report = gate.inspect(link, self.roms, self.inp, self.wlf, probe=self.response())
        self.assertEqual(report["status"], "BLOCKED_NO_EXECUTABLE_WOLFMAME")

    def test_bounded_raw_probe_output_does_not_leak_banner(self):
        self.exe.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = '-help' ]; then head -c 131073 /dev/zero | tr '\\000' 'x'; exit 0; fi\n"
            "exit 4\n"
        )
        self.exe.chmod(0o700)
        status, captured, timed_out = gate.bounded_probe(
            self.exe, ["-help"], self.root, 10,
        )
        self.assertEqual(status, 0)
        self.assertEqual(captured, "")
        self.assertFalse(timed_out)

    def test_vintage_generic_mame_banner_is_accepted_without_wolf_identity_claim(self):
        def legacy(_binary, argv, _cwd, _timeout):
            if argv == ["-help"]:
                return 0, "MAME 0.106 copyright historic", False
            return 0, "romset dino is good", False
        receipt = self.inspect(probe=legacy)
        self.assertTrue(receipt["emulator_help_reports_mame_0_106"])
        self.assertTrue(receipt["dino_rom_verifyroms_passed"])
        self.assertFalse(receipt["emulator_binary_provenance_verified"])
        self.assertFalse(receipt["actual_inp_playback_verified"])

    def test_rom_verification_timeout_cannot_claim_readiness(self):
        def rom_timeout(_binary, argv, _cwd, _seconds):
            if argv == ["-help"]:
                return 0, "MAME 0.106", False
            return None, "", True
        receipt = self.inspect(probe=rom_timeout)
        self.assertEqual(receipt["status"], "BLOCKED_ROM_VERIFICATION_TIMEOUT")
        self.assertFalse(receipt["dino_rom_verifyroms_passed"])
        self.assertFalse(receipt["actual_inp_playback_verified"])

    def test_fake_success_exit_without_good_romset_is_rejected(self):
        def misleading(_binary, argv, _cwd, _seconds):
            if argv == ["-help"]:
                return 0, "MAME 0.106", False
            return 0, "1 romsets found, 1 were OK", False
        receipt = self.inspect(probe=misleading)
        self.assertEqual(receipt["status"], "BLOCKED_ROM_VERIFICATION_FAILED")
        self.assertFalse(receipt["dino_rom_verifyroms_passed"])

    def test_symlink_rom_directory_is_rejected(self):
        shortcut = self.root / "rom-link"
        shortcut.symlink_to(self.roms, target_is_directory=True)
        receipt = gate.inspect(self.exe, shortcut, self.inp, self.wlf,
                               probe=self.response())
        self.assertEqual(receipt["status"], "BLOCKED_NO_PRIVATE_ROM_DIRECTORY")

    def test_version_banner_spoof_is_not_provenance(self):
        receipt = self.inspect(probe=self.response())
        self.assertTrue(receipt["emulator_help_reports_mame_0_106"])
        self.assertFalse(receipt["emulator_binary_provenance_verified"])


if __name__ == "__main__":
    unittest.main()
