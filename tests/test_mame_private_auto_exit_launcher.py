"""ROM-free CLI and subprocess environment tests for opt-in Lua auto-exit."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_private_dino_session import (
    CAPTURE_DIR_NAME, REPORT_NAME, execute_private_capture, main,
)
from test_mame_private_guarded_capture import GuardedCaptureTests


# Reuse synthetic process/report helpers without inheriting their tests.
class MameAutoExitLauncherTests(unittest.TestCase):
    def setUp(self):
        self.fixtures = GuardedCaptureTests(methodName='test_audit_before_game_uses_separate_process_without_token')
        self.fixtures.setUp()
        self.addCleanup(self.fixtures.doCleanups)
        self.root = self.fixtures.root
        self.tree = self.fixtures.tree
        self.mame = self.fixtures.mame
        self.roms = self.fixtures.roms
        self.workspace = self.fixtures.workspace

    def test_guarded_auto_exit_env_only_on_game_not_verification(self):
        seen = []
        def fake_run(args, **kwargs):
            seen.append((list(args), dict(kwargs['env'])))
            if '-verifyroms' in args:
                return subprocess.CompletedProcess(args, 0)
            return self.fixtures.fake_game(
                args, kwargs['env']['CPS1_DINO_CAPTURE_SESSION'])

        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fixtures.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=fake_run) as proc:
            out = execute_private_capture(
                self.mame, self.tree, self.roms, self.workspace,
                verify_private_romset_before_capture=True,
                auto_exit_after_capture=True)
        self.assertEqual(proc.call_count, 2)
        self.assertNotIn('CPS1_DINO_AUTO_EXIT_AFTER_CAPTURE', seen[0][1])
        self.assertNotIn('CPS1_DINO_CAPTURE_SESSION', seen[0][1])
        self.assertEqual(seen[1][1]['CPS1_DINO_AUTO_EXIT_AFTER_CAPTURE'], '1')
        self.assertEqual(len(seen[1][1]['CPS1_DINO_CAPTURE_SESSION']), 32)
        self.assertTrue(out['auto_exit_after_capture_requested'])
        self.assertTrue(json.loads((self.workspace / REPORT_NAME).read_text())[
            'private_capture_completion']['auto_exit_after_capture_requested'])
        self.assertFalse(out['frame_sync_verified'])

    def test_inherited_auto_exit_never_changes_default_manual_capture(self):
        def fake_run(args, **kwargs):
            self.assertNotIn('CPS1_DINO_AUTO_EXIT_AFTER_CAPTURE', kwargs['env'])
            return self.fixtures.fake_game(
                args, kwargs['env']['CPS1_DINO_CAPTURE_SESSION'])
        with patch.dict(os.environ, {'CPS1_DINO_AUTO_EXIT_AFTER_CAPTURE': '1'}), \
             patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fixtures.fake_build), \
             patch('tools.mame_private_dino_session.subprocess.run',
                   side_effect=fake_run):
            out = execute_private_capture(
                self.mame, self.tree, self.roms, self.workspace)
        self.assertFalse(out['auto_exit_after_capture_requested'])
        self.assertFalse(json.loads((self.workspace / REPORT_NAME).read_text())[
            'private_capture_completion']['auto_exit_after_capture_requested'])

    def test_auto_exit_boolean_and_rom_free_modes_are_rejected_without_running(self):
        options = (
            {'auto_exit_after_capture': 'yes'},
            {'auto_exit_after_capture': True, 'preflight_only': True},
            {'auto_exit_after_capture': True, 'verify_build_only': True},
            {'auto_exit_after_capture': True, 'check_launch_readiness': True},
            {'auto_exit_after_capture': True, 'verify_private_romset_only': True},
        )
        with patch('tools.mame_private_dino_session.subprocess.run') as run:
            for flags in options:
                with self.subTest(flags=flags):
                    with self.assertRaisesRegex(ValueError, 'boolean|only available'):
                        execute_private_capture(
                            self.mame, self.tree, self.roms, self.workspace, **flags)
            run.assert_not_called()
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_cli_flag_sets_game_env_and_returns_boolean_only(self):
        def fake_run(args, **kwargs):
            self.assertEqual(kwargs['env']['CPS1_DINO_AUTO_EXIT_AFTER_CAPTURE'], '1')
            return self.fixtures.fake_game(
                args, kwargs['env']['CPS1_DINO_CAPTURE_SESSION'])
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fixtures.fake_build), \
             patch('tools.mame_private_dino_session.subprocess.run',
                   side_effect=fake_run), \
             contextlib.redirect_stdout(stdout), \
             contextlib.redirect_stderr(stderr):
            code = main([
                '--mame', str(self.mame),
                '--mame-tree', str(self.tree),
                '--rom-dir', str(self.roms),
                '--workspace', str(self.workspace),
                '--auto-exit-after-capture',
            ])
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), '')
        obj = json.loads(stdout.getvalue())
        self.assertTrue(obj['auto_exit_after_capture_requested'])
        self.assertNotIn(str(self.roms), stdout.getvalue())
        self.assertNotIn('dino.zip', stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
