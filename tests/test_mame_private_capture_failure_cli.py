"""ROM-free CLI integration regressions for local failed-capture summaries."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_private_dino_session import (
    main, CAPTURE_DIR_NAME, REPORT_NAME, VERIFY_LOG_NAME,
)


def _synthetic_mame_identity(*args, **kwargs):
    return {
        'driver': 'dino',
        'listxml_validated': True,
        'compiled_instrumented_latch_v2_format': True,
        'compiled_session_label_probe_marker': True,
        'compiled_session_environment_probe_marker': True,
        'linked_dino_executable_probe_markers': True,
    }


class CaptureFailureCliTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.tree = self.root / 'mame0289'
        self.mame = self.tree / 'dino'
        (self.tree / 'src/mame/capcom').mkdir(parents=True)
        (self.tree / 'src/mame/capcom/cps1_v.cpp').write_text('synthetic only')
        self.mame.write_bytes(b'not an emulator')
        self.mame.chmod(0o755)
        self.roms = self.root / 'user-owned-roms'
        self.roms.mkdir()
        (self.roms / 'dino.zip').write_bytes(b'SYNTHETIC-ONLY-CONTENTS')
        self.workspace = self.root / 'private'
        self.workspace.mkdir(mode=0o700)

    def args(self, *extra):
        return ['--mame', str(self.mame), '--mame-tree', str(self.tree),
                '--rom-dir', str(self.roms), '--workspace', str(self.workspace),
                *extra]

    def run_cli(self, extra, callback):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=_synthetic_mame_identity), \
             patch('tools.mame_private_dino_session.subprocess.run',
                   side_effect=callback) as run, \
             contextlib.redirect_stdout(stdout), \
             contextlib.redirect_stderr(stderr):
            code = main(self.args(*extra))
        return code, stdout.getvalue(), stderr.getvalue(), run

    def test_guarded_rom_audit_failure_returns_safe_absent_capture_summary(self):
        def callback(args, **kwargs):
            kwargs['stdout'].write(b'PRIVATE GAME FILE /secret/user/dino.zip')
            return subprocess.CompletedProcess(args, 5)
        code, stdout, stderr, run = self.run_cli(
            ['--verify-private-romset-before-capture',
             '--diagnose-failed-capture'], callback)
        self.assertEqual(code, 2)
        self.assertEqual(stdout, '')
        self.assertEqual(run.call_count, 1)
        out = json.loads(stderr)
        self.assertEqual(out['reason_code'], 'PRIVATE_MAME_ROMSET_AUDIT_FAILED')
        self.assertEqual(out['capture_progress']['status'],
                         'NO_PRIVATE_CAPTURE_DIRECTORY')
        self.assertEqual(out['capture_progress']['present_files'], 0)
        self.assertFalse((self.workspace / CAPTURE_DIR_NAME).exists())
        self.assertFalse((self.workspace / REPORT_NAME).exists())
        self.assertNotIn('/secret/user/', stderr)
        self.assertNotIn(str(self.workspace), stderr)
        self.assertIn(b'/secret/user/',
                      (self.workspace / VERIFY_LOG_NAME).read_bytes())

    def test_failed_game_process_reports_partial_lua_cpp_coverage(self):
        executed = []
        def callback(args, **kwargs):
            executed.append(args)
            if '-verifyroms' in args:
                return subprocess.CompletedProcess(args, 0)
            capture = self.workspace / CAPTURE_DIR_NAME
            (capture / 'frame-00000900.manifest.json').write_bytes(b'{}')
            (capture / 'frame-00000900.obj-latch-count.txt').write_bytes(
                b'FAKE_SYNTHETIC_SIDECAR')
            return subprocess.CompletedProcess(args, 3)
        code, stdout, stderr, run = self.run_cli(
            ['--verify-private-romset-before-capture',
             '--diagnose-failed-capture'], callback)
        self.assertEqual(code, 2)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(stdout, '')
        out = json.loads(stderr)
        self.assertEqual(out['reason_code'], 'LOCAL_MAME_PROCESS_FAILED')
        progress = out['capture_progress']
        self.assertEqual(progress['status'], 'INCOMPLETE_PRIVATE_CAPTURE_FILE_SET')
        self.assertEqual(progress['present_files'], 2)
        self.assertEqual(progress['missing_files'], 52)
        self.assertEqual(progress['source_frame_coverage'][0]['lua_present_files'], 1)
        self.assertEqual(progress['source_frame_coverage'][0]['cpp_present_files'], 1)
        self.assertFalse(progress['capture_contents_read'])
        self.assertFalse(progress['gameplay_verified'])
        self.assertFalse((self.workspace / REPORT_NAME).exists())
        self.assertNotIn(str(self.roms), stderr)
        self.assertNotIn('dino.zip', stderr)

    def test_non_opted_game_failure_keeps_legacy_single_reason_without_progress(self):
        def callback(args, **kwargs):
            return subprocess.CompletedProcess(args, 7)
        code, stdout, stderr, run = self.run_cli([], callback)
        self.assertEqual(code, 2)
        self.assertEqual(run.call_count, 1)
        out = json.loads(stderr)
        self.assertEqual(out['reason_code'], 'LOCAL_MAME_PROCESS_FAILED')
        self.assertNotIn('capture_progress', out)
        self.assertEqual(stdout, '')

    def test_readiness_and_verify_only_reject_failure_progress_flag(self):
        for mode in ('--preflight-only', '--verify-build-only',
                     '--check-launch-readiness', '--verify-private-romset-only'):
            with self.subTest(mode=mode):
                code, stdout, stderr, run = self.run_cli(
                    [mode, '--diagnose-failed-capture'],
                    lambda args, **kwargs: subprocess.CompletedProcess(args, 0))
                self.assertEqual(code, 2)
                self.assertEqual(run.call_count, 0)
                out = json.loads(stderr)
                self.assertEqual(out['reason_code'], 'INVALID_LAUNCH_ARGUMENTS')
                self.assertEqual(out['capture_progress']['status'],
                                 'NO_PRIVATE_CAPTURE_DIRECTORY')
                self.assertEqual(stdout, '')
        self.assertEqual(list(self.workspace.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
