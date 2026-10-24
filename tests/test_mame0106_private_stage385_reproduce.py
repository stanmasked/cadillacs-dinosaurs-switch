"""Stage385 ROM-free synthetic tests; never access any original game files."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from tools import mame0106_private_stage385_reproduce as p


class Stage385SyntheticTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name)
        self.gold = self.root / "technical.zip"
        self.cap = self.root / "synthetic-capsule.zip"
        self.report = self.root / "stage384.json"
        self.output = self.root / "stage385.json"
        # Public CI must never read private owner files. Synthetic-only test
        # fixture patches the guard but production module stays guarded.
        guard = patch.object(p.capsule, "guard_private", return_value=None)
        guard.start()
        self.addCleanup(guard.stop)
        self.synthetic = b"SYNTHETIC FIXTURE DATA - NOT A GAME ROM"
        # Exactly 16 synthetic payloads comprising 7,995,392 fake bytes.
        self.payloads = {}
        for n in range(16):
            size = 500000 if n < 15 else 495392
            self.payloads[f"not-game-{n:02d}.bin"] = (
                self.synthetic * (size // len(self.synthetic) + 1))[:size]
        xml = ET.Element("mame")
        game = ET.SubElement(xml, "game", {"name": "dino"})
        for name, content in self.payloads.items():
            ET.SubElement(game, "rom", {
                "name": name, "size": str(len(content)),
                "crc": f"{zipfile.crc32(content) & 0xffffffff:08x}",
                "sha1": hashlib.sha1(content).hexdigest(),
            })
        self.xml = ET.tostring(xml)
        self.rom = self.root / "synthetic-rom.zip"
        with zipfile.ZipFile(self.rom, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for name, data in self.payloads.items():
                z.writestr(name, data)
        with zipfile.ZipFile(self.gold, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("dino-driver.xml", self.xml)
            z.writestr("synthetic-technical.txt", b"public synthetic only")
        with zipfile.ZipFile(self.cap, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.write(self.rom, "roms/dino.zip")
            z.writestr("synthetic-only.txt", b"not original")
        self.report.write_text('{"synthetic":true}', encoding="utf-8")

    def _fake_offline(self, rom, xml):
        return p.romcheck.offline_audit(
            rom, xml,
            rom_sha=p.romcheck.digest(rom),
            xml_sha=p.romcheck.digest(xml))

    def _mock_real_constraints(self):
        """Production pins are bypassed ONLY for all-synthetic fixture files."""
        return [
            patch.object(p, "_read_stage384", return_value={}),
            patch.object(p.capsule, "validate_capsule", return_value={}),
            patch.object(p, "GOLDEN_ZIP_SHA256", hashlib.sha256(self.gold.read_bytes()).hexdigest()),
            patch.object(p, "CAPSULE_SHA256", hashlib.sha256(self.cap.read_bytes()).hexdigest()),
            patch.object(p.golden, "FROZEN_COMPONENT_SHA256", {
                "dino-driver.xml": hashlib.sha256(self.xml).hexdigest(),
                "synthetic-technical.txt": hashlib.sha256(b"public synthetic only").hexdigest(),
            }),
        ]

    def test_real_offline_crc_sha1_recheck_of_16_synthetic_payloads(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for setting in self._mock_real_constraints():
                stack.enter_context(setting)
            stack.enter_context(patch.object(p.romcheck, "guard_public_runner"))
            original = p.romcheck.offline_audit
            def audit(rom, xml):
                return original(rom, xml, rom_sha=p.romcheck.digest(rom),
                                xml_sha=p.romcheck.digest(xml))
            stack.enter_context(patch.object(p.romcheck, "offline_audit", side_effect=audit))
            report = p.reproduce(self.cap, self.gold, self.report)
        self.assertEqual(report["rom_members_verified_crc32_sha1"], 16)
        self.assertEqual(report["rom_payload_bytes_verified"], 7995392)
        for key in ("native_mame_process_executed", "inp_playback_executed",
                    "physical_switch_executed", "independent_windows_attestation",
                    "private_game_bytes_in_report"):
            self.assertIs(report[key], False)
        self.assertEqual(report["status"], "verified_offline_only")

    def test_exact_archive_pin_rejects_changed_golden_zip(self):
        with self.assertRaisesRegex(p.RepeatError, "golden_archive_digest_mismatch"):
            p._verify_golden(self.gold)

    def test_fake_repin_does_not_override_component_checks(self):
        with patch.object(p, "GOLDEN_ZIP_SHA256",
                          hashlib.sha256(self.gold.read_bytes()).hexdigest()):
            with self.assertRaisesRegex(p.RepeatError, "golden_inventory_refused"):
                p._verify_golden(self.gold)

    def test_malformed_stage384_report_rejected(self):
        with self.assertRaisesRegex(p.RepeatError, "stage384_evidence_sha_mismatch"):
            p._read_stage384(self.report)

    def test_double_json_key_rejected_even_when_report_hash_is_supplied(self):
        self.report.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
        with patch.object(p, "STAGE384_REPORT_SHA256",
                          hashlib.sha256(self.report.read_bytes()).hexdigest()):
            with self.assertRaisesRegex(p.RepeatError, "duplicate_json_key"):
                p._read_stage384(self.report)

    def test_nan_refused_even_with_sha_repin(self):
        self.report.write_text('{"schema":NaN}', encoding="utf-8")
        with patch.object(p, "STAGE384_REPORT_SHA256",
                          hashlib.sha256(self.report.read_bytes()).hexdigest()):
            with self.assertRaisesRegex(p.RepeatError, "nonfinite_json_number"):
                p._read_stage384(self.report)

    def test_private_output_must_be_new(self):
        self.output.write_text("never overwrite")
        with self.assertRaisesRegex(p.RepeatError, "output_must_be_new"):
            p._private_output(self.output)
        self.assertEqual(self.output.read_text(), "never overwrite")

    def test_private_output_symlink_parent_refused(self):
        self.output.unlink(missing_ok=True)
        linked = self.root / "linked"
        try:
            linked.symlink_to(self.root, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(p.RepeatError, "linked_output_parent"):
            p._private_output(linked / "new.json")

    def test_public_actions_guard_stops_private_read(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}), patch.object(
                p.capsule, "guard_private", side_effect=p.capsule.CapsuleError(
                    "public_runner_forbidden")):
            with self.assertRaisesRegex(p.capsule.CapsuleError, "public_runner_forbidden"):
                p.reproduce(self.cap, self.gold, self.report)

    def test_cli_private_output_forbidden_to_overwrite(self):
        self.output.write_text("old")
        code = p.main(["--capsule", str(self.cap), "--golden-zip", str(self.gold),
                       "--stage384-report", str(self.report), "--output", str(self.output)])
        self.assertEqual(code, 2)
        self.assertEqual(self.output.read_text(), "old")


if __name__ == "__main__":
    unittest.main()
