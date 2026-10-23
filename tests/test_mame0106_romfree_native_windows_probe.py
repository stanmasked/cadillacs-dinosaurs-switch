"""Synthetic-only tests; no original game resources or captures are used."""
import struct
from pathlib import Path
import tempfile
import unittest
from tools import mame0106_romfree_native_windows_probe as p


class NativeWindowsRomFreeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        exe = bytearray(0x90)
        exe[:2] = b"MZ"
        struct.pack_into("<I", exe, 0x3C, 0x80)
        exe[0x80:0x86] = b"PE\x00\x00\x4c\x01"
        for name in p.FILES:
            (self.root / name).write_bytes(exe if name == "mame0106.exe" else name.encode())
        (self.root / "source-pin.txt").write_text(p.SOURCE_PIN + "\n")
        self.own_sha = p.sha256_file(self.root / "mame0106.exe")
        self.write_manifest()

    def write_manifest(self):
        self.root.joinpath("SHA256SUMS.txt").write_text(
            "".join(f"{p.sha256_file(self.root / name)}  {name}\n" for name in sorted(p.FILES)))

    def test_synthetic_bundle_verifies(self):
        self.assertEqual(p.verify_bundle(self.root, expected_exe_sha=self.own_sha), 8)

    def test_actual_exe_sha_is_required(self):
        with self.assertRaises(p.ProbeError):
            p.verify_bundle(self.root)

    def test_tamper_is_rejected(self):
        (self.root / "mame0106-help.txt").write_text("changed")
        with self.assertRaises(p.ProbeError):
            p.verify_bundle(self.root, expected_exe_sha=self.own_sha)

    def test_untrusted_source_pin_is_rejected(self):
        (self.root / "source-pin.txt").write_text("source_commit=wrong\n")
        with self.assertRaises(p.ProbeError):
            p.verify_bundle(self.root, expected_exe_sha=self.own_sha)

    def test_manifest_traversal_is_rejected(self):
        with (self.root / "SHA256SUMS.txt").open("a") as out:
            out.write("0" * 64 + "  ../private.rom\n")
        with self.assertRaises(p.ProbeError):
            p.verify_bundle(self.root, expected_exe_sha=self.own_sha)

    def test_split_marker_detected(self):
        path = self.root / "synthetic-driver.xml"
        path.write_bytes(b"a" * (65536 - 8) + b'<game name="dino"')
        self.assertTrue(p.contains(path, b'<game name="dino"'))
        self.assertFalse(p.contains(path, b'<game name="other"'))

    def test_wrong_arch_is_rejected(self):
        binary = self.root / "mame0106.exe"
        data = bytearray(binary.read_bytes())
        data[0x84:0x86] = b"\x64\x86"
        binary.write_bytes(data)
        self.write_manifest()
        with self.assertRaises(p.ProbeError):
            p.verify_bundle(self.root, expected_exe_sha=p.sha256_file(binary))


if __name__ == "__main__":
    unittest.main()
