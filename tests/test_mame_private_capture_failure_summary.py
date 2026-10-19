"""Fixed-size, redacted reports for failed private game-capture attempts."""
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.mame_private_capture_failure_summary import (
    safe_capture_failure_report, safe_progress_projection,
)
from tools.mame_private_capture_progress import private_capture_progress


class PrivateFailureProgressTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.workspace = Path(tmp.name) / 'isolated'
        self.workspace.mkdir(mode=0o700)
        self.capture = self.workspace / 'cps1-captures'

    def report(self):
        return private_capture_progress(self.workspace)

    def test_no_capture_directory_gives_safe_zero_counts(self):
        result = safe_capture_failure_report(
            ValueError('Local MAME exited unsuccessfully; /secret/dino.zip'),
            self.workspace, include_progress=True)
        self.assertEqual(result['reason_code'], 'LOCAL_MAME_PROCESS_FAILED')
        progress = result['capture_progress']
        self.assertEqual(progress['status'], 'NO_PRIVATE_CAPTURE_DIRECTORY')
        self.assertEqual(progress['present_files'], 0)
        self.assertEqual(progress['missing_files'], 54)
        self.assertEqual(len(progress['source_frame_coverage']), 6)
        self.assertFalse(progress['gameplay_verified'])
        self.assertNotIn('/secret/', json.dumps(result))
        self.assertNotIn(str(self.workspace), json.dumps(result))

    def test_partial_lua_sidecar_counts_but_no_gameplay_claim(self):
        self.capture.mkdir()
        (self.capture / 'frame-00000900.manifest.json').write_bytes(b'{}')
        report = safe_capture_failure_report(
            ValueError('Local MAME session timed out'), self.workspace,
            include_progress=True)
        progress = report['capture_progress']
        self.assertEqual(progress['status'], 'INCOMPLETE_PRIVATE_CAPTURE_FILE_SET')
        self.assertEqual(progress['present_files'], 1)
        self.assertEqual(progress['missing_files'], 53)
        self.assertEqual(progress['source_frame_coverage'][0]['lua_present_files'], 1)
        self.assertEqual(progress['source_frame_coverage'][0]['cpp_present_files'], 0)
        self.assertFalse(progress['capture_contents_read'])
        self.assertFalse(progress['frame_sync_verified'])

    def test_no_opt_in_preserves_existing_safe_cli_response(self):
        result = safe_capture_failure_report(
            ValueError('Local MAME session timed out; /private/rom'), self.workspace)
        self.assertNotIn('capture_progress', result)
        self.assertNotIn('/private/rom', json.dumps(result))
        self.assertEqual(result['reason_code'], 'LOCAL_MAME_PROCESS_FAILED')

    def test_capture_symlink_refuses_progress_and_hides_original_path(self):
        self.capture.symlink_to('/private/secrets/rom/data', target_is_directory=True)
        report = safe_capture_failure_report(
            RuntimeError('Sensitive rom /private/secrets/rom/data'), self.workspace,
            include_progress=True)
        self.assertEqual(report['capture_progress']['status'],
                         'PRIVATE_CAPTURE_PROGRESS_REFUSED')
        self.assertNotIn('/private/secrets', json.dumps(report))

    def test_invalid_workspace_or_missing_workspace_fails_closed(self):
        for candidate in (None, '/secret/nonexistent-private-workspace'):
            with self.subTest(candidate=candidate):
                result = safe_capture_failure_report(
                    OSError('/private/dino.zip'), candidate,
                    include_progress=True)
                self.assertEqual(result['capture_progress']['status'],
                                 'PRIVATE_CAPTURE_PROGRESS_REFUSED')
                self.assertNotIn('dino.zip', json.dumps(result))

    def test_injected_unknown_fields_and_source_paths_not_projected(self):
        src = self.report()
        src['ROM_PRIVATE_PATH'] = '/private/user-owned/dino.zip'
        src['frame_progress'][0]['comment'] = 'SECRET SESSION TOKEN'
        projected = safe_progress_projection(src)
        self.assertNotIn('ROM_PRIVATE_PATH', json.dumps(projected))
        self.assertNotIn('SECRET SESSION TOKEN', json.dumps(projected))
        self.assertFalse(projected['pixel_parity_eligible'])

    def test_foreign_status_and_action_never_accepted(self):
        original = self.report()
        for field in ('status', 'next_local_investigation_code'):
            src = dict(original)
            src[field] = '/private/roms/top-secret.dino.zip'
            with self.subTest(field=field), self.assertRaisesRegex(
                    ValueError, 'status malformed'):
                safe_progress_projection(src)

    def test_malformed_counts_and_frame_labels_refused(self):
        for field, value in (
            ('present_files', 55), ('present_files', True),
            ('present_files', 'rom/private'), ('missing_files', -1),
            ('expected_files', 9), ('invalid_size_files', 61),
        ):
            src = self.report()
            src[field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    safe_progress_projection(src)
        src = self.report()
        src['frame_progress'][0]['nominal_frame'] = 901
        with self.assertRaisesRegex(ValueError, 'label mismatch'):
            safe_progress_projection(src)

    def test_reader_exception_is_always_static(self):
        with patch('tools.mame_private_capture_failure_summary.private_capture_progress',
                   side_effect=RuntimeError('SUPER-SECRET-ROM /private/assets')):
            report = safe_capture_failure_report(
                ValueError('Private capture incomplete'), self.workspace,
                include_progress=True)
        self.assertEqual(report['capture_progress']['status'],
                         'PRIVATE_CAPTURE_PROGRESS_REFUSED')
        self.assertNotIn('SUPER-SECRET-ROM', json.dumps(report))

    def test_complete_size_only_set_is_still_not_validated(self):
        from tools.mame_private_capture_stability import EXPECTED_SIZES
        self.capture.mkdir()
        for index in range(6):
            frame = 900 + index * 2
            for suffix, size in EXPECTED_SIZES.items():
                with (self.capture / f'frame-{frame:08d}.{suffix}').open('wb') as f:
                    f.truncate(min(size, 10) if suffix in (
                        'manifest.json', 'obj-latch-count.txt') else size)
        report = safe_capture_failure_report(
            ValueError('Private capture is incomplete or invalid'),
            self.workspace, include_progress=True)
        progress = report['capture_progress']
        self.assertEqual(progress['status'], 'COMPLETE_FILE_SET_UNVERIFIED')
        self.assertEqual(progress['complete_metadata_frames'], 6)
        self.assertEqual(progress['present_files'], 54)
        self.assertFalse(progress['gameplay_verified'])
        self.assertFalse(progress['pixel_parity_eligible'])


if __name__ == '__main__':
    unittest.main()
