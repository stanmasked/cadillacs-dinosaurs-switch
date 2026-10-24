"""Stage379 offline auditor, entirely synthetic: no ROM, INP/WLF, or MAME."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import mame0106_private_session_audit as p
from tools import mame0106_private_execution_session as session
from tools import mame0106_private_native_receipt as native
from tools import mame0106_private_evidence_gate as gate


class SyntheticPrivateSessionAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.folder = self.root / "synthetic-stage376"
        self.folder.mkdir()
        self._guard = patch.object(p, "guard_private", return_value=None)
        self._guard.start()
        self.addCleanup(self._guard.stop)

    def write_evidence(self, positive=True):
        observation = {
            "status": "native_verified" if positive else "not_verified",
            "process_exit_code": 0 if positive else 2,
            "exact_status_lines": positive,
        }
        receipt = native._build_receipt(
            observation, nonce="f"*32, when="2026-10-24T00:00:00Z")
        data = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
        (self.folder / session.RECEIPT_NAME).write_bytes(data)
        grade = ("native_positive_local_self_report" if positive
                 else "native_negative_local_self_report")
        manifest = {
            "schema": session.SCHEMA,
            "stage": "Stage376",
            "game": "dino",
            "created_utc": "2026-10-24T00:00:01Z",
            "capsule_sha256": native.STAGE369_SHA256,
            "receipt_file": session.RECEIPT_NAME,
            "receipt_sha256": hashlib.sha256(data).hexdigest(),
            "receipt_bytes": len(data),
            "evidence_grade": grade,
            "local_self_report_only": True,
            "native_rom_verification_positive": positive,
            "wolfmame_inp_playback_executed": False,
            "physical_nintendo_switch_verified": False,
            "owner_only_archive_required": True,
        }
        self.set_manifest(manifest)
        return manifest

    def set_manifest(self, obj):
        (self.folder / session.MANIFEST_NAME).write_text(
            json.dumps(obj, sort_keys=True, indent=2) + "\n", encoding="utf-8")

    def test_positive_local_self_report_only(self):
        self.write_evidence()
        self.assertEqual(p.audit(self.folder), "native_positive_local_self_report")
        self.assertEqual(p.main(["--session-dir", str(self.folder),
                                 "--require-native-positive"]), 0)

    def test_negative_report_remains_negative(self):
        self.write_evidence(positive=False)
        self.assertEqual(p.audit(self.folder), "native_negative_local_self_report")
        self.assertEqual(p.main(["--session-dir", str(self.folder),
                                 "--require-native-positive"]), 3)

    def test_no_private_inputs_accessed(self):
        self.write_evidence()
        original = (self.folder / session.RECEIPT_NAME).read_bytes()
        self.assertEqual(p.audit(self.folder), "native_positive_local_self_report")
        self.assertEqual((self.folder / session.RECEIPT_NAME).read_bytes(), original)
        self.assertEqual({x.name for x in self.folder.iterdir()}, p.EXPECTED_FILES)

    def test_mutated_receipt_rejected(self):
        self.write_evidence()
        file = self.folder / session.RECEIPT_NAME
        file.write_bytes(file.read_bytes() + b" ")
        with self.assertRaisesRegex(p.SessionAuditError, "checksum_mismatch"):
            p.audit(self.folder)

    def test_manifest_checksum_forged_but_receipt_grade_invalid(self):
        m = self.write_evidence(positive=False)
        m["native_rom_verification_positive"] = True
        m["evidence_grade"] = "native_positive_local_self_report"
        self.set_manifest(m)
        with self.assertRaisesRegex(p.SessionAuditError, "grade_conflict"):
            p.audit(self.folder)

    def test_manifest_claim_only_change_rejected(self):
        m = self.write_evidence()
        m["wolfmame_inp_playback_executed"] = True
        self.set_manifest(m)
        with self.assertRaisesRegex(p.SessionAuditError, "provenance_mismatch"):
            p.audit(self.folder)

    def test_manifest_capsule_pin_mismatch(self):
        m = self.write_evidence()
        m["capsule_sha256"] = "0"*64
        self.set_manifest(m)
        with self.assertRaisesRegex(p.SessionAuditError, "provenance_mismatch"):
            p.audit(self.folder)

    def test_manifest_time_predates_receipt(self):
        m = self.write_evidence()
        m["created_utc"] = "2026-10-23T23:00:00Z"
        self.set_manifest(m)
        with self.assertRaisesRegex(p.SessionAuditError, "predates_receipt"):
            p.audit(self.folder)

    def test_missing_or_extra_file_rejected(self):
        self.write_evidence()
        (self.folder / "synthetic-extra.txt").write_text("only synthetic")
        with self.assertRaisesRegex(p.SessionAuditError, "unexpected_session_inventory"):
            p.audit(self.folder)
        (self.folder / "synthetic-extra.txt").unlink()
        (self.folder / session.RECEIPT_NAME).unlink()
        with self.assertRaisesRegex(p.SessionAuditError, "unexpected_session_inventory"):
            p.audit(self.folder)

    def test_duplicate_json_keys_rejected(self):
        self.write_evidence()
        file = self.folder / session.MANIFEST_NAME
        file.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
        with self.assertRaisesRegex(p.SessionAuditError, "invalid_session_json"):
            p.audit(self.folder)

    def test_nonfinite_json_rejected(self):
        self.write_evidence()
        file = self.folder / session.MANIFEST_NAME
        file.write_text('{"schema":NaN}', encoding="utf-8")
        with self.assertRaisesRegex(p.SessionAuditError, "invalid_session_json"):
            p.audit(self.folder)

    def test_symlink_to_valid_receipt_rejected(self):
        self.write_evidence()
        file = self.folder / session.RECEIPT_NAME
        outside = self.root / "synthetic-copy.json"
        outside.write_bytes(file.read_bytes())
        file.unlink()
        try:
            file.symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaisesRegex(p.SessionAuditError, "session_member_link_forbidden"):
            p.audit(self.folder)

    def test_parent_symlink_refused(self):
        self.write_evidence()
        alias = self.root / "synthetic-alias"
        try:
            alias.symlink_to(self.folder, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable")
        with self.assertRaisesRegex(p.SessionAuditError, "unsafe_session_directory"):
            p.audit(alias)

    def test_oversized_manifest_rejected(self):
        self.write_evidence()
        (self.folder / session.MANIFEST_NAME).write_bytes(b"x"*(p.MAX_JSON_BYTES+1))
        with self.assertRaisesRegex(p.SessionAuditError, "invalid_session_member_size"):
            p.audit(self.folder)

    def test_bool_receipt_length_rejected(self):
        m = self.write_evidence()
        m["receipt_bytes"] = True
        self.set_manifest(m)
        with self.assertRaisesRegex(p.SessionAuditError, "checksum_mismatch"):
            p.audit(self.folder)

    def test_public_actions_guard_refuses(self):
        self.write_evidence()
        with patch.object(p, "guard_private", side_effect=gate.CapsuleError(
                "public_runner_forbidden")):
            self.assertEqual(p.main(["--session-dir", str(self.folder)]), 2)

    def test_recompute_manifest_sha_does_not_authenticate_replaced_receipt(self):
        m = self.write_evidence()
        # Even a matching new digest cannot promote a malformed local report.
        payload = b'{"schema":"unknown","native_rom_verification_status":"native_verified"}'
        (self.folder / session.RECEIPT_NAME).write_bytes(payload)
        m["receipt_sha256"] = hashlib.sha256(payload).hexdigest()
        m["receipt_bytes"] = len(payload)
        self.set_manifest(m)
        with self.assertRaisesRegex(p.SessionAuditError, "invalid_private_runtime_receipt"):
            p.audit(self.folder)


if __name__ == "__main__":
    unittest.main()
