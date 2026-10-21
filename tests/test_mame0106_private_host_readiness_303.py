"""Stage303 ROM-free Windows/Wine host capability tests; no real game."""
import json
import tempfile
import unittest
from pathlib import Path

from tools import mame0106_private_host_readiness_303 as host


def fake_pe32():
    fake = bytearray(512)
    fake[:2] = b"MZ"
    fake[60:64] = (128).to_bytes(4, "little")
    fake[128:132] = b"PE\x00\x00"
    fake[132:134] = b"\x4c\x01"
    fake[152:154] = b"\x0b\x01"
    return bytes(fake)


class HostReadinessTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="dino303-executor-only-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.exe = self.root / "historical-synthetic.exe"
        self.exe.write_bytes(fake_pe32())
        self.wine = self.root / "fake-wine-command"
        self.wine.write_text("#!/bin/sh\nexit 1\n")
        self.wine.chmod(0o700)

    def test_actual_pe32_format_can_be_identified_without_execution(self):
        self.assertTrue(host.pe32_i386(self.exe))
        result = host.readiness(self.exe, windows=False, wine=None)
        self.assertEqual(result["status"], host.BLOCKED)
        self.assertTrue(result["mame_pe32_i386_confirmed"])
        self.assertFalse(result["mame_executed"])
        self.assertFalse(result["original_inp_wlf_replayed"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_native_windows_is_candidate_not_a_gameplay_success(self):
        result = host.readiness(self.exe, windows=True)
        self.assertEqual(result["status"], host.READY_WIN)
        self.assertFalse(result["dino_rom_loader_executed"])
        self.assertFalse(result["dino_gameplay_verified"])

    def test_linux_wine_executable_is_unverified_candidate(self):
        result = host.readiness(self.exe, windows=False, wine=self.wine)
        self.assertEqual(result["status"], host.READY_WINE)
        self.assertTrue(result["wine_binary_present"])
        self.assertFalse(result["wine_32bit_runtime_verified"])
        self.assertFalse(result["mame_executed"])

    def test_missing_wine_is_not_accepted(self):
        result = host.readiness(self.exe, windows=False,
                                wine=self.root / "not-installed")
        self.assertEqual(result["status"], host.BLOCKED)
        self.assertFalse(result["wine_binary_present"])

    def test_not_executable_wine_is_not_accepted(self):
        self.wine.chmod(0o600)
        self.assertEqual(
            host.readiness(self.exe, windows=False, wine=self.wine)["status"],
            host.BLOCKED)

    def test_pe32_plus_and_other_cpu_rejected(self):
        pe = bytearray(fake_pe32())
        pe[152:154] = b"\x0b\x02"
        self.exe.write_bytes(pe)
        with self.assertRaisesRegex(ValueError,"i386 PE32"):
            host.pe32_i386(self.exe)
        self.assertEqual(host.readiness(self.exe, wine=self.wine)["status"],
                         host.BLOCKED)
        pe = bytearray(fake_pe32())
        pe[132:134] = b"\x64\x86"
        self.exe.write_bytes(pe)
        self.assertEqual(host.readiness(self.exe, wine=self.wine)["status"],
                         host.BLOCKED)

    def test_bad_pe_offset_and_symlink_rejected(self):
        pe = bytearray(fake_pe32())
        pe[60:64] = (0xFFFFFFFF).to_bytes(4,"little")
        self.exe.write_bytes(pe)
        self.assertEqual(host.readiness(self.exe)["status"],host.BLOCKED)
        self.exe.write_bytes(fake_pe32())
        symlink = self.root / "alias.exe"
        symlink.symlink_to(self.exe)
        with self.assertRaises(ValueError):
            host.pe32_i386(symlink)

    def test_readiness_never_exports_rom_hashes_media_or_paths(self):
        report=host.readiness(self.exe, wine=self.wine, windows=False)
        self.assertFalse(report["private_paths_hashes_or_media_exported"])
        self.assertNotIn(str(self.root),json.dumps(report))
        self.assertFalse(report["physical_nintendo_switch_tested"])

    def test_private_cli_report_stays_exclusive(self):
        target=self.root / "readiness-status.json"
        outcome=host.main(["--mame",str(self.exe),"--out",str(target)])
        self.assertEqual(outcome, 2)
        self.assertEqual(target.stat().st_mode & 0o777,0o600)
        report=json.loads(target.read_text())
        self.assertEqual(report["status"],host.BLOCKED)
        self.assertNotIn(str(self.root),target.read_text())
        with self.assertRaises(ValueError):
            host.main(["--mame",str(self.exe),"--out",str(target)])


if __name__ == "__main__":
    unittest.main()
