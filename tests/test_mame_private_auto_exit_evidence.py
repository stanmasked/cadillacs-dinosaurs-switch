"""Synthetic private MAME auto-exit log marker evidence regressions."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_private_auto_exit_evidence import (
    private_mame_auto_exit_log_observation, READY_LINE, GRACE_LINE,
    LOG_NAME, MAX_LOG_SCAN_BYTES,
)
from tools.mame_private_dino_session import (
    REPORT_NAME, execute_private_capture, main,
)
from test_mame_private_guarded_capture import GuardedCaptureTests


class LocalAutoExitLogEvidenceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.log = self.root / LOG_NAME

    def test_ready_marker_does_not_disclose_any_log_bytes(self):
        self.log.write_bytes(b'ROM SECRET /private/owned/dino.zip\n' + READY_LINE + b'\n')
        result = private_mame_auto_exit_log_observation(self.root)
        self.assertEqual(result['status'], 'LOCAL_LUA_REPORTED_SIZE_READY_EXIT')
        self.assertTrue(result['marker_observed'])
        self.assertFalse(result['frame_sync_verified'])
        self.assertFalse(result['pixel_parity_eligible'])
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('dino.zip', json.dumps(result))

    def test_grace_marker_distinct_from_ready(self):
        self.log.write_bytes(GRACE_LINE + b'\n')
        out = private_mame_auto_exit_log_observation(self.root)
        self.assertEqual(out['status'], 'LOCAL_LUA_REPORTED_GRACE_LIMIT_EXIT')
        self.assertTrue(out['observed_message_not_independent_proof'])

    def test_no_log_is_fixed_refusal(self):
        self.assertEqual(private_mame_auto_exit_log_observation(self.root)['status'],
                         'LOCAL_MAME_AUTO_EXIT_LOG_REFUSED')

    def test_inexact_lines_and_missing_markers_not_detected(self):
        self.log.write_bytes(b'foo ' + READY_LINE + b'\n' + GRACE_LINE + b' bar\n')
        result = private_mame_auto_exit_log_observation(self.root)
        self.assertEqual(result['status'], 'LOCAL_MAME_AUTO_EXIT_MARKER_NOT_OBSERVED')

    def test_repeated_or_conflicting_markers_are_ambiguous(self):
        for data in (READY_LINE + b'\n' + READY_LINE + b'\n',
                     READY_LINE + b'\n' + GRACE_LINE + b'\n',
                     GRACE_LINE + b'\n' + GRACE_LINE + b'\n'):
            with self.subTest(raw=data):
                self.log.write_bytes(data)
                result = private_mame_auto_exit_log_observation(self.root)
                self.assertEqual(result['status'],
                                 'LOCAL_MAME_AUTO_EXIT_MARKERS_AMBIGUOUS')
                self.assertFalse(result['marker_observed'])

    def test_symlink_and_hardlink_refused_without_content_read(self):
        secret = self.root / 'actual-secret-data'
        secret.write_bytes(READY_LINE)
        self.log.symlink_to(secret)
        self.assertEqual(private_mame_auto_exit_log_observation(self.root)['status'],
                         'LOCAL_MAME_AUTO_EXIT_LOG_REFUSED')
        self.log.unlink()
        os.link(secret, self.log)
        self.assertEqual(private_mame_auto_exit_log_observation(self.root)['status'],
                         'LOCAL_MAME_AUTO_EXIT_LOG_REFUSED')

    def test_oversized_log_is_refused_before_open(self):
        with self.log.open('wb') as output:
            output.truncate(MAX_LOG_SCAN_BYTES + 1)
        with patch('tools.mame_private_auto_exit_evidence.os.open',
                   side_effect=AssertionError('should not open log')) as opened:
            result = private_mame_auto_exit_log_observation(self.root)
            opened.assert_not_called()
        self.assertEqual(result['status'], 'LOCAL_MAME_AUTO_EXIT_LOG_REFUSED')

    def test_invalid_or_nonexistent_workspace_is_safe(self):
        for workspace in (None, object(), '/private/nonexistent/owned-ROM'):
            with self.subTest(category=type(workspace).__name__):
                out = private_mame_auto_exit_log_observation(workspace)
                self.assertEqual(out['status'], 'LOCAL_MAME_AUTO_EXIT_LOG_REFUSED')
                self.assertNotIn('owned-ROM', json.dumps(out))

    def test_production_lua_contains_exact_fixed_exit_line_labels(self):
        source = (Path(__file__).resolve().parents[1] /
                  'tools/mame_cps1_capture.lua').read_text(encoding='utf-8')
        self.assertIn("print('CPS1_DINO_AUTO_EXIT_V1_READY_54_SIZE_ONLY')", source)
        self.assertIn("print('CPS1_DINO_AUTO_EXIT_V1_GRACE_INCOMPLETE_SIZE_ONLY')", source)
        self.assertEqual(source.count(READY_LINE.decode()), 1)
        self.assertEqual(source.count(GRACE_LINE.decode()), 1)


class AutoExitMarkerIntegrationTests(unittest.TestCase):
    def setUp(self):
        fixture = GuardedCaptureTests(
            methodName='test_audit_before_game_uses_separate_process_without_token')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture

    def test_successful_synthetic_capture_reports_log_observation_only(self):
        f = self.fixture
        def callback(args, **kwargs):
            if '-verifyroms' in args:
                return subprocess.CompletedProcess(args, 0)
            kwargs['stdout'].write(b'PRIVATE MAME ROM /private/original/dino.zip\n')
            kwargs['stdout'].write(READY_LINE + b'\n')
            return f.fake_game(args, kwargs['env']['CPS1_DINO_CAPTURE_SESSION'])
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=f.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=callback):
            out = execute_private_capture(
                f.mame, f.tree, f.roms, f.workspace,
                verify_private_romset_before_capture=True,
                auto_exit_after_capture=True)
        self.assertEqual(out['auto_exit_log_observation']['status'],
                         'LOCAL_LUA_REPORTED_SIZE_READY_EXIT')
        report = json.loads((f.workspace / REPORT_NAME).read_text())
        self.assertEqual(report['private_capture_completion'][
            'auto_exit_log_observation']['status'],
            'LOCAL_LUA_REPORTED_SIZE_READY_EXIT')
        self.assertNotIn('/private/original/dino.zip', json.dumps(report))
        self.assertFalse(out['frame_sync_verified'])

    def test_default_manual_session_does_not_read_private_log(self):
        f = self.fixture
        def callback(args, **kwargs):
            return f.fake_game(args, kwargs['env']['CPS1_DINO_CAPTURE_SESSION'])
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=f.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=callback), patch(
                   'tools.mame_private_dino_session.private_mame_auto_exit_log_observation',
                   side_effect=AssertionError('manual mode must not read log')) as observer:
            out = execute_private_capture(f.mame, f.tree, f.roms, f.workspace)
        observer.assert_not_called()
        self.assertIsNone(out['auto_exit_log_observation'])

    def test_failed_game_cli_output_is_fixed_grace_marker_and_safe_counts(self):
        f = self.fixture
        stdout, stderr = io.StringIO(), io.StringIO()
        def callback(args, **kwargs):
            kwargs['stdout'].write(GRACE_LINE + b'\n')
            kwargs['stdout'].write(b'SECRET /private/dino.zip\n')
            return subprocess.CompletedProcess(args, 2)
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=f.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=callback), \
             contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main([
                '--mame', str(f.mame), '--mame-tree', str(f.tree),
                '--rom-dir', str(f.roms), '--workspace', str(f.workspace),
                '--auto-exit-after-capture', '--diagnose-failed-capture'])
        self.assertEqual(status, 2)
        self.assertEqual(stdout.getvalue(), '')
        response = json.loads(stderr.getvalue())
        self.assertEqual(response['reason_code'], 'LOCAL_MAME_PROCESS_FAILED')
        self.assertEqual(response['auto_exit_log_observation']['status'],
                         'LOCAL_LUA_REPORTED_GRACE_LIMIT_EXIT')
        self.assertFalse((f.workspace / REPORT_NAME).exists())
        self.assertNotIn('/private/dino.zip', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
