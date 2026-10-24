"""Synthetic-only Stage372 evidence separation tests; no actual game files."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import mame0106_private_evidence_gate as gate
from tools import mame0106_private_native_receipt as receipt


class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.path = self.root / 'synthetic-evidence.json'

    def preflight(self):
        return {
            'schema': gate.PREFLIGHT_SCHEMA,
            'stage': 'Stage371', 'checked_utc': '2026-10-24T00:00:08+00:00',
            'archive_bytes': 29169673, 'archive_sha256': gate.STAGE369_SHA256,
            'source_archive_basename': gate.ARCHIVE_NAME,
            'offline_capsule_integrity': 'passed',
            'receipt_generation_script': 'tools/mame0106_private_native_receipt.py',
            'synthetic_test_cases_passed': 19,
            'owner_only_storage_required': True,
            'mame_verifyroms_dino_executed': False,
            'windows_process_started': False,
            'wolfmame_inp_playback_executed': False,
            'physical_switch_tested': False,
            'note': gate.NOTE,
        }

    def write(self, data):
        self.path.write_text(json.dumps(data), encoding='utf-8')

    def test_stage371_offline_grade_not_promoted(self):
        self.write(self.preflight())
        self.assertEqual(gate.audit(self.path), 'offline_preflight_only')
        self.assertEqual(gate.main(['--report', str(self.path), '--require-native-positive']), 3)

    def test_owner_positive_receipt_is_still_self_report(self):
        data = receipt._build_receipt(
            {'status': 'native_verified', 'process_exit_code': 0,
             'exact_status_lines': True},
            nonce='a'*32, when='2026-10-24T00:00:00Z')
        self.write(data)
        self.assertEqual(gate.audit(self.path), 'native_positive_local_self_report')
        self.assertEqual(gate.main(['--report', str(self.path), '--require-native-positive']), 0)

    def test_negative_receipt_blocks_gate(self):
        data = receipt._build_receipt(
            {'status': 'not_verified', 'process_exit_code': 2,
             'exact_status_lines': False},
            nonce='b'*32, when='2026-10-24T00:00:00Z')
        self.write(data)
        self.assertEqual(gate.audit(self.path), 'native_negative_local_self_report')
        self.assertEqual(gate.main(['--report', str(self.path), '--require-native-positive']), 3)

    def test_preflight_cannot_claim_execution(self):
        for field in ('mame_verifyroms_dino_executed',
                      'windows_process_started', 'wolfmame_inp_playback_executed'):
            with self.subTest(field=field):
                data = self.preflight(); data[field] = True
                with self.assertRaises(gate.EvidenceError):
                    gate.classify_evidence(data)

    def test_preflight_tampered_sha_and_extra_raw_data_refused(self):
        for key, value in [('archive_sha256', '0'*64),
                           ('raw_emulator_output', 'PRIVATE'),
                           ('checked_utc', '2026-10-24T00:00:00'),
                           ('synthetic_test_cases_passed', True)]:
            with self.subTest(field=key):
                data = self.preflight(); data[key] = value
                with self.assertRaises(gate.EvidenceError):
                    gate.classify_evidence(data)

    def test_runtime_unsupported_physical_claim_refused(self):
        data = receipt._build_receipt(
            {'status':'native_verified','process_exit_code':0,
             'exact_status_lines':True}, nonce='c'*32,
            when='2026-10-24T00:00:00Z')
        data['physical_nintendo_switch_verified'] = True
        with self.assertRaises(gate.EvidenceError):
            gate.classify_evidence(data)

    def test_duplicate_json_keys_are_refused(self):
        self.path.write_text('{"schema":"x","schema":"y"}', encoding='utf-8')
        with self.assertRaisesRegex(gate.EvidenceError, 'duplicate_json_key'):
            gate.audit(self.path)

    def test_non_json_and_oversized_are_refused(self):
        self.path.write_text('not json', encoding='utf-8')
        with self.assertRaises(gate.EvidenceError):
            gate.audit(self.path)
        self.path.write_bytes(b'Z'*(gate.MAX_REPORT_BYTES+1))
        with self.assertRaises(gate.EvidenceError):
            gate.audit(self.path)

    def test_repository_and_symlink_inputs_refused(self):
        data = self.root / 'source.json'; data.write_text('{}')
        try:
            self.path.symlink_to(data)
        except (OSError, NotImplementedError):
            self.skipTest('Host forbids symlink')
        with self.assertRaises(gate.EvidenceError):
            gate.audit(self.path)

    def test_public_ci_rejects_real_report_read(self):
        self.write(self.preflight())
        with patch.dict('os.environ', {'GITHUB_ACTIONS': 'true'}):
            self.assertEqual(gate.main(['--report', str(self.path)]), 2)

    def test_unknown_schema_refused(self):
        with self.assertRaises(gate.EvidenceError):
            gate.classify_evidence({'schema': 'untrusted'})


if __name__ == '__main__':
    unittest.main()
