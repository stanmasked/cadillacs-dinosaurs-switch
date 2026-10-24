"""Stage376 public synthetic fixtures; no original ROMs or MAME data."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import mame0106_private_execution_session as p
from tools import mame0106_private_native_receipt as native
from tools import mame0106_private_evidence_gate as gate


class OwnerPrivateSessionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.capsule = self.root / 'synthetic-only.zip'
        self.session = self.root / 'synthetic-session'

    def _fake_run(self, positive=True):
        def stub(_capsule, path):
            observation = {
                'status': 'native_verified' if positive else 'not_verified',
                'process_exit_code': 0 if positive else 2,
                'exact_status_lines': positive,
            }
            value = native._build_receipt(
                observation, nonce='f'*32, when='2026-10-24T00:00:00Z')
            native._write_receipt(path, value)
            return {'status': observation['status'], 'receipt_written': True,
                    'recording_playback': 'not_executed'}
        return stub

    def _invoke_synthetic(self, positive=True):
        with patch.object(native, '_windows_owner_guard'), \
             patch.object(native, 'run', side_effect=self._fake_run(positive)), \
             patch.object(gate, 'guard_private', return_value=None):
            return p.execute(self.capsule, self.session)

    def test_positive_receipt_and_manifest_are_consistent(self):
        result = self._invoke_synthetic()
        self.assertEqual(result['status'], 'native_positive_local_self_report')
        manifest = json.loads((self.session / p.MANIFEST_NAME).read_text())
        raw = (self.session / p.RECEIPT_NAME).read_bytes()
        self.assertEqual(manifest['receipt_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(manifest['receipt_bytes'], len(raw))
        self.assertEqual(manifest['capsule_sha256'], native.STAGE369_SHA256)
        self.assertFalse(manifest['wolfmame_inp_playback_executed'])
        self.assertFalse(manifest['physical_nintendo_switch_verified'])
        self.assertTrue(manifest['local_self_report_only'])
        self.assertTrue(manifest['owner_only_archive_required'])
        self.assertEqual({x.name for x in self.session.iterdir()},
                         {p.RECEIPT_NAME, p.MANIFEST_NAME})

    def test_negative_receipt_cannot_be_upgraded(self):
        result = self._invoke_synthetic(False)
        self.assertEqual(result['status'], 'native_negative_local_self_report')
        manifest = json.loads((self.session / p.MANIFEST_NAME).read_text())
        self.assertFalse(manifest['native_rom_verification_positive'])
        self.assertEqual(manifest['evidence_grade'],
                         'native_negative_local_self_report')

    def test_repeat_session_is_non_destructive(self):
        self._invoke_synthetic()
        original = (self.session / p.MANIFEST_NAME).read_bytes()
        with self.assertRaisesRegex(p.SessionError, 'session_must_be_new'):
            self._invoke_synthetic()
        self.assertEqual((self.session / p.MANIFEST_NAME).read_bytes(), original)

    def test_public_ci_guard_refuses_before_writing(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS': 'true'}):
            self.assertEqual(p.main(['--capsule', str(self.capsule),
                                     '--session-dir', str(self.session)]), 2)
        self.assertFalse(self.session.exists())

    def test_non_windows_host_guard_refuses_before_writing(self):
        with patch.object(native.os, 'name', 'posix'):
            with patch.dict(os.environ, {'GITHUB_ACTIONS': 'false'}):
                self.assertEqual(p.main(['--capsule', str(self.capsule),
                                         '--session-dir', str(self.session)]), 2)
        self.assertFalse(self.session.exists())

    def test_parent_symlink_refused(self):
        alias = self.root / 'alias'
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except (NotImplementedError, OSError):
            self.skipTest('Host forbids symlinks')
        with self.assertRaisesRegex(p.SessionError, 'reparse_refused'):
            p._private_new_session_path(alias / 'new-private-session')

    def test_existing_session_is_never_overwritten(self):
        self.session.mkdir()
        marker = self.session / 'preserve.txt'
        marker.write_text('SYNTHETIC')
        with self.assertRaisesRegex(p.SessionError, 'session_must_be_new'):
            p._private_new_session_path(self.session)
        self.assertEqual(marker.read_text(), 'SYNTHETIC')

    def test_mismatch_between_process_and_evidence_fails_closed(self):
        def forged(_capsule, path):
            self._fake_run(False)(_capsule, path)
            return {'status': 'native_verified'}
        with patch.object(native, '_windows_owner_guard'), \
             patch.object(native, 'run', side_effect=forged), \
             patch.object(gate, 'guard_private', return_value=None):
            with self.assertRaisesRegex(p.SessionError, 'evidence_disagrees'):
                p.execute(self.capsule, self.session)
        self.assertTrue((self.session / p.RECEIPT_NAME).is_file())
        self.assertFalse((self.session / p.MANIFEST_NAME).exists())

    def test_failed_capsule_verification_leaves_no_success_manifest(self):
        with patch.object(native, '_windows_owner_guard'), \
             patch.object(native, 'run', side_effect=native.ReceiptError('synthetic_failure')):
            with self.assertRaises(native.ReceiptError):
                p.execute(self.capsule, self.session)
        self.assertTrue(self.session.is_dir())
        self.assertFalse((self.session / p.MANIFEST_NAME).exists())

    def test_report_contains_no_original_inputs_or_raw_game_output(self):
        self._invoke_synthetic()
        for entry in self.session.iterdir():
            content = entry.read_text()
            self.assertNotIn('dino.inp', content)
            self.assertNotIn('dino.wlf', content)
            self.assertNotIn('roms/dino.zip', content)
            self.assertNotIn('raw_mame_output', content)


if __name__ == '__main__':
    unittest.main()
