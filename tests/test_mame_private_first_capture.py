"""ROM-free first-run handoff CLI regressions with synthetic dino data only."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_private_first_capture import (
    _successful_capture, _safe_failure, main, private_first_capture_handoff,
)
from tools.mame_private_dino_session import REPORT_NAME, CAPTURE_DIR_NAME
from tools.mame_private_auto_exit_evidence import READY_LINE
from test_mame_private_guarded_capture import GuardedCaptureTests


class PrivateFirstCaptureHandoffTests(unittest.TestCase):
    def setUp(self):
        fixture = GuardedCaptureTests(
            methodName='test_audit_before_game_uses_separate_process_without_token')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.arguments = [
            '--mame', str(fixture.mame),
            '--mame-tree', str(fixture.tree),
            '--rom-dir', str(fixture.roms),
            '--workspace', str(fixture.workspace),
        ]

    def invoke(self, extra=(), runner=None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fixture.fake_build), \
             patch('tools.mame_private_dino_session.subprocess.run',
                   side_effect=runner) as proc, \
             contextlib.redirect_stdout(stdout), \
             contextlib.redirect_stderr(stderr):
            code = main(self.arguments + list(extra))
        return code, stdout.getvalue(), stderr.getvalue(), proc

    def test_default_mode_only_checks_rom_free_readiness(self):
        def subprocess_called(*args, **kwargs):
            self.fail('ROM-free metadata readiness must not call game subprocess')
        rc, stdout, stderr, proc = self.invoke(runner=subprocess_called)
        self.assertEqual(rc, 0)
        self.assertEqual(stderr, '')
        proc.assert_not_called()
        result = json.loads(stdout)
        self.assertEqual(result['schema'], 'PRIVATE_DINO_FIRST_CAPTURE_HANDOFF_V1')
        self.assertEqual(result['status'],
                         'PRIVATE_DINO_FIRST_CAPTURE_READINESS_METADATA_ONLY')
        self.assertTrue(result['mame_instrumented_build_checked'])
        self.assertTrue(result['private_game_entry_observed'])
        self.assertTrue(result['requires_explicit_run_for_original_game'])
        self.assertFalse(result['original_rom_bytes_read'])
        self.assertFalse(result['game_executed'])
        self.assertFalse(result['pixel_parity_eligible'])
        self.assertFalse((self.fixture.workspace / CAPTURE_DIR_NAME).exists())
        self.assertFalse((self.fixture.workspace / REPORT_NAME).exists())

    def test_explicit_run_gates_game_after_private_rom_check(self):
        observed = []
        f = self.fixture
        def callback(args, **kwargs):
            observed.append((args, kwargs['env'].get('CPS1_DINO_AUTO_EXIT_AFTER_CAPTURE')))
            if '-verifyroms' in args:
                self.assertIsNone(observed[-1][1])
                return subprocess.CompletedProcess(args, 0)
            self.assertEqual(observed[-1][1], '1')
            kwargs['stdout'].write(b'SECRET FILE /private/roms/dino.zip\n')
            kwargs['stdout'].write(READY_LINE + b'\n')
            return f.fake_game(args, kwargs['env']['CPS1_DINO_CAPTURE_SESSION'])
        rc, stdout, stderr, proc = self.invoke(['--run'], callback)
        self.assertEqual(rc, 0)
        self.assertEqual(stderr, '')
        self.assertEqual(proc.call_count, 2)
        self.assertIn('-verifyroms', observed[0][0])
        self.assertIn('-autoboot_script', observed[1][0])
        out = json.loads(stdout)
        self.assertEqual(out['status'], 'PRIVATE_SIX_FRAME_STRUCTURAL_AUDIT_PASSED')
        self.assertTrue(out['local_mame_rom_audit_exited_zero'])
        self.assertTrue(out['local_original_rom_sha256_stable'])
        self.assertEqual(out['verified_file_count'], 54)
        self.assertEqual(out['auto_exit_marker_status'],
                         'LOCAL_LUA_REPORTED_SIZE_READY_EXIT')
        self.assertFalse(out['physical_vblank_verified'])
        self.assertNotIn('/private/roms/', stdout)
        self.assertNotIn('dino.zip', stdout)
        self.assertNotIn('reference_activity', stdout)
        self.assertTrue((f.workspace / REPORT_NAME).is_file())

    def test_verifyroms_failure_is_redacted_and_has_no_game_capture(self):
        def callback(args, **kwargs):
            self.assertIn('-verifyroms', args)
            kwargs['stdout'].write(b'PRIVATE ROM /private/owned/dino.zip')
            return subprocess.CompletedProcess(args, 4)
        rc, stdout, stderr, proc = self.invoke(['--run'], callback)
        self.assertEqual(rc, 2)
        self.assertEqual(stdout, '')
        self.assertEqual(proc.call_count, 1)
        out = json.loads(stderr)
        self.assertEqual(out['status'], 'PRIVATE_DINO_FIRST_CAPTURE_REFUSED')
        self.assertEqual(out['reason_code'], 'PRIVATE_MAME_ROMSET_AUDIT_FAILED')
        self.assertEqual(out['capture_progress_status'],
                         'NO_PRIVATE_CAPTURE_DIRECTORY')
        self.assertFalse((self.fixture.workspace / CAPTURE_DIR_NAME).exists())
        self.assertNotIn('/private/owned/', stderr)
        self.assertNotIn('dino.zip', stderr)

    def test_partial_game_capture_refuses_and_reports_only_counts(self):
        f = self.fixture
        def callback(args, **kwargs):
            if '-verifyroms' in args:
                return subprocess.CompletedProcess(args, 0)
            (f.workspace / CAPTURE_DIR_NAME /
             'frame-00000900.manifest.json').write_bytes(b'{}')
            return subprocess.CompletedProcess(args, 8)
        rc, stdout, stderr, proc = self.invoke(['--run'], callback)
        self.assertEqual(rc, 2)
        self.assertEqual(stdout, '')
        self.assertEqual(proc.call_count, 2)
        out = json.loads(stderr)
        self.assertEqual(out['reason_code'], 'LOCAL_MAME_PROCESS_FAILED')
        self.assertEqual(out['capture_progress_status'],
                         'INCOMPLETE_PRIVATE_CAPTURE_FILE_SET')
        self.assertEqual(out['present_files'], 1)
        self.assertEqual(out['missing_files'], 53)
        self.assertFalse(out['active_gameplay_verified'])
        self.assertFalse((f.workspace / REPORT_NAME).exists())
        self.assertNotIn('manifest.json', stderr)

    def test_preflight_failure_does_not_disclose_private_paths(self):
        self.fixture.mame.unlink()
        rc, stdout, stderr, proc = self.invoke()
        self.assertEqual(rc, 2)
        self.assertEqual(stdout, '')
        self.assertNotIn(str(self.fixture.root), stderr)
        out = json.loads(stderr)
        self.assertEqual(out['status'], 'PRIVATE_DINO_FIRST_CAPTURE_REFUSED')
        self.assertNotIn('capture_progress_status', out)

    def test_timeout_argument_rejected_without_starting_mame(self):
        rc, stdout, stderr, proc = self.invoke(
            ['--run', '--timeout-seconds', '4'])
        self.assertEqual(rc, 2)
        self.assertEqual(stdout, '')
        proc.assert_not_called()
        self.assertEqual(json.loads(stderr)['reason_code'],
                         'INVALID_LAUNCH_ARGUMENTS')
        self.assertFalse((self.fixture.workspace / REPORT_NAME).exists())

    def test_malicious_inner_success_with_private_strings_is_rejected(self):
        forged = {
            'status': 'PRIVATE_CAPTURE_INTEGRITY_VERIFIED_ONLY',
            'game_executed': True,
            'nominal_frame_count': 6,
            'crc32_lua_components_checked': 30,
            'bound_cpp_obj_samples': 6,
            'local_mame_verifyroms_exit_zero_before_capture': True,
            'private_rom_content_sha256_stable_during_capture': True,
            'auto_exit_after_capture_requested': True,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
            'original_game_data': '/private/owned/dino.zip',
            'private_logger': 'ROM SHA256 PROPRIETARY',
            'auto_exit_log_observation': {
                'status': 'LOCAL_LUA_REPORTED_SIZE_READY_EXIT',
                'secret': 'PRIVATE'},
            'auto_exit_post_run_reconciliation': {
                'status': 'READY_MESSAGE_AGREES_WITH_SIZE_ONLY_FILES',
                'some_bytes': 'SECRET'},
        }
        projected = _successful_capture(forged)
        self.assertEqual(projected['verified_file_count'], 54)
        self.assertNotIn('original_game_data', projected)
        self.assertNotIn('/private/', json.dumps(projected))
        self.assertNotIn('SECRET', json.dumps(projected))
        self.assertNotIn('PROPRIETARY', json.dumps(projected))
        forged['frame_sync_verified'] = True
        with self.assertRaises(ValueError):
            _successful_capture(forged)

    def test_inner_helpers_cannot_print_original_paths_from_wrapped_call(self):
        def fake_inner(*args, **kwargs):
            print('SECRET PRIVATE ROM /unshared/dino.zip')
            raise ValueError('Private dino ROM changed /unshared/dino.zip')
        rc, stdout, stderr = None, io.StringIO(), io.StringIO()
        with patch('tools.mame_private_first_capture.execute_private_capture',
                   side_effect=fake_inner), \
             contextlib.redirect_stdout(stdout), \
             contextlib.redirect_stderr(stderr):
            rc = main(self.arguments + ['--run'])
        self.assertEqual(rc, 2)
        self.assertEqual(stdout.getvalue(), '')
        self.assertNotIn('SECRET', stderr.getvalue())
        self.assertNotIn('/unshared/', stderr.getvalue())
        self.assertEqual(json.loads(stderr.getvalue())['status'],
                         'PRIVATE_DINO_FIRST_CAPTURE_REFUSED')

    def test_inner_readiness_inconsistent_cannot_be_reported_ready(self):
        with patch('tools.mame_private_first_capture.execute_private_capture',
                   return_value={'status': 'PRIVATE_DINO_LAUNCH_PREFLIGHT_ONLY',
                                 'private_rom_entry_observed': False,
                                 'printed_rom': '/private/original'}):
            with self.assertRaises(ValueError):
                private_first_capture_handoff(
                    self.fixture.mame, self.fixture.tree, self.fixture.roms,
                    self.fixture.workspace)

    def test_false_positive_nested_status_cannot_upgrade_failure(self):
        with patch('tools.mame_private_first_capture.safe_capture_failure_report',
                   return_value={'reason_code': 'LOCAL_MAME_PROCESS_FAILED',
                                 'capture_progress': {
                                     'status': '/private/sensitive',
                                     'present_files': 999,
                                     'missing_files': True}}):
            output = _safe_failure(ValueError('fake'), self.fixture.workspace, True)
        self.assertEqual(output['capture_progress_status'],
                         'PRIVATE_CAPTURE_PROGRESS_REFUSED')
        self.assertNotIn('present_files', output)
        self.assertNotIn('missing_files', output)
        self.assertNotIn('/private/sensitive', json.dumps(output))


if __name__ == '__main__':
    unittest.main()
