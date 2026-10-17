"""Synthetic ROM-free tests for locally isolated MAME dino capture sessions."""
from pathlib import Path
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_obj_latch_evidence import obj_fnv1a64
from tools.mame_private_dino_session import (
    CAPTURE_DIR_NAME, LOG_NAME, REPORT_NAME,
    PROJECT_ROOT, execute_private_capture, main, preflight,
)
from test_mame_obj_cli_end_to_end import make_capture


class PrivateDinoSessionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.build = self.root / 'source'
        self.mame = self.build / 'dino'
        (self.build / 'src' / 'mame' / 'capcom').mkdir(parents=True)
        (self.build / 'src/mame/capcom/cps1_v.cpp').write_text('private')
        self.mame.write_bytes(b'fake executable marker')
        self.mame.chmod(0o755)
        self.roms = self.root / 'privately-owned-roms'
        self.roms.mkdir()
        self.workspace = self.root / 'private-workspace'
        self.workspace.mkdir(mode=0o700)

    @staticmethod
    def compiled_dino_identity(*args, **kwargs):
        return {
            'driver': 'dino',
            'compiled_instrumented_latch_v2_format': True,
            'listxml_validated': True,
        }

    def run_local(self, *, process=None):
        with patch('tools.mame_private_dino_session.inspect_binary',
                   side_effect=self.compiled_dino_identity), \
             patch('tools.mame_private_dino_session.subprocess.run',
                   side_effect=process) as runner:
            result = execute_private_capture(
                self.mame, self.build, self.roms, self.workspace,
                timeout_seconds=120)
        return result, runner

    def populate_fake_private_capture(self, args, *, version=2):
        root = self.workspace / CAPTURE_DIR_NAME
        make_capture(root)
        for i in range(6):
            stem = f'frame-{900 + i*2:08d}'
            obj = (root / f'{stem}.buffered-obj-be.bin').read_bytes()
            line = (f'CPS1_DINO_LATCH_V2 {20+i*2} {obj_fnv1a64(obj)}\n'
                    if version == 2 else f'CPS1_DINO_LATCH_V1 {20+i*2}\n')
            (root / f'{stem}.obj-latch-count.txt').write_text(line)
        return subprocess.CompletedProcess(args, 0)

    def test_preflight_only_does_not_execute_or_write_or_read_rom_data(self):
        with patch('tools.mame_private_dino_session.inspect_binary') as build, \
             patch('tools.mame_private_dino_session.subprocess.run') as run:
            result = execute_private_capture(
                self.mame, self.build, self.roms, self.workspace,
                preflight_only=True)
        self.assertEqual(result['status'], 'FILESYSTEM_PREFLIGHT_ONLY')
        self.assertFalse(result['game_executed'])
        self.assertEqual(list(self.workspace.iterdir()), [])
        build.assert_not_called()
        run.assert_not_called()

    def test_workspace_inside_source_or_rom_or_project_is_rejected(self):
        for path in (self.build, self.roms, PROJECT_ROOT,
                     self.build / 'subfolder'):
            with self.subTest(type=str(path)):
                if path.name == 'subfolder':
                    path.mkdir()
                with self.assertRaisesRegex(ValueError, 'separate'):
                    preflight(self.mame, self.build, self.roms, path)

    def test_rom_directory_inside_public_project_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'outside the project'):
            preflight(self.mame, self.build, PROJECT_ROOT, self.workspace)

    def test_existing_capture_report_or_log_never_overwritten(self):
        for name in (CAPTURE_DIR_NAME, REPORT_NAME, LOG_NAME):
            path = self.workspace / name
            if name == CAPTURE_DIR_NAME:
                path.mkdir()
            else:
                path.write_bytes(b'PRIVATE_DO_NOT_OVERWRITE')
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'already contains'):
                    preflight(self.mame, self.build, self.roms, self.workspace)
            if path.is_dir():
                path.rmdir()
            else:
                self.assertEqual(path.read_bytes(), b'PRIVATE_DO_NOT_OVERWRITE')
                path.unlink()

    def test_workspace_must_not_expose_local_game_data_to_other_users(self):
        if os.name != 'posix':
            self.skipTest('POSIX permissions required')
        self.workspace.chmod(0o755)
        with self.assertRaisesRegex(ValueError, '0700-style'):
            preflight(self.mame, self.build, self.roms, self.workspace)
        self.workspace.chmod(0o700)

    def test_executable_symlink_is_rejected_before_resolving(self):
        link=self.root / 'mame-symlink'
        link.symlink_to(self.mame)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            preflight(link, self.build, self.roms, self.workspace)

    def test_missing_mame_source_rom_or_workspace_refused(self):
        params = [
            (self.root / 'no-mame', self.build, self.roms, self.workspace),
            (self.mame, self.root / 'missing-source', self.roms, self.workspace),
            (self.mame, self.build, self.root / 'no-rom', self.workspace),
            (self.mame, self.build, self.roms, self.root / 'no-workspace'),
        ]
        for values in params:
            with self.subTest(args=values[0].name):
                with self.assertRaises(ValueError):
                    preflight(*values)

    def test_timeout_bounds_and_boolean_rejected_before_launch(self):
        for timeout in (True, 0, 29, 3601, '120'):
            with self.subTest(timeout=timeout):
                with self.assertRaisesRegex(ValueError, 'timeout'):
                    execute_private_capture(
                        self.mame, self.build, self.roms,
                        self.workspace, timeout_seconds=timeout)
        with self.assertRaisesRegex(ValueError, 'boolean'):
            execute_private_capture(
                self.mame, self.build, self.roms,
                self.workspace, preflight_only='yes')

    def test_local_fake_game_runs_real_multiframe_integrity_cli(self):
        def fake_mame(argv, **kwargs):
            self.assertEqual(argv[0], str(self.mame.resolve()))
            self.assertEqual(argv[1:3], ['dino', '-rompath'])
            self.assertEqual(argv[3], str(self.roms.resolve()))
            self.assertEqual(argv[4], '-autoboot_script')
            self.assertTrue(argv[5].endswith('tools/mame_cps1_capture.lua'))
            self.assertEqual(kwargs['cwd'], self.workspace.resolve())
            self.assertEqual(kwargs['timeout'], 120)
            self.assertIs(kwargs['stderr'], subprocess.STDOUT)
            self.assertTrue(kwargs['stdout'].writable())
            return self.populate_fake_private_capture(argv)

        report, runner = self.run_local(process=fake_mame)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(report['status'], 'PRIVATE_CAPTURE_INTEGRITY_VERIFIED_ONLY')
        self.assertEqual(report['nominal_frame_count'], 6)
        self.assertEqual(report['crc32_lua_components_checked'], 30)
        self.assertEqual(report['bound_cpp_obj_samples'], 6)
        self.assertTrue(report['game_executed'])
        self.assertFalse(report['original_game_authenticity_verified'])
        self.assertFalse(report['obj_latch_age_verified'])
        self.assertFalse(report['pixel_parity_eligible'])
        activity = report['reference_activity']
        self.assertEqual(activity['status'], 'REFERENCE_BYTES_CHANGED_UNVERIFIED')
        self.assertEqual(activity['changed_reference_intervals'], 5)
        self.assertTrue(activity['all_frames_single_color'])
        self.assertFalse(activity['active_gameplay_verified'])
        self.assertFalse(activity['frame_sync_verified'])
        intervals = report['multistream_interval_evidence']
        self.assertEqual(intervals['status'], 'LOW_INFORMATION_FOR_MULTISTREAM_STUDY')
        self.assertEqual(intervals['nominal_frame_labels'], [900,902,904,906,908,910])
        self.assertEqual(intervals['rgb_change_intervals'], 5)
        self.assertEqual(intervals['obj_change_intervals'], 0)
        self.assertEqual(intervals['latch_increment_intervals'], 5)
        self.assertEqual(len(intervals['intervals']), 5)
        self.assertIn('NO_OBJ_CHANGES_OBSERVED', intervals['observational_cautions'])
        self.assertFalse(intervals['active_gameplay_verified'])
        self.assertFalse(intervals['frame_sync_verified'])
        self.assertTrue((self.workspace / LOG_NAME).is_file())
        if os.name == 'posix':
            self.assertEqual((self.workspace / LOG_NAME).stat().st_mode & 0o777, 0o600)
            self.assertEqual((self.workspace / REPORT_NAME).stat().st_mode & 0o777, 0o600)
        raw = json.loads((self.workspace / REPORT_NAME).read_text())
        self.assertEqual(
            raw['obj_latch_count_evidence']['obj_byte_fingerprint_verified_count'], 6)
        self.assertFalse(raw['frame_sync_verified'])
        self.assertEqual(
            raw['private_capture_completion']['status'],
            'PRIVATE_CAPTURE_INTEGRITY_VERIFIED_ONLY')
        self.assertTrue(
            raw['private_capture_completion']['full_check_sequence_completed'])
        self.assertEqual(
            raw['private_capture_source_stability']['source_files_checked'], 54)
        self.assertTrue(
            raw['private_capture_source_stability']['source_files_unchanged_during_audit'])
        self.assertNotIn('source_file_sha256', raw['private_capture_source_stability'])
        self.assertFalse(
            raw['private_capture_completion']['pixel_parity_eligible'])
        self.assertEqual(
            raw['reference_activity']['changed_reference_intervals'], 5)
        self.assertEqual(
            raw['multistream_interval_evidence']['obj_change_intervals'], 0)
        self.assertFalse(any(p.name.startswith('.dino-audit-pending-')
                             for p in self.workspace.iterdir()))

    def test_no_file_output_after_failed_binary_identity_check(self):
        with patch('tools.mame_private_dino_session.inspect_binary',
                   return_value={'driver': 'dino'}):
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                execute_private_capture(
                    self.mame, self.build, self.roms, self.workspace)
        self.assertEqual(list(self.workspace.iterdir()), [])

    def test_successful_process_without_complete_capture_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'missing or unexpected files'):
            self.run_local(process=lambda args, **kwargs:
                           subprocess.CompletedProcess(args, 0))
        self.assertFalse((self.workspace / REPORT_NAME).exists())

    def test_nonzero_mame_exit_preserves_local_log_and_refuses_audit(self):
        with self.assertRaisesRegex(ValueError, 'exited unsuccessfully'):
            self.run_local(process=lambda args, **kwargs:
                           subprocess.CompletedProcess(args, 3))
        self.assertTrue((self.workspace / LOG_NAME).is_file())
        self.assertFalse((self.workspace / REPORT_NAME).exists())

    def test_private_mame_timeout_does_not_promote_capture(self):
        def timeout(args, **kwargs):
            raise subprocess.TimeoutExpired(args, kwargs['timeout'])
        with self.assertRaisesRegex(ValueError, 'timed out'):
            self.run_local(process=timeout)
        self.assertFalse((self.workspace / REPORT_NAME).exists())

    def test_legacy_v1_capture_is_not_accepted_as_verified_v2(self):
        def old_mame(args, **kwargs):
            return self.populate_fake_private_capture(args, version=1)
        with self.assertRaisesRegex(ValueError, 'conservative V2'):
            self.run_local(process=old_mame)
        self.assertFalse((self.workspace / REPORT_NAME).exists())
        self.assertFalse(any(p.name.startswith('.dino-audit-pending-')
                             for p in self.workspace.iterdir()))

    def test_rgb_check_failure_does_not_publish_partial_report(self):
        with patch('tools.mame_private_dino_session.reference_activity_diagnostic',
                   side_effect=ValueError('synthetic RGB late failure')):
            with self.assertRaisesRegex(ValueError, 'RGB late failure'):
                self.run_local(process=lambda args, **kw:
                               self.populate_fake_private_capture(args))
        self.assertFalse((self.workspace / REPORT_NAME).exists())
        self.assertFalse(any(p.name.startswith('.dino-audit-pending-')
                             for p in self.workspace.iterdir()))
        self.assertTrue((self.workspace / CAPTURE_DIR_NAME).is_dir())

    def test_cross_stream_check_failure_does_not_publish_partial_report(self):
        with patch('tools.mame_private_dino_session.multistream_interval_evidence',
                   side_effect=ValueError('synthetic interval late failure')):
            with self.assertRaisesRegex(ValueError, 'interval late failure'):
                self.run_local(process=lambda args, **kw:
                               self.populate_fake_private_capture(args))
        self.assertFalse((self.workspace / REPORT_NAME).exists())
        self.assertFalse(any(p.name.startswith('.dino-audit-pending-')
                             for p in self.workspace.iterdir()))

    def test_game_capture_mutation_during_interval_analysis_is_rejected(self):
        from tools.mame_multistream_interval_evidence import multistream_interval_evidence
        def mutate_after_valid_intervals(*args, **kwargs):
            result = multistream_interval_evidence(*args, **kwargs)
            target = (self.workspace / CAPTURE_DIR_NAME /
                      'frame-00000904.buffered-obj-be.bin')
            data = bytearray(target.read_bytes())
            data[33] ^= 0x02
            target.write_bytes(data)
            return result
        with patch('tools.mame_private_dino_session.multistream_interval_evidence',
                   side_effect=mutate_after_valid_intervals):
            with self.assertRaisesRegex(ValueError, 'changed during the audit'):
                self.run_local(process=lambda args, **kw:
                               self.populate_fake_private_capture(args))
        self.assertFalse((self.workspace / REPORT_NAME).exists())
        self.assertFalse(any(p.name.startswith('.dino-audit-pending-')
                             for p in self.workspace.iterdir()))

    def test_edit_after_json_serialization_before_publication_fails_closed(self):
        import json as json_module
        real_dump = json_module.dump
        def write_then_change_input(obj, output, **kwargs):
            real_dump(obj, output, **kwargs)
            target = (self.workspace / CAPTURE_DIR_NAME /
                      'frame-00000906.reference-rgb24.bin')
            blob = bytearray(target.read_bytes())
            blob[-1] ^= 0x08
            target.write_bytes(blob)
        with patch('tools.mame_private_dino_session.json.dump',
                   side_effect=write_then_change_input):
            with self.assertRaisesRegex(ValueError, 'changed during the audit'):
                self.run_local(process=lambda args, **kw:
                               self.populate_fake_private_capture(args))
        self.assertFalse((self.workspace / REPORT_NAME).exists())
        self.assertFalse(any(p.name.startswith('.dino-audit-pending-')
                             for p in self.workspace.iterdir()))

    def test_existing_uncounted_file_prevents_complete_audit(self):
        def make_game_with_unexpected_file(args, **kwargs):
            output = self.populate_fake_private_capture(args)
            (self.workspace / CAPTURE_DIR_NAME /
             'untracked-private-image.png').write_bytes(b'never serialize')
            return output
        with self.assertRaisesRegex(ValueError, 'missing or unexpected'):
            self.run_local(process=make_game_with_unexpected_file)
        self.assertFalse((self.workspace / REPORT_NAME).exists())

    def test_malformed_audit_json_does_not_publish_report(self):
        def write_malformed(argv):
            out = Path(argv[argv.index('--out') + 1])
            out.write_bytes(b'{invalid JSON')
            return 0
        with patch('tools.mame_private_dino_session.alignment_main',
                   side_effect=write_malformed):
            with self.assertRaises(json.JSONDecodeError):
                self.run_local(process=lambda args, **kw:
                               self.populate_fake_private_capture(args))
        self.assertFalse((self.workspace / REPORT_NAME).exists())
        self.assertFalse(any(p.name.startswith('.dino-audit-pending-')
                             for p in self.workspace.iterdir()))

    def test_partial_cli_report_with_error_code_is_not_published(self):
        def write_then_fail(argv):
            Path(argv[argv.index('--out') + 1]).write_text('{}')
            return 2
        with patch('tools.mame_private_dino_session.alignment_main',
                   side_effect=write_then_fail):
            with self.assertRaisesRegex(ValueError, 'incomplete or invalid'):
                self.run_local(process=lambda args, **kw:
                               self.populate_fake_private_capture(args))
        self.assertFalse((self.workspace / REPORT_NAME).exists())
        self.assertFalse(any(p.name.startswith('.dino-audit-pending-')
                             for p in self.workspace.iterdir()))

    def test_report_created_during_emulator_run_is_never_overwritten(self):
        def fake_emulator_with_foreign_report(args, **kwargs):
            result = self.populate_fake_private_capture(args)
            (self.workspace / REPORT_NAME).write_bytes(b'PRIVATE_EXISTING_REPORT')
            return result
        with self.assertRaises(FileExistsError):
            self.run_local(process=fake_emulator_with_foreign_report)
        self.assertEqual(
            (self.workspace / REPORT_NAME).read_bytes(),
            b'PRIVATE_EXISTING_REPORT')
        self.assertFalse(any(p.name.startswith('.dino-audit-pending-')
                             for p in self.workspace.iterdir()))

    def test_cli_preflight_hides_absolute_private_rom_path(self):
        text = io.StringIO()
        with contextlib.redirect_stdout(text):
            code = main([
                '--mame', str(self.mame),
                '--mame-tree', str(self.build),
                '--rom-dir', str(self.roms),
                '--workspace', str(self.workspace),
                '--preflight-only',
            ])
        self.assertEqual(code, 0)
        self.assertIn('FILESYSTEM_PREFLIGHT_ONLY', text.getvalue())
        self.assertNotIn(str(self.roms), text.getvalue())
        self.assertNotIn(str(self.workspace), text.getvalue())


if __name__ == '__main__':
    unittest.main()
