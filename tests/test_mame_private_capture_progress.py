"""ROM-free bounded metadata progress scan for a failed MAME capture."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_private_capture_progress import (
    private_capture_progress, main, CAPTURE_DIR_NAME, MAX_SCAN_ENTRIES,
)
from tools.mame_private_capture_stability import EXPECTED_SIZES


class PrivateCaptureProgressTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name) / 'workspace'
        self.workspace.mkdir(mode=0o700)
        self.captures = self.workspace / CAPTURE_DIR_NAME

    def add_frame(self, frame, suffixes=None):
        self.captures.mkdir(exist_ok=True)
        for suffix in suffixes or EXPECTED_SIZES:
            expected = EXPECTED_SIZES[suffix]
            path = self.captures / f'frame-{frame:08d}.{suffix}'
            with path.open('wb') as f:
                f.truncate(min(55, expected) if suffix in (
                    'manifest.json', 'obj-latch-count.txt') else expected)

    def test_absent_capture_dir_requires_private_startup_inspection(self):
        out = private_capture_progress(self.workspace)
        self.assertEqual(out['status'], 'NO_PRIVATE_CAPTURE_DIRECTORY')
        self.assertEqual(out['expected_files'], 54)
        self.assertEqual(out['present_files'], 0)
        self.assertEqual(out['missing_files'], 54)
        self.assertEqual(out['complete_metadata_frames'], 0)
        self.assertEqual(out['stream_coverage']['neither_complete_size_only_frames'], 6)
        self.assertEqual(out['frame_progress'][0]['lua_size_only_state'], 'ABSENT')
        self.assertEqual(out['frame_progress'][0]['cpp_size_only_state'], 'ABSENT')
        self.assertEqual(out['next_local_investigation_code'],
                         'INSPECT_PRIVATE_MAME_STARTUP_LOG')
        self.assertFalse(out['capture_validated'])
        self.assertFalse(out['rom_bytes_read'])

    def test_empty_directory_has_separate_missing_hooks_diagnosis(self):
        self.captures.mkdir()
        out = private_capture_progress(self.workspace)
        self.assertEqual(out['status'], 'NO_EXPECTED_PRIVATE_CAPTURE_FILES')
        self.assertEqual(out['unexpected_entry_count'], 0)
        self.assertFalse(out['active_gameplay_verified'])

    def test_partial_lua_and_cpp_frame_coverage_are_reported(self):
        self.add_frame(900, ('gfxram-be.bin', 'manifest.json',
                             'render-regs-be.bin'))
        self.add_frame(902)
        out = private_capture_progress(self.workspace)
        self.assertEqual(out['status'], 'INCOMPLETE_PRIVATE_CAPTURE_FILE_SET')
        self.assertEqual(out['present_files'], 12)
        self.assertEqual(out['missing_files'], 42)
        self.assertEqual(out['complete_metadata_frames'], 1)
        self.assertEqual(out['frame_progress'][0]['lua_files_present'], 2)
        self.assertEqual(out['frame_progress'][0]['cpp_files_present'], 1)
        self.assertEqual(out['frame_progress'][0]['lua_valid_sized_files'], 2)
        self.assertEqual(out['frame_progress'][0]['cpp_valid_sized_files'], 1)
        self.assertTrue(out['frame_progress'][0]['lua_manifest_present'])
        self.assertFalse(out['frame_progress'][0]['cpp_latch_sidecar_present'])
        self.assertEqual(out['frame_progress'][0]['cross_stream_size_only_state'],
                         'NEITHER_COMPLETE_SIZE_ONLY')
        self.assertEqual(
            out['stream_coverage']['lua_manifest_with_incomplete_components_frames'], 1)
        self.assertEqual(out['frame_progress'][1]['valid_sized_files'], 9)
        self.assertEqual(out['frame_progress'][5]['present_files'], 0)
        self.assertFalse(out['capture_validated'])

    def test_complete_metadata_cannot_claim_valid_gameplay(self):
        for frame in (900, 902, 904, 906, 908, 910):
            self.add_frame(frame)
        out = private_capture_progress(self.workspace)
        self.assertEqual(out['status'], 'COMPLETE_FILE_SET_UNVERIFIED')
        self.assertEqual(out['present_files'], 54)
        self.assertEqual(out['complete_metadata_frames'], 6)
        self.assertEqual(out['stream_coverage']['paired_complete_size_only_frames'], 6)
        self.assertEqual(out['stream_coverage']['neither_complete_size_only_frames'], 0)
        self.assertEqual(out['frame_progress'][5]['cross_stream_size_only_state'],
                         'BOTH_COMPLETE_SIZE_ONLY')
        self.assertEqual(out['next_local_investigation_code'],
                         'RUN_FULL_PRIVATE_CAPTURE_INTEGRITY_AUDIT')
        for key in ('capture_validated', 'active_gameplay_verified',
                    'frame_sync_verified', 'pixel_parity_eligible'):
            self.assertFalse(out[key])

    def test_only_lua_files_suggest_cpp_local_probe_inspection(self):
        for frame in (900, 902, 904):
            self.add_frame(frame, (
                'gfxram-be.bin', 'cps-a-be.bin', 'cps-b-be.bin',
                'palette-rgb24.bin', 'reference-rgb24.bin', 'manifest.json'))
        out = private_capture_progress(self.workspace)
        self.assertEqual(out['status'], 'INCOMPLETE_PRIVATE_CAPTURE_FILE_SET')
        self.assertEqual(out['stream_coverage']['lua_complete_size_only_frames'], 3)
        self.assertEqual(out['stream_coverage']['cpp_complete_size_only_frames'], 0)
        self.assertEqual(out['stream_coverage']['paired_complete_size_only_frames'], 0)
        self.assertEqual(out['frame_progress'][0]['cpp_size_only_state'], 'ABSENT')
        self.assertEqual(out['frame_progress'][0]['cross_stream_size_only_state'],
                         'LUA_COMPLETE_CPP_INCOMPLETE')
        self.assertEqual(out['next_local_investigation_code'],
                         'INSPECT_CPP_VIDEO_UPDATE_CAPTURE_HOOK')
        self.assertFalse(out['capture_validated'])

    def test_only_cpp_files_suggest_lua_local_hook_inspection(self):
        for frame in (900, 902):
            self.add_frame(frame, (
                'render-regs-be.bin', 'buffered-obj-be.bin', 'obj-latch-count.txt'))
        out = private_capture_progress(self.workspace)
        self.assertEqual(out['stream_coverage']['cpp_complete_size_only_frames'], 2)
        self.assertEqual(out['stream_coverage']['lua_complete_size_only_frames'], 0)
        self.assertEqual(out['frame_progress'][1]['cross_stream_size_only_state'],
                         'CPP_COMPLETE_LUA_INCOMPLETE')
        self.assertEqual(out['next_local_investigation_code'],
                         'INSPECT_LUA_FRAME_DONE_CAPTURE_HOOK')
        self.assertFalse(out['frame_sync_verified'])

    def test_mixed_complete_streams_identify_nominal_coverage_mismatch(self):
        self.add_frame(900, (
            'gfxram-be.bin', 'cps-a-be.bin', 'cps-b-be.bin',
            'palette-rgb24.bin', 'reference-rgb24.bin', 'manifest.json'))
        self.add_frame(902, (
            'render-regs-be.bin', 'buffered-obj-be.bin', 'obj-latch-count.txt'))
        self.add_frame(904)
        out = private_capture_progress(self.workspace)
        coverage = out['stream_coverage']
        self.assertEqual(coverage['paired_complete_size_only_frames'], 1)
        self.assertEqual(coverage['lua_complete_cpp_incomplete_frames'], 1)
        self.assertEqual(coverage['cpp_complete_lua_incomplete_frames'], 1)
        self.assertEqual(coverage['neither_complete_size_only_frames'], 3)
        self.assertEqual(out['next_local_investigation_code'],
                         'COMPARE_LUA_CPP_NOMINAL_FRAME_COVERAGE')

    def test_offset_plus_one_in_directory_scan_is_not_vblank_proof(self):
        lua = ('gfxram-be.bin', 'cps-a-be.bin', 'cps-b-be.bin',
               'palette-rgb24.bin', 'reference-rgb24.bin', 'manifest.json')
        cpp = ('render-regs-be.bin', 'buffered-obj-be.bin', 'obj-latch-count.txt')
        for index in (0, 1, 2):
            self.add_frame(900 + 2 * index, lua)
        for index in (1, 2, 3):
            self.add_frame(900 + 2 * index, cpp)
        out = private_capture_progress(self.workspace)
        hint = out['nominal_coverage_shift_hypotheses']
        self.assertEqual(hint['status'], 'OFF_LABEL_COVERAGE_HYPOTHESIS_ONLY')
        self.assertEqual(hint['candidate_cpp_relative_to_lua_shift_samples'], 1)
        self.assertEqual(out['next_local_investigation_code'],
                         'INSPECT_LUA_CPP_NOMINAL_LABEL_COVERAGE_OFFSET')
        self.assertFalse(hint['hypothesis_verified'])
        self.assertFalse(out['capture_validated'])

    def test_offset_hypotheses_do_not_override_size_or_unexpected_errors(self):
        lua = ('gfxram-be.bin', 'cps-a-be.bin', 'cps-b-be.bin',
               'palette-rgb24.bin', 'reference-rgb24.bin', 'manifest.json')
        cpp = ('render-regs-be.bin', 'buffered-obj-be.bin', 'obj-latch-count.txt')
        for index in (0, 1, 2):
            self.add_frame(900 + 2 * index, lua)
        for index in (1, 2, 3):
            self.add_frame(900 + 2 * index, cpp)
        broken = self.captures / 'frame-00000900.reference-rgb24.bin'
        broken.write_bytes(b'x')
        out = private_capture_progress(self.workspace)
        self.assertEqual(out['next_local_investigation_code'],
                         'INSPECT_PRIVATE_CAPTURE_PARTIAL_WRITES')
        self.assertEqual(out['nominal_coverage_shift_hypotheses']['status'],
                         'INSUFFICIENT_COMPLETE_SOURCE_FRAMES')
        broken.unlink()
        self.add_frame(900, ('reference-rgb24.bin',))
        (self.captures / 'sensitive-local-unexpected').write_bytes(b'secret')
        out = private_capture_progress(self.workspace)
        self.assertEqual(out['status'], 'UNEXPECTED_PRIVATE_CAPTURE_ENTRIES')
        self.assertEqual(out['next_local_investigation_code'],
                         'INSPECT_PRIVATE_CAPTURE_EXTRA_FILES')
        self.assertNotIn('sensitive-local-unexpected', json.dumps(out))

    def test_latch_sidecar_present_without_cpp_pair_is_annotation_only(self):
        self.add_frame(900, ('obj-latch-count.txt',))
        out = private_capture_progress(self.workspace)
        self.assertEqual(
            out['stream_coverage']['cpp_latch_sidecar_with_incomplete_components_frames'], 1)
        self.assertTrue(out['frame_progress'][0]['cpp_latch_sidecar_present'])
        self.assertEqual(out['frame_progress'][0]['cpp_size_only_state'],
                         'INCOMPLETE_SIZE_ONLY')
        self.assertFalse(out['capture_validated'])

    def test_bad_size_cannot_mark_lua_cpp_stream_complete(self):
        self.add_frame(900)
        (self.captures / 'frame-00000900.buffered-obj-be.bin').write_bytes(b'x')
        out = private_capture_progress(self.workspace)
        self.assertEqual(out['status'], 'INVALID_PRIVATE_CAPTURE_FILE_SIZES')
        self.assertEqual(out['frame_progress'][0]['lua_size_only_state'],
                         'COMPLETE_SIZE_ONLY')
        self.assertEqual(out['frame_progress'][0]['cpp_size_only_state'],
                         'INCOMPLETE_SIZE_ONLY')
        self.assertEqual(out['frame_progress'][0]['cross_stream_size_only_state'],
                         'LUA_COMPLETE_CPP_INCOMPLETE')
        self.assertEqual(out['stream_coverage']['paired_complete_size_only_frames'], 0)
        self.assertEqual(out['next_local_investigation_code'],
                         'INSPECT_PRIVATE_CAPTURE_PARTIAL_WRITES')

    def test_bounded_size_error_does_not_open_private_frame(self):
        self.add_frame(900)
        broken = self.captures / 'frame-00000900.reference-rgb24.bin'
        broken.write_bytes(b'x')
        with patch('builtins.open', side_effect=AssertionError('must not read')):
            out = private_capture_progress(self.workspace)
        self.assertEqual(out['status'], 'INVALID_PRIVATE_CAPTURE_FILE_SIZES')
        self.assertEqual(out['invalid_size_files'], 1)
        self.assertEqual(out['valid_sized_files'], 8)
        self.assertEqual(out['complete_metadata_frames'], 0)

    def test_extra_file_is_counted_but_name_never_exposed(self):
        self.add_frame(900)
        (self.captures / 'TOP-SECRET-ROM-FILENAME.bin').write_bytes(b'private')
        out = private_capture_progress(self.workspace)
        self.assertEqual(out['status'], 'UNEXPECTED_PRIVATE_CAPTURE_ENTRIES')
        self.assertEqual(out['unexpected_entry_count'], 1)
        self.assertNotIn('TOP-SECRET', json.dumps(out))

    def test_symlink_and_hardlink_refused_without_following(self):
        self.add_frame(900)
        target = self.captures / 'frame-00000900.reference-rgb24.bin'
        linked = self.captures / 'linked-frame'
        linked.symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'unsafe or linked'):
            private_capture_progress(self.workspace)
        linked.unlink()
        os.link(target, linked)
        with self.assertRaisesRegex(ValueError, 'unsafe or linked'):
            private_capture_progress(self.workspace)

    def test_capture_directory_symlink_is_rejected(self):
        actual = self.workspace / 'real-capture'
        actual.mkdir()
        self.captures.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            private_capture_progress(self.workspace)

    def test_scanner_refuses_more_than_bounded_entry_count(self):
        self.captures.mkdir()
        for i in range(MAX_SCAN_ENTRIES + 1):
            (self.captures / f'synthetic-{i}').touch()
        with self.assertRaisesRegex(ValueError, 'bounded scan'):
            private_capture_progress(self.workspace)

    def test_rejects_unprivate_workspace_and_path_links(self):
        self.workspace.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'permissions'):
            private_capture_progress(self.workspace)
        self.workspace.chmod(0o700)
        alias = self.workspace.parent / 'linked-workspace'
        alias.symlink_to(self.workspace, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            private_capture_progress(alias)

    def test_cli_never_echoes_paths_or_exception_data(self):
        self.captures.mkdir()
        (self.captures / 'secret-private-file').write_bytes(b'not a ROM')
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = main(['--workspace', str(self.workspace)])
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.workspace), stdout.getvalue())
        self.assertNotIn('secret-private-file', stdout.getvalue())
        stderr = io.StringIO()
        with patch('tools.mame_private_capture_progress.private_capture_progress',
                   side_effect=OSError('private-secret /roms/dino.zip')), \
             contextlib.redirect_stderr(stderr):
            code = main(['--workspace', str(self.workspace)])
        self.assertEqual(code, 2)
        self.assertNotIn('/roms/dino.zip', stderr.getvalue())
        self.assertEqual(json.loads(stderr.getvalue())['status'],
                         'PRIVATE_CAPTURE_PROGRESS_REFUSED')


if __name__ == '__main__':
    unittest.main()
