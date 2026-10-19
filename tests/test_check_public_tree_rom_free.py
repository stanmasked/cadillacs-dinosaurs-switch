"""Synthetic ROM-free regressions for a public code-only Git staging gate."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.check_public_tree_rom_free import check_staged_git_tree, main


class PublicTreePrivacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(['git', 'init', '-q', str(self.root)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.put('README.md', b'# Synthetic source only\n')

    def git(self, *args):
        subprocess.run(['git', '-C', str(self.root), *args],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def put(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.git('add', '-f', '--', name)

    def test_safe_source_index_is_accepted(self):
        self.put('tools/safe.lua', b'-- synthetic code only\n')
        out = check_staged_git_tree(self.root)
        self.assertEqual(out['status'],
                         'PUBLIC_CODE_TREE_ROM_FREE_METADATA_CHECK_PASSED')
        self.assertEqual(out['tracked_entries_examined'], 2)
        self.assertEqual(out['rejected_entry_count'], 0)
        self.assertFalse(out['git_history_checked'])

    def test_project_precommit_hook_is_allowed_but_other_extensionless_is_not(self):
        self.put('.githooks/pre-commit',
                 b'#!/bin/sh\nexec python3 tools/check_public_tree_rom_free.py\n')
        result = check_staged_git_tree(self.root)
        self.assertEqual(result['rejected_entry_count'], 0)
        self.put('other/private-script', b'not-a-source-document')
        result = check_staged_git_tree(self.root)
        self.assertEqual(result['fixed_reason_counts']['forbidden_paths'], 1)

    def test_zip_and_bin_forced_into_index_are_refused_without_paths(self):
        self.put('dino.zip', b'PK\x03\x04SYNTHETIC NOT ORIGINAL')
        self.put('roms/gfx.bin', b'SYNTHETIC BYTES')
        out = check_staged_git_tree(self.root)
        self.assertEqual(out['rejected_entry_count'], 2)
        self.assertEqual(out['fixed_reason_counts']['forbidden_paths'], 2)
        report = json.dumps(out)
        self.assertNotIn('dino.zip', report)
        self.assertNotIn('gfx.bin', report)

    def test_renamed_rom_archive_magic_is_rejected(self):
        self.put('tools/disguised.txt', b'PK\x03\x04SYNTHETIC')
        out = check_staged_git_tree(self.root)
        self.assertEqual(out['fixed_reason_counts']['non_source_content'], 1)

    def test_lfs_pointer_does_not_bypass_blocked_artifact_checks(self):
        self.put('docs/fake_pointer.md',
                 b'version https://git-lfs.github.com/spec/v1\n'
                 b'oid sha256:00000000000000000000000000000000\n')
        out = check_staged_git_tree(self.root)
        self.assertEqual(out['fixed_reason_counts']['non_source_content'], 1)

    def test_large_source_blob_is_refused(self):
        self.put('tools/oversized.py', b'# synthetic\n' * 30000)
        out = check_staged_git_tree(self.root)
        self.assertEqual(out['fixed_reason_counts']['oversized_source_blobs'], 1)

    def test_symlink_in_git_index_is_refused(self):
        target = self.root / 'rom-file'
        target.write_text('private data')
        link = self.root / 'tools' / 'linked.py'
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
        self.git('add', '-f', '--', 'tools/linked.py')
        out = check_staged_git_tree(self.root)
        self.assertEqual(out['fixed_reason_counts']['unsafe_git_entries'], 1)

    def test_index_is_authoritative_not_unstaged_working_copy(self):
        self.put('tools/clean.py', b'# staged safe\n')
        (self.root / 'tools/clean.py').write_bytes(b'PK\x03\x04not-staged')
        out = check_staged_git_tree(self.root)
        self.assertEqual(out['rejected_entry_count'], 0)

    def test_non_source_extension_and_binary_content_rejected(self):
        self.put('assets/custom.abc', b'SYNTHETIC DATA')
        self.put('tools/nul.py', b'hello\x00world')
        out = check_staged_git_tree(self.root)
        self.assertEqual(out['fixed_reason_counts']['forbidden_paths'], 1)
        self.assertEqual(out['fixed_reason_counts']['non_source_content'], 1)

    def test_cli_exit_codes_are_safe_and_fixed(self):
        console = io.StringIO()
        with contextlib.redirect_stdout(console):
            code = main(['--repository', str(self.root)])
        self.assertEqual(code, 0)
        self.assertNotIn(str(self.root), console.getvalue())
        self.put('game/dino.gen', b'not-real-rom')
        console = io.StringIO()
        with contextlib.redirect_stdout(console):
            code = main(['--repository', str(self.root)])
        self.assertEqual(code, 2)
        self.assertNotIn('dino.gen', console.getvalue())
        self.assertFalse(json.loads(console.getvalue())[
            'private_paths_or_blob_bytes_emitted'])

    def test_git_error_never_displays_private_paths(self):
        console = io.StringIO()
        with contextlib.redirect_stdout(console):
            code = main(['--repository', str(self.root / 'SECRET_NONEXISTENT_REPOSITORY')])
        self.assertEqual(code, 2)
        self.assertNotIn('SECRET_NONEXISTENT_REPOSITORY', console.getvalue())
        self.assertEqual(json.loads(console.getvalue())['rejected_entry_count'], 1)


if __name__ == '__main__':
    unittest.main()
