"""Guarded MAME ROM audit -> diagnostic capture, using synthetic data only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_private_dino_session import (
    CAPTURE_DIR_NAME, LOG_NAME, REPORT_NAME, VERIFY_LOG_NAME,
    execute_private_capture, preflight,
)
from tools.mame_obj_latch_evidence import obj_fnv1a64
from test_mame_obj_cli_end_to_end import make_capture


class GuardedCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.tree = self.root / 'source'
        self.mame = self.tree / 'dino'
        (self.tree / 'src/mame/capcom').mkdir(parents=True)
        (self.tree / 'src/mame/capcom/cps1_v.cpp').write_text('synthetic')
        self.mame.write_bytes(b'fake executable')
        self.mame.chmod(0o755)
        self.roms = self.root / 'roms'
        self.roms.mkdir()
        (self.roms / 'dino.zip').write_bytes(b'not-a-real-rom')
        self.workspace = self.root / 'private-workspace'
        self.workspace.mkdir(mode=0o700)

    @staticmethod
    def fake_build(*args, **kwargs):
        return {
            'driver': 'dino',
            'listxml_validated': True,
            'compiled_instrumented_latch_v2_format': True,
            'compiled_session_label_probe_marker': True,
            'compiled_session_environment_probe_marker': True,
            'linked_dino_executable_probe_markers': True,
        }

    def fake_game(self, args, session):
        capture = self.workspace / CAPTURE_DIR_NAME
        make_capture(capture)
        for i in range(6):
            stem = f'frame-{900 + i * 2:08d}'
            buffer = (capture / (stem + '.buffered-obj-be.bin')).read_bytes()
            manifest = capture / (stem + '.manifest.json')
            info = json.loads(manifest.read_text())
            info['capture_session'] = session
            manifest.write_text(json.dumps(info))
            (capture / (stem + '.obj-latch-count.txt')).write_text(
                f'CPS1_DINO_LATCH_V2 {20+i*2} {obj_fnv1a64(buffer)}\n'
                f'CPS1_DINO_SESSION {session}\n')
        return subprocess.CompletedProcess(args, 0)

    def test_audit_before_game_uses_separate_process_without_token(self):
        seen = []
        def run(args, **kwargs):
            session = kwargs['env'].get('CPS1_DINO_CAPTURE_SESSION')
            seen.append((list(args), session))
            if '-verifyroms' in args:
                kwargs['stdout'].write(b'FAKE_PRIVATE_MAME_AUDIT')
                return subprocess.CompletedProcess(args, 0)
            return self.fake_game(args, session)
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=run) as process:
            out = execute_private_capture(
                self.mame, self.tree, self.roms, self.workspace,
                timeout_seconds=120, verify_private_romset_before_capture=True)
        self.assertEqual(process.call_count, 2)
        self.assertEqual(seen[0][0][1:3], ['dino', '-verifyroms'])
        self.assertIsNone(seen[0][1])
        self.assertIn('-noreadconfig', seen[0][0])
        self.assertIn('-autoboot_script', seen[1][0])
        self.assertIn('-noreadconfig', seen[1][0])
        self.assertEqual(len(seen[1][1]), 32)
        self.assertTrue(out['local_mame_verifyroms_exit_zero_before_capture'])
        self.assertTrue(out['private_rom_entry_metadata_stable_during_capture'])
        self.assertTrue(out['private_rom_content_sha256_stable_during_capture'])
        self.assertTrue(out['private_rom_bytes_read_by_python'])
        self.assertFalse(out['original_game_authenticity_verified'])
        self.assertFalse(out['frame_sync_verified'])
        private_report = json.loads((self.workspace / REPORT_NAME).read_text())
        self.assertTrue(private_report['private_capture_completion'][
            'local_mame_verifyroms_exit_zero_before_capture'])
        self.assertTrue(private_report['private_capture_completion'][
            'private_rom_content_sha256_stable_during_capture'])
        self.assertNotIn('FAKE_PRIVATE_MAME_AUDIT', json.dumps(private_report))
        self.assertEqual((self.workspace / VERIFY_LOG_NAME).read_bytes(),
                         b'FAKE_PRIVATE_MAME_AUDIT')
        self.assertTrue((self.workspace / LOG_NAME).is_file())

    def test_rom_mutation_during_verification_never_starts_game(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            (self.roms / 'dino.zip').write_bytes(b'SYNTHETIC_CHANGED_DURING_AUDIT')
            return subprocess.CompletedProcess(args, 0)
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=run):
            with self.assertRaisesRegex(ValueError, 'metadata changed'):
                execute_private_capture(
                    self.mame, self.tree, self.roms, self.workspace,
                    verify_private_romset_before_capture=True)
        self.assertEqual(len(calls), 1)
        self.assertIn('-verifyroms', calls[0])
        self.assertFalse((self.workspace / CAPTURE_DIR_NAME).exists())
        self.assertFalse((self.workspace / REPORT_NAME).exists())

    def test_rom_mutation_during_game_never_publishes_final_report(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            if '-verifyroms' in args:
                return subprocess.CompletedProcess(args, 0)
            result = self.fake_game(
                args, kwargs['env']['CPS1_DINO_CAPTURE_SESSION'])
            (self.roms / 'dino.zip').write_bytes(b'SYNTHETIC_CHANGED_DURING_GAME')
            return result
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=run):
            with self.assertRaisesRegex(ValueError, 'metadata changed'):
                execute_private_capture(
                    self.mame, self.tree, self.roms, self.workspace,
                    verify_private_romset_before_capture=True)
        self.assertEqual(len(calls), 2)
        self.assertFalse((self.workspace / REPORT_NAME).exists())
        self.assertTrue((self.workspace / CAPTURE_DIR_NAME).exists())

    def test_nonzero_audit_never_starts_game(self):
        seen = []
        def run(args, **kw):
            seen.append(args)
            kw['stdout'].write(b'PRIVATE_ROM_PATH')
            return subprocess.CompletedProcess(args, 5)
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=run):
            with self.assertRaisesRegex(ValueError, 'ROM verification failed'):
                execute_private_capture(
                    self.mame, self.tree, self.roms, self.workspace,
                    verify_private_romset_before_capture=True)
        self.assertEqual(len(seen), 1)
        self.assertIn('-verifyroms', seen[0])
        self.assertFalse((self.workspace / CAPTURE_DIR_NAME).exists())
        self.assertFalse((self.workspace / REPORT_NAME).exists())
        self.assertFalse((self.workspace / LOG_NAME).exists())
        self.assertEqual((self.workspace / VERIFY_LOG_NAME).read_bytes(),
                         b'PRIVATE_ROM_PATH')

    def test_timeout_blocks_capture_and_keeps_private_log(self):
        def timeout(args, **kw):
            raise subprocess.TimeoutExpired(args, kw['timeout'])
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=timeout) as process:
            with self.assertRaisesRegex(ValueError, 'verification timed out'):
                execute_private_capture(
                    self.mame, self.tree, self.roms, self.workspace,
                    verify_private_romset_before_capture=True)
            process.assert_called_once()
        self.assertTrue((self.workspace / VERIFY_LOG_NAME).is_file())
        self.assertFalse((self.workspace / CAPTURE_DIR_NAME).exists())

    def test_existing_audit_log_cannot_be_reused_as_proof(self):
        log = self.workspace / VERIFY_LOG_NAME
        log.write_bytes(b'PREVIOUS_AUDIT')
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'log already exists'):
                execute_private_capture(
                    self.mame, self.tree, self.roms, self.workspace,
                    verify_private_romset_before_capture=True)
            run.assert_not_called()
        self.assertEqual(log.read_bytes(), b'PREVIOUS_AUDIT')
        self.assertFalse((self.workspace / CAPTURE_DIR_NAME).exists())

    def test_guard_requires_set_and_refuses_mixed_modes(self):
        (self.roms / 'dino.zip').unlink()
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'No private dino'):
                execute_private_capture(
                    self.mame, self.tree, self.roms, self.workspace,
                    verify_private_romset_before_capture=True)
            run.assert_not_called()
        self.assertEqual(list(self.workspace.iterdir()), [])
        for config in (
            {'verify_private_romset_before_capture': 'true'},
            {'verify_private_romset_before_capture': True,
             'verify_private_romset_only': True},
            {'verify_private_romset_before_capture': True,
             'preflight_only': True},
            {'verify_private_romset_before_capture': True,
             'verify_build_only': True},
            {'verify_private_romset_before_capture': True,
             'check_launch_readiness': True},
        ):
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, 'boolean|preflight mode'):
                    execute_private_capture(
                        self.mame, self.tree, self.roms, self.workspace, **config)

    def test_unguarded_capture_has_no_false_rom_audit_provenance(self):
        def run(args, **kwargs):
            return self.fake_game(
                args, kwargs['env']['CPS1_DINO_CAPTURE_SESSION'])
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.fake_build), patch(
                   'tools.mame_private_dino_session.subprocess.run',
                   side_effect=run):
            out = execute_private_capture(
                self.mame, self.tree, self.roms, self.workspace)
        self.assertFalse(out['local_mame_verifyroms_exit_zero_before_capture'])
        self.assertFalse(out['private_rom_entry_metadata_stable_during_capture'])
        self.assertFalse(out['private_rom_content_sha256_stable_during_capture'])
        self.assertFalse(out['private_rom_bytes_read_by_python'])
        self.assertFalse(json.loads((self.workspace / REPORT_NAME).read_text())[
            'private_capture_completion']['local_mame_verifyroms_exit_zero_before_capture'])
        self.assertFalse((self.workspace / VERIFY_LOG_NAME).exists())


if __name__ == '__main__':
    unittest.main()
