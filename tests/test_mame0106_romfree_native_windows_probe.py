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


class FrozenArtifactPinsTests(NativeWindowsRomFreeTests):
    """Completely synthetic, public test data; no real executable or ROM."""

    def synthetic_frozen_pins(self):
        for name in ("MAME-0106-LICENSE.txt", "runtime-status.txt"):
            (self.root / name).write_text("SYNTHETIC " + name, encoding="utf-8")
        return {name: p.sha256_file(self.root / name)
                for name in p.FROZEN_COMPONENT_SHA256}

    def test_all_synthetic_frozen_components_match(self):
        pins = self.synthetic_frozen_pins()
        self.assertEqual(p.verify_frozen_components(self.root, pins), 12)

    def test_rewritten_manifest_not_sufficient_for_provenance(self):
        pins = self.synthetic_frozen_pins()
        (self.root / "mame0106-help.txt").write_text("FORGED BUT CONSISTENT", encoding="utf-8")
        self.write_manifest()
        self.assertEqual(p.verify_bundle(self.root, expected_exe_sha=self.own_sha), 8)
        with self.assertRaisesRegex(p.ProbeError, "frozen_component_mismatch"):
            p.verify_frozen_components(self.root, pins)

    def test_unexpected_extra_component_rejected(self):
        pins = self.synthetic_frozen_pins()
        (self.root / "untrusted-private.bin").write_bytes(b"SYNTHETIC")
        with self.assertRaisesRegex(p.ProbeError, "frozen_inventory_mismatch"):
            p.verify_frozen_components(self.root, pins)

    def test_missing_component_rejected(self):
        pins = self.synthetic_frozen_pins()
        (self.root / "runtime-status.txt").unlink()
        with self.assertRaisesRegex(p.ProbeError, "frozen_inventory_mismatch"):
            p.verify_frozen_components(self.root, pins)

    def test_original_pins_not_satisfied_by_synthetic_files(self):
        self.synthetic_frozen_pins()
        with self.assertRaisesRegex(p.ProbeError, "frozen_component_mismatch"):
            p.verify_frozen_components(self.root)

    def test_symlink_to_valid_bytes_rejected(self):
        pins = self.synthetic_frozen_pins()
        source = self.root / "mame0106-help.txt"
        copy = self.root.parent / "public-synthetic-copy.txt"
        copy.write_bytes(source.read_bytes())
        source.unlink()
        try:
            source.symlink_to(copy)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaisesRegex(p.ProbeError, "frozen_member_type"):
            p.verify_frozen_components(self.root, pins)

    def test_invalid_digest_and_path_pin_rejected(self):
        pins = self.synthetic_frozen_pins()
        for forged in ({**pins, "source-pin.txt": "INVALID"},
                       {**pins, "../fake": "0"*64}):
            with self.subTest(keys=list(forged)[-1]):
                with self.assertRaises(p.ProbeError):
                    p.verify_frozen_components(self.root, forged)


if __name__ == "__main__":
    unittest.main()
