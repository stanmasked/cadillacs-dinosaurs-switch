"""Public synthetic tests for private evidence wrapper. No actual ROM/EXE."""
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch, Mock
from tools import mame0106_private_native_receipt as p


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.addCleanup(self._d.cleanup)
        self.root = Path(self._d.name)
        self.archive = self.root / 'synthetic-stage369.zip'
        self.output = self.root / 'private-evidence.json'
        self.fakeobs = {'status': 'native_verified', 'process_exit_code': 0,
                        'exact_status_lines': True}

    def test_exact_three_lines_positive(self):
        self.assertEqual(p._observed_result(0, b'status=native_verified\ngame=dino\nrecording_playback=not_executed\n',b'')['status'], 'native_verified')

    def test_negative_scenarios_fail(self):
        expected=b'\n'.join(x.encode() for x in p.EXPECTED_LINES)
        for code,out,err in [(2,expected,b''),(0,expected+b'\nstatus=native_verified',b''),
                             (0,expected,b'unexpected stderr'),(0,b'status=native_verified\n',b''),
                             (0,b'',b''),(0,b'recording_playback=executed',b'')]:
            with self.subTest(code=code,stdout_len=len(out),stderr_len=len(err)):
                self.assertEqual(p._observed_result(code,out,err)['status'],'not_verified')

    def test_large_or_nonutf8_output_refused(self):
        with self.assertRaisesRegex(p.ReceiptError,'untrusted_script_output_size'):
            p._observed_lines(b'X'*(p.MAX_SCRIPT_OUTPUT+1))
        with self.assertRaisesRegex(p.ReceiptError,'untrusted_script_output_encoding'):
            p._observed_lines(b'\xff')

    def test_recorded_receipt_consistent(self):
        receipt = p._build_receipt(self.fakeobs,nonce='a'*32,when='2026-10-24T00:00:00Z')
        self.assertTrue(p.validate_receipt_object(receipt))
        self.assertEqual(receipt['evidence_type'],p.ATTESTATION)
        self.assertFalse(receipt['wolfmame_inp_playback_executed'])

    def test_receipt_forgery_unsupported_claim_refused(self):
        receipt=p._build_receipt(self.fakeobs,nonce='a'*32,when='2026-10-24T00:00:00Z')
        for key,value in [('wolfmame_inp_playback_executed',True),
                          ('local_windows_powershell_invoked',False),
                          ('exact_three_line_result',False),
                          ('private_rom_sha256','0'*64),
                          ('evidence_type','cryptographically_authenticated'),
                          ('local_session_nonce','NOT-RANDOM'),
                          ('completed_utc','tomorrow')]:
            with self.subTest(field=key):
                modified=dict(receipt);modified[key]=value
                with self.assertRaises(p.ReceiptError):p.validate_receipt_object(modified)

    def test_unknown_keys_refused(self):
        receipt=p._build_receipt(self.fakeobs,nonce='a'*32,when='2026-10-24T00:00:00Z')
        receipt['raw_rom_bytes']='DANGEROUS'
        with self.assertRaisesRegex(p.ReceiptError,'receipt_schema_mismatch'):
            p.validate_receipt_object(receipt)

    def test_write_non_destructive_private_receipt(self):
        receipt=p._build_receipt(self.fakeobs,nonce='a'*32,when='2026-10-24T00:00:00Z')
        p._write_receipt(self.output,receipt)
        self.assertTrue(self.output.exists())
        self.assertTrue(p.validate_receipt_object(json.loads(self.output.read_text())))
        first=self.output.read_bytes()
        with self.assertRaisesRegex(p.ReceiptError,'unsafe_receipt_destination'):
            p._write_receipt(self.output,receipt)
        self.assertEqual(self.output.read_bytes(),first)

    def test_symlink_receipt_refused(self):
        target=self.root/'source.json';target.write_text('{}')
        try:
            self.output.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("host forbids creation of symlinks")
        with self.assertRaisesRegex(p.ReceiptError,'unsafe_receipt_destination'):
            p._safe_receipt_path(self.output)

    def test_public_runner_refuses_before_source_read(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            with self.assertRaises(p.CapsuleError):
                p.run(self.archive,self.output)
        self.assertFalse(self.output.exists())

    def test_linux_guard_is_explicit(self):
        with patch.object(p.os,'name','posix'):
            with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):
                with self.assertRaisesRegex(p.ReceiptError,'private_windows_host_required'):
                    p.run(self.archive,self.output)

    def test_mocked_private_windows_success(self):
        with patch.object(p,'_windows_owner_guard'),patch.object(p,'_validate_stage369_capsule') as verify,patch.object(p,'_stage_and_execute',return_value=self.fakeobs) as execute:
            info=p.run(self.archive,self.output)
        verify.assert_called_once_with(self.archive)
        execute.assert_called_once_with(self.archive)
        self.assertEqual(info['status'],'native_verified')
        self.assertTrue(self.output.is_file())

    def test_mocked_negative_produces_only_negative_receipt(self):
        failed={'status':'not_verified','process_exit_code':2,'exact_status_lines':False}
        with patch.object(p,'_windows_owner_guard'),patch.object(p,'_validate_stage369_capsule'),patch.object(p,'_stage_and_execute',return_value=failed):
            info=p.run(self.archive,self.output)
        self.assertEqual(info['status'],'not_verified')
        data=json.loads(self.output.read_text())
        self.assertEqual(data['native_rom_verification_status'],'not_verified')

    def test_no_console_output_from_subprocess(self):
        # The process observation reports only bounded static markers.
        case=p._observed_result(0,b'\n'.join(x.encode() for x in p.EXPECTED_LINES),b'')
        self.assertNotIn('stdout',p._build_receipt(case))
        self.assertNotIn('stderr',p._build_receipt(case))

    def test_verify_only_cannot_assert_native_execution(self):
        with patch.object(p,'_validate_stage369_capsule') as verify:
            r=p.verify_only(self.archive)
        verify.assert_called_once_with(self.archive)
        self.assertIs(r['native_mame_verification_executed'],False)

    def test_exact_three_lines_rejects_blank_padding(self):
        expected=b'\n'.join(x.encode() for x in p.EXPECTED_LINES)
        for raw in [b'\n'+expected, expected+b'\n\n', b' '+expected, expected+b' ']:
            with self.subTest(raw_size=len(raw)):
                self.assertEqual(p._observed_result(0,raw,b'')['status'],'not_verified')

    def test_synthetic_archive_staged_then_cleaned(self):
        # Every archived byte is manufactured in this test. No actual ROM/EXE.
        import types
        with zipfile.ZipFile(self.archive, 'x') as z:
            for name in p.FIXED_FILES:
                z.writestr(name, b'synthetic-only:' + name.encode('ascii'))
        seen=[]
        def fake_subprocess(argv,**kwargs):
            root=Path(kwargs['cwd'])
            seen.append(root)
            self.assertEqual(Path(argv[-1]).name,'verifyroms.ps1')
            for name in p.FIXED_FILES:
                self.assertTrue((root / name).is_file())
            self.assertEqual(kwargs['stdin'],p.subprocess.DEVNULL)
            self.assertEqual(kwargs['timeout'],135)
            return types.SimpleNamespace(returncode=0,
                stdout=b'\n'.join(x.encode() for x in p.EXPECTED_LINES)+b'\n',stderr=b'')
        with patch.object(p, 'STAGE369_SHA256', p.hashfile(self.archive)[0]), \
             patch.object(p, '_validate_stage369_capsule') as check, \
             patch.object(p.subprocess,'run',side_effect=fake_subprocess):
            result=p._stage_and_execute(self.archive)
            check.assert_called_once()
        self.assertEqual(result['status'],'native_verified')
        self.assertEqual(len(seen),1)
        self.assertFalse(seen[0].exists())

    def test_synthetic_subprocess_failure_not_success(self):
        import types
        with zipfile.ZipFile(self.archive,'x') as z:
            for name in p.FIXED_FILES:
                z.writestr(name,b'SYNTHETIC')
        with patch.object(p, 'STAGE369_SHA256', p.hashfile(self.archive)[0]), \
             patch.object(p, '_validate_stage369_capsule'), \
             patch.object(p.subprocess,'run',return_value=types.SimpleNamespace(returncode=9,stdout=b'status=native_verified\ngame=dino\nrecording_playback=not_executed\n',stderr=b'')):
            result=p._stage_and_execute(self.archive)
        self.assertEqual(result['status'],'not_verified')

    def test_synthetic_subprocess_timeout_fails_closed(self):
        import subprocess
        with zipfile.ZipFile(self.archive,'x') as z:
            for name in p.FIXED_FILES:
                z.writestr(name,b'SYNTHETIC')
        with patch.object(p, 'STAGE369_SHA256', p.hashfile(self.archive)[0]), \
             patch.object(p, '_validate_stage369_capsule'), \
             patch.object(p.subprocess,'run',side_effect=subprocess.TimeoutExpired('SYNTHETIC',135)):
            with self.assertRaisesRegex(p.ReceiptError,'private_powershell_execution_not_completed'):
                p._stage_and_execute(self.archive)

    def test_stage377_snapshot_requires_exact_pinned_bytes(self):
        # A complete synthetic ZIP must NEVER pass the production SHA pin.
        with zipfile.ZipFile(self.archive, 'x') as z:
            for name in p.FIXED_FILES:
                z.writestr(name, b'SYNTHETIC-ONLY')
        destination = self.root / 'synthetic-snapshot.zip'
        with self.assertRaisesRegex(p.ReceiptError, 'private_snapshot_digest_mismatch'):
            p._snapshot_private_capsule(self.archive, destination)
        self.assertTrue(destination.exists())

    def test_stage377_snapshot_matches_synthetic_bytes_with_test_pin(self):
        with zipfile.ZipFile(self.archive, 'x') as z:
            for name in p.FIXED_FILES:
                z.writestr(name, b'SYNTHETIC-ONLY')
        destination = self.root / 'synthetic-snapshot.zip'
        digest = p.hashfile(self.archive)[0]
        with patch.object(p, 'STAGE369_SHA256', digest):
            p._snapshot_private_capsule(self.archive, destination)
        self.assertEqual(destination.read_bytes(), self.archive.read_bytes())

    def test_stage377_rejects_source_swapped_after_preflight(self):
        with zipfile.ZipFile(self.archive, 'x') as z:
            for name in p.FIXED_FILES:
                z.writestr(name, b'SYNTHETIC ORIGINAL')
        original_sha = p.hashfile(self.archive)[0]
        checks = []
        def replaced_during_first_check(_archive):
            checks.append(1)
            if len(checks) == 1:
                self.archive.unlink()
                with zipfile.ZipFile(self.archive, 'x') as replacement:
                    for name in p.FIXED_FILES:
                        replacement.writestr(name, b'SYNTHETIC REPLACEMENT')
            return {'status': 'offline_capsule_integrity_pass'}
        with patch.object(p, '_windows_owner_guard'), \
             patch.object(p, 'STAGE369_SHA256', original_sha), \
             patch.object(p, '_validate_stage369_capsule', side_effect=replaced_during_first_check), \
             patch.object(p.subprocess, 'run') as execute:
            with self.assertRaisesRegex(p.ReceiptError, 'private_snapshot_digest_mismatch'):
                p.run(self.archive, self.output)
        execute.assert_not_called()
        self.assertEqual(len(checks), 1)
        self.assertFalse(self.output.exists())

    def test_stage377_staged_bytes_are_revalidated_before_execution(self):
        with zipfile.ZipFile(self.archive, 'x') as z:
            for name in p.FIXED_FILES:
                z.writestr(name, b'SYNTHETIC')
        original_sha = p.hashfile(self.archive)[0]
        # A second ZIP/member audit of the exact pinned snapshot is mandatory,
        # even though the caller already checked its original path.
        with patch.object(p, 'STAGE369_SHA256', original_sha), \
             patch.object(p, '_validate_stage369_capsule', side_effect=p.ReceiptError('staged_audit_failed')) as audit, \
             patch.object(p.subprocess, 'run') as execute:
            with self.assertRaisesRegex(p.ReceiptError, 'staged_audit_failed'):
                p._stage_and_execute(self.archive)
        audit.assert_called_once()
        self.assertNotEqual(audit.call_args.args[0], self.archive)
        execute.assert_not_called()

    def test_main_public_guard_no_report(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            ret=p.main(['--capsule',str(self.archive),'--receipt',str(self.output)])
        self.assertEqual(ret,2)
        self.assertFalse(self.output.exists())


if __name__=='__main__':
    unittest.main()
