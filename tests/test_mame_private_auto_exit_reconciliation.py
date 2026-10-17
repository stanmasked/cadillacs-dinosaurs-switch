"""ROM-free crosschecks of observed Lua auto-exit reason and final files."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_private_auto_exit_reconciliation import (
    reconcile_auto_exit_with_capture,
)
from tools.mame_private_auto_exit_evidence import (
    READY_LINE, GRACE_LINE, private_mame_auto_exit_log_observation,
)
from tools.mame_private_dino_session import (
    CAPTURE_DIR_NAME, REPORT_NAME, execute_private_capture, main,
)
from tools.mame_private_capture_failure_summary import safe_progress_projection
from tools.mame_private_capture_progress import private_capture_progress
from test_mame_private_guarded_capture import GuardedCaptureTests


def marker(status):
    return {'status': status, 'marker_observed': True,
            'secret_rom_path': '/private/original/dino.zip',
            'private_log': 'SECRET GAME FILES'}


class AutoExitPureReconciliationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.workspace = self.root / 'isolated'
        self.workspace.mkdir(mode=0o700)

    def progress(self):
        return safe_progress_projection(private_capture_progress(self.workspace))

    def test_ready_marker_and_strict_completed_capture_compatible_only(self):
        out = reconcile_auto_exit_with_capture(
            marker('LOCAL_LUA_REPORTED_SIZE_READY_EXIT'),
            strict_audit_passed=True)
        self.assertEqual(out['status'],
                         'READY_MESSAGE_AGREES_WITH_SIZE_ONLY_FILES')
        self.assertTrue(out['strict_structural_capture_audit_passed'])
        self.assertFalse(out['actual_process_exit_cause_verified'])
        self.assertFalse(out['pixel_parity_eligible'])
        self.assertNotIn('/private/', json.dumps(out))
        self.assertNotIn('SECRET', json.dumps(out))

    def test_grace_marker_contradicts_strict_synthetic_capture(self):
        out = reconcile_auto_exit_with_capture(
            marker('LOCAL_LUA_REPORTED_GRACE_LIMIT_EXIT'),
            strict_audit_passed=True)
        self.assertEqual(out['status'],
                         'GRACE_MESSAGE_CONTRADICTS_POST_RUN_FILES')
        self.assertTrue(out['strict_structural_capture_audit_passed'])
        self.assertFalse(out['frame_sync_verified'])

    def test_ready_marker_contradicts_missing_capture_files(self):
        out = reconcile_auto_exit_with_capture(
            marker('LOCAL_LUA_REPORTED_SIZE_READY_EXIT'),
            failure_progress=self.progress())
        self.assertEqual(out['status'],
                         'READY_MESSAGE_CONTRADICTS_POST_RUN_FILES')
        self.assertFalse(out['strict_structural_capture_audit_passed'])

    def test_grace_marker_agrees_with_missing_capture_files_only(self):
        out = reconcile_auto_exit_with_capture(
            marker('LOCAL_LUA_REPORTED_GRACE_LIMIT_EXIT'),
            failure_progress=self.progress())
        self.assertEqual(out['status'],
                         'GRACE_MESSAGE_AGREES_WITH_INCOMPLETE_FILES')
        self.assertFalse(out['original_game_authenticity_verified'])

    def test_grace_on_metadata_complete_but_unaudited_set_is_mismatch(self):
        src = self.progress()
        for row in src['source_frame_coverage']:
            row['lua_present_files'] = row['lua_valid_sized_files'] = 6
            row['cpp_present_files'] = row['cpp_valid_sized_files'] = 3
        src.update({
            'status': 'COMPLETE_FILE_SET_UNVERIFIED',
            'present_files': 54, 'missing_files': 0,
            'invalid_size_files': 0, 'unexpected_entry_count': 0,
            'complete_metadata_frames': 6,
        })
        out = reconcile_auto_exit_with_capture(
            marker('LOCAL_LUA_REPORTED_GRACE_LIMIT_EXIT'),
            failure_progress=src)
        self.assertEqual(out['status'], 'GRACE_MESSAGE_CONTRADICTS_POST_RUN_FILES')
        self.assertFalse(out['strict_structural_capture_audit_passed'])

    def test_bad_or_absent_marker_never_used(self):
        for candidate in (None, 'private trace', {'status': 'DO_NOT_TRUST',
                                                   'marker_observed': True},
                          {'status': 'LOCAL_LUA_REPORTED_SIZE_READY_EXIT',
                           'marker_observed': False}):
            with self.subTest(candidate=candidate):
                out = reconcile_auto_exit_with_capture(
                    candidate, failure_progress=self.progress())
                self.assertIn(out['status'], (
                    'AUTO_EXIT_RECONCILIATION_UNAVAILABLE',
                    'AUTO_EXIT_MARKER_NOT_USABLE'))
                self.assertFalse(out['actual_process_exit_cause_verified'])

    def test_invalid_progress_never_claims_ready_or_grace_agreement(self):
        base = self.progress()
        broken = [
            None, {}, {'status': 'PRIVATE_CAPTURE_PROGRESS_REFUSED'},
            dict(base, present_files=True),
            dict(base, missing_files=99),
            dict(base, complete_metadata_frames=6),
            dict(base, status='COMPLETE_FILE_SET_UNVERIFIED'),
        ]
        broken_frame = self.progress()
        broken_frame['source_frame_coverage'][0]['nominal_frame'] = 901
        broken.append(broken_frame)
        for progress in broken:
            with self.subTest(progress=type(progress).__name__):
                out = reconcile_auto_exit_with_capture(
                    marker('LOCAL_LUA_REPORTED_GRACE_LIMIT_EXIT'),
                    failure_progress=progress)
                self.assertEqual(out['status'], 'AUTO_EXIT_PROGRESS_NOT_USABLE')

    def test_boolean_strict_flag_cannot_be_forged(self):
        out = reconcile_auto_exit_with_capture(
            marker('LOCAL_LUA_REPORTED_SIZE_READY_EXIT'),
            strict_audit_passed='true')
        self.assertEqual(out['status'], 'AUTO_EXIT_RECONCILIATION_UNAVAILABLE')
        self.assertFalse(out['strict_structural_capture_audit_passed'])


class AutoExitRunReconciliationTests(unittest.TestCase):
    def setUp(self):
        fixture = GuardedCaptureTests(
            methodName='test_audit_before_game_uses_separate_process_without_token')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture

    def test_private_success_report_contains_safe_ready_reconciliation(self):
        f = self.fixture
        def proc(args, **kwargs):
            if '-verifyroms' in args:
                return subprocess.CompletedProcess(args, 0)
            kwargs['stdout'].write(b'SECRET dino.zip\n' + READY_LINE + b'\n')
            return f.fake_game(args, kwargs['env']['CPS1_DINO_CAPTURE_SESSION'])
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=f.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=proc):
            out = execute_private_capture(
                f.mame, f.tree, f.roms, f.workspace,
                verify_private_romset_before_capture=True,
                auto_exit_after_capture=True)
        reconciled = out['auto_exit_post_run_reconciliation']
        self.assertEqual(reconciled['status'],
                         'READY_MESSAGE_AGREES_WITH_SIZE_ONLY_FILES')
        self.assertFalse(reconciled['pixel_parity_eligible'])
        saved = json.loads((f.workspace / REPORT_NAME).read_text())
        self.assertEqual(saved['private_capture_completion'][
            'auto_exit_post_run_reconciliation']['status'],
            'READY_MESSAGE_AGREES_WITH_SIZE_ONLY_FILES')
        self.assertNotIn('dino.zip', json.dumps(saved))

    def test_manual_synthetic_success_has_no_auto_exit_reconciliation(self):
        f = self.fixture
        def proc(args, **kwargs):
            return f.fake_game(args, kwargs['env']['CPS1_DINO_CAPTURE_SESSION'])
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=f.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=proc):
            out = execute_private_capture(f.mame, f.tree, f.roms, f.workspace)
        self.assertIsNone(out['auto_exit_post_run_reconciliation'])

    def test_failed_local_process_ready_marker_with_missing_cpp_is_contradiction(self):
        f = self.fixture
        stdout, stderr = io.StringIO(), io.StringIO()
        def proc(args, **kwargs):
            kwargs['stdout'].write(b'PRIVATE /rom/dino.zip\n' + READY_LINE + b'\n')
            capture = f.workspace / CAPTURE_DIR_NAME
            (capture / 'frame-00000900.manifest.json').write_bytes(b'{}')
            return subprocess.CompletedProcess(args, 3)
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=f.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=proc), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            rc = main([
                '--mame', str(f.mame), '--mame-tree', str(f.tree),
                '--rom-dir', str(f.roms), '--workspace', str(f.workspace),
                '--auto-exit-after-capture', '--diagnose-failed-capture'])
        self.assertEqual(rc, 2)
        failure = json.loads(stderr.getvalue())
        self.assertEqual(failure['auto_exit_log_observation']['status'],
                         'LOCAL_LUA_REPORTED_SIZE_READY_EXIT')
        self.assertEqual(failure['auto_exit_post_run_reconciliation']['status'],
                         'READY_MESSAGE_CONTRADICTS_POST_RUN_FILES')
        self.assertFalse((f.workspace / REPORT_NAME).exists())
        self.assertNotIn('/rom/dino.zip', stderr.getvalue())
        self.assertEqual(stdout.getvalue(), '')

    def test_failed_mame_without_marker_has_unusable_diagnostic(self):
        f = self.fixture
        stderr = io.StringIO()
        def proc(args, **kwargs):
            return subprocess.CompletedProcess(args, 5)
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=f.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=proc), contextlib.redirect_stderr(stderr):
            rc = main([
                '--mame', str(f.mame), '--mame-tree', str(f.tree),
                '--rom-dir', str(f.roms), '--workspace', str(f.workspace),
                '--auto-exit-after-capture', '--diagnose-failed-capture'])
        self.assertEqual(rc, 2)
        failure = json.loads(stderr.getvalue())
        self.assertEqual(failure['auto_exit_post_run_reconciliation']['status'],
                         'AUTO_EXIT_MARKER_NOT_USABLE')


if __name__ == '__main__':
    unittest.main()
