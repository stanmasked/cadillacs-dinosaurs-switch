"""Stage294 synthetic self-consistency checks; unsigned manifests are NOT provenance."""
import hashlib
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path

from tools import wolfmame0106_private_runtime_bundle_gate as gate294

PATCH_MARKERS = (
    "diff --git a/src/inptport.c b/src/inptport.c",
    "diff --git a/src/video.c b/src/video.c",
    "diff --git a/src/video.h b/src/video.h",
    "diff --git a/src/windows/video.c b/src/windows/video.c",
    "diff --git a/src/windows/video.h b/src/windows/video.h",
    "stage290_note_playback_word",
    "mngcounttrace",
    "stage290-mng-counts.csv",
)


class RuntimeBundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dino294-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bundle = self.root / "private-extracted-bundle"
        self.bundle.mkdir()
        self.exe = self.root / "separate-emulator-copy.exe"
        self._make_bundle()

    @staticmethod
    def fake_pe32():
        """Synthetic header, NOT an executable; checksum binding tests only."""
        hdr = bytearray(512)
        hdr[:2] = b"MZ"
        struct.pack_into("<I", hdr, 0x3c, 128)
        hdr[128:132] = b"PE\x00\x00"
        hdr[132:134] = b"\x4c\x01"
        struct.pack_into("<H", hdr, 152, 0x10b)
        return bytes(hdr)

    def _make_bundle(self):
        data = {
            "mame0106.exe": self.fake_pe32(),
            "mame0106-source.zip": b"ARTIFICIAL mame source zip placeholder",
            "mame0106-build-compat.patch": b"synthetic build patch\n",
            "mame0106-windowed-mng-capture.patch": b"synthetic window patch\n",
            "mame0106-inprocess-count-trace-combined.patch": (
                "\n".join(PATCH_MARKERS) + "\n").encode(),
            "dino-driver.xml": b'<mame><game name="dino"/></mame>\n',
            "mame0106-help.txt": b"M.A.M.E. v0.106 - synthetic fixture\n",
            "mame0106-showconfig.txt": (
                b"playback\nmngwrite\nmngstartframe\nmngframes\n"
                b"mngcounttrace\nframes_to_run\n"),
        }
        self.exe.write_bytes(data["mame0106.exe"])
        for name, payload in data.items():
            (self.bundle / name).write_bytes(payload)
        pin = "\n".join(f"{k}={v}" for k, v in
                        gate294.EXPECTED_METADATA.items()) + "\n"
        (self.bundle / "source-pin.txt").write_text(pin)
        self.refresh_manifest()

    def refresh_manifest(self):
        rows = [
            hashlib.sha256((self.bundle / name).read_bytes()).hexdigest()
            + "  " + name
            for name in gate294.EXPECTED_FILES
        ]
        (self.bundle / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n")

    def verify(self):
        return gate294.audit(self.bundle, self.exe)

    def test_synthetic_bundle_is_only_consistent_not_authenticated(self):
        result = self.verify()
        self.assertEqual(result["status"], gate294.STATUS)
        self.assertTrue(result["private_binary_matches_bundle_digest"])
        self.assertTrue(result["source_patch_declares_inprocess_trace"])
        self.assertTrue(result["candidate_executable_is_pe32_i386"])
        self.assertFalse(result["github_artifact_origin_cryptographically_attested"])
        self.assertFalse(result["wolfmame_binary_provenance_independently_verified"])
        self.assertFalse(result["actual_original_inp_playback_verified"])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("0a83d596", json.dumps(result))
        self.assertNotIn("sha256", json.dumps(result))

    def test_changed_executable_copy_rejected(self):
        self.exe.write_bytes(self.fake_pe32() + b"extra")
        with self.assertRaisesRegex(ValueError, "differs"):
            self.verify()

    def test_changed_bundle_file_rejected_even_if_exe_copy_ok(self):
        (self.bundle / "mame0106-source.zip").write_bytes(b"tampered source")
        with self.assertRaisesRegex(ValueError, "manifest"):
            self.verify()

    def test_exact_source_commit_and_opt_in_trace_marker_mandatory(self):
        pin = self.bundle / "source-pin.txt"
        pin.write_text(pin.read_text().replace(
            gate294.EXPECTED_METADATA["source_commit"], "c" * 40))
        with self.assertRaisesRegex(ValueError, "Stage290"):
            self.verify()
        self._make_bundle()
        pin.write_text(pin.read_text().replace(
            "inprocess_counter_trace=enabled_on_request",
            "inprocess_counter_trace=disabled"))
        with self.assertRaisesRegex(ValueError, "Stage290"):
            self.verify()

    def test_absent_source_trace_marker_refused_even_when_rehashed(self):
        patch = self.bundle / "mame0106-inprocess-count-trace-combined.patch"
        patch.write_text(patch.read_text().replace("stage290_note_playback_word", "not_present"))
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.verify()

    def test_missing_command_line_flag_rejected_even_when_rehashed(self):
        config = self.bundle / "mame0106-showconfig.txt"
        config.write_text(config.read_text().replace("mngcounttrace", "unrelated"))
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "option absent"):
            self.verify()

    def test_wrong_pe_machine_or_pe32_plus_rejected(self):
        raw = bytearray(self.fake_pe32())
        raw[132:134] = b"\x64\x86"  # 64-bit x86_64 machine
        self.exe.write_bytes(raw)
        (self.bundle / "mame0106.exe").write_bytes(raw)
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "PE32 Intel"):
            self.verify()
        raw = bytearray(self.fake_pe32())
        struct.pack_into("<H", raw, 152, 0x20b)
        self.exe.write_bytes(raw)
        (self.bundle / "mame0106.exe").write_bytes(raw)
        self.refresh_manifest()
        with self.assertRaisesRegex(ValueError, "PE32"):
            self.verify()

    def test_duplicate_manifest_record_rejected(self):
        manifest = self.bundle / "SHA256SUMS.txt"
        manifest.write_text(manifest.read_text() + manifest.read_text().splitlines()[0] + "\n")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.verify()

    def test_unexpected_manifest_name_rejected(self):
        manifest = self.bundle / "SHA256SUMS.txt"
        manifest.write_text(manifest.read_text() + "0"*64 + "  original-game.rom\n")
        with self.assertRaisesRegex(ValueError, "unexpected"):
            self.verify()

    def test_source_pin_duplicate_value_rejected(self):
        pin = self.bundle / "source-pin.txt"
        pin.write_text(pin.read_text() + "source_tag=mame0106\n")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.verify()

    def test_symlink_member_and_parent_rejected(self):
        target = self.bundle / "mame0106-help.txt"
        twin = self.root / "original-help.txt"
        twin.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(twin)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            self.verify()
        self._make_bundle()
        alias = self.root / "alias"
        alias.symlink_to(self.bundle, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "invalid"):
            gate294.audit(alias, self.exe)

    def test_cli_exclusive_private_success_and_failure_receipts(self):
        output = self.root / "provenance-check.json"
        args = ["--runtime-bundle", str(self.bundle), "--emulator", str(self.exe),
                "--out", str(output)]
        self.assertEqual(gate294.main(args), 0)
        contents = output.read_text()
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.root), contents)
        with self.assertRaises(FileExistsError):
            gate294.main(args)
        self.exe.write_bytes(b"not an executable")
        bad = self.root / "failed-check.json"
        self.assertEqual(gate294.main(args[:-1] + [str(bad)]), 2)
        self.assertEqual(json.loads(bad.read_text())["status"],
                         "BLOCKED_PRIVATE_RUNTIME_BUNDLE_INCONSISTENT")

    def test_native_windows_crlf_cli_captures_allowed(self):
        for filename in ("mame0106-help.txt", "mame0106-showconfig.txt",
                         "dino-driver.xml"):
            path = self.bundle / filename
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.refresh_manifest()
        self.assertEqual(self.verify()["status"], gate294.STATUS)

    def test_changed_bundle_blocks_experiment_before_launch(self):
        from tools import wolfmame0106_private_two_window_experiment as coordinator
        called = []
        args = [
            "--emulator", str(self.exe),
            "--runtime-bundle", str(self.bundle),
            "--rom-dir", str(self.root),
            "--inp", str(self.root / "synthetic.inp"),
            "--wlf", str(self.root / "synthetic.wlf"),
            "--out-dir", str(self.root / "not-to-be-created"),
        ]
        def mock_experiment(*_args, **_kwargs):
            called.append(True)
            return {"status": coordinator.MATCH}
        self.assertEqual(coordinator.main(args, experiment=mock_experiment), 0)
        self.assertEqual(called, [True])
        called.clear()
        (self.bundle / "source-pin.txt").write_text("source_commit=invalid\n")
        self.assertEqual(coordinator.main(args, experiment=mock_experiment), 2)
        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
