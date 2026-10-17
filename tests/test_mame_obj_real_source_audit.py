"""ROM-free independent audit of instrumented original MAME video C++.

The full upstream mame0289 source is fetched only in CI (verified by its
exact Git blob) and is never committed to this repository.
"""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_mame_obj_source_probe import MINIMAL_SOURCE
from tools.mame_obj_source_probe import instrument, git_blob_sha
from tools import mame_obj_real_source_audit as audit


class MameVerifiedSourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.original = MINIMAL_SOURCE.encode('utf-8')
        self.generated = instrument(MINIMAL_SOURCE).encode('utf-8')
        self.patcher = patch.object(
            audit, 'EXPECTED_MAME_BLOB', git_blob_sha(self.original))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_allowed_insertions_restore_pristine_source_byte_for_byte(self):
        report = audit.audit_original_and_generated(
            self.original, self.generated)
        self.assertEqual(report['approved_insertions'], 3)
        self.assertTrue(report['byte_exact_restoration'])
        self.assertEqual(report['source_git_blob_sha1'],
                         git_blob_sha(self.original))
        self.assertFalse(report['actual_upstream_source_compiled'])
        self.assertFalse(report['original_game_frame_sync_verified'])
        self.assertFalse(report['pixel_parity_eligible'])

    def test_rejects_another_mame_tag_or_edited_upstream(self):
        with self.assertRaisesRegex(ValueError, 'Unexpected upstream Git blob'):
            audit.audit_original_and_generated(
                self.original + b'\n', self.generated)

    def test_rejects_source_content_modified_outside_insertions(self):
        generated = self.generated + b'// unexpected mutation\n'
        with self.assertRaisesRegex(ValueError, 'changed original MAME code'):
            audit.audit_original_and_generated(self.original, generated)

    def test_rejects_generated_probe_hash_or_counter_mutation(self):
        for old, new in (
            (b'1099511628211ULL', b'1099511628212ULL'),
            (b'CPS1_DINO_LATCH_V2', b'CPS1_DINO_LATCH_V3'),
            (b'uint16_t observed_obj_words[0x400];',
             b'uint16_t observed_obj_words[0x200];'),
        ):
            with self.subTest(change=old[:30]):
                self.assertIn(old, self.generated)
                with self.assertRaisesRegex(ValueError, 'missing exact approved'):
                    audit.audit_original_and_generated(
                        self.original,
                        self.generated.replace(old, new, 1))

    def test_rejects_missing_latch_instrumentation(self):
        replaced = self.generated.replace(
            b'cps1_dino_obj_latch_events.fetch_add',
            b'cps1_dino_obj_latch_events.no_increment')
        with self.assertRaisesRegex(ValueError, 'missing exact approved'):
            audit.audit_original_and_generated(self.original, replaced)

    def test_rejects_identical_raw_inputs(self):
        with self.assertRaisesRegex(ValueError, 'missing exact approved'):
            audit.audit_original_and_generated(
                self.original, self.original)

    def test_rejects_bad_types_and_invalid_utf8(self):
        with self.assertRaisesRegex(ValueError, 'requires original'):
            audit.audit_original_and_generated(
                self.original.decode(), self.generated)
        with self.assertRaisesRegex(ValueError, 'must be UTF-8'):
            audit.audit_original_and_generated(
                self.original, self.generated + b'\xff')

    def test_cli_accepts_distinct_files_but_never_echoes_game_source(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / 'mame.cpp'
            generated = Path(folder) / 'patched.cpp'
            original.write_bytes(self.original)
            generated.write_bytes(self.generated)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                status = audit.main([str(original), str(generated)])
            self.assertEqual(status, 0)
            output = stdout.getvalue()
            self.assertIn('"byte_exact_restoration": true', output)
            self.assertNotIn('memcpy(m_buffered_obj', output)
            self.assertNotIn('#include "cps1.h"', output)

    def test_cli_rejects_same_file_or_missing_input(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / 'mame.cpp'
            missing = Path(folder) / 'absent.cpp'
            original.write_bytes(self.original)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(audit.main([str(original), str(original)]), 2)
                self.assertEqual(audit.main([str(original), str(missing)]), 2)


if __name__ == '__main__':
    unittest.main()
