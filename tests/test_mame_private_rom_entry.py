"""ROM-free tests for local-only original dino asset placement metadata."""
from pathlib import Path
import tempfile
import unittest

from tools.mame_private_rom_entry import require_private_dino_entry


class PrivateDinoEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_nonempty_zip_entry_is_reported_without_rom_reads(self):
        (self.root / 'dino.zip').write_bytes(b'synthetic-not-a-ROM')
        result = require_private_dino_entry(self.root)
        self.assertEqual(result['status'],
                         'PRIVATE_DINO_ROM_ENTRY_PRESENT_UNVALIDATED')
        self.assertTrue(result['game_set_entry_observed'])
        self.assertFalse(result['rom_file_bytes_read'])
        self.assertFalse(result['rom_integrity_verified'])
        self.assertFalse(result['game_executed'])

    def test_unpacked_dino_folder_is_allowed_without_opening_bytes(self):
        folder = self.root / 'dino'
        folder.mkdir()
        (folder / 'synthetic.bin').write_bytes(b'not-ROM-data')
        result = require_private_dino_entry(self.root)
        self.assertTrue(result['game_set_entry_observed'])
        self.assertFalse(result['rom_set_completeness_verified'])

    def test_missing_or_empty_zip_refused(self):
        with self.assertRaisesRegex(ValueError, 'No private dino'):
            require_private_dino_entry(self.root)
        (self.root / 'dino.zip').touch()
        with self.assertRaisesRegex(ValueError, 'nonempty regular'):
            require_private_dino_entry(self.root)

    def test_zip_symlink_refused_even_when_target_is_nonempty(self):
        data = self.root / 'owned.zip'
        data.write_bytes(b'private-data')
        (self.root / 'dino.zip').symlink_to(data)
        with self.assertRaisesRegex(ValueError, 'nonempty regular'):
            require_private_dino_entry(self.root)

    def test_directory_symlink_and_empty_unpacked_folder_refused(self):
        actual = self.root / 'owned-folder'
        actual.mkdir()
        (actual / 'file').write_bytes(b'private-data')
        link = self.root / 'dino'
        link.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'real directory'):
            require_private_dino_entry(self.root)
        link.unlink()
        link.mkdir()
        with self.assertRaisesRegex(ValueError, 'no nonempty files'):
            require_private_dino_entry(self.root)

    def test_unpacked_unsafe_entries_rejected_even_with_valid_rom(self):
        unpacked = self.root / 'dino'
        unpacked.mkdir()
        (unpacked / 'synthetic.bin').write_bytes(b'fake')
        (unpacked / 'linked').symlink_to(unpacked / 'synthetic.bin')
        with self.assertRaisesRegex(ValueError, 'unsafe entries'):
            require_private_dino_entry(self.root)

    def test_nonprivate_path_rejected(self):
        with self.assertRaisesRegex(ValueError, 'ordinary directory'):
            require_private_dino_entry(self.root / 'missing')
        ordinary_file = self.root / 'somefile'
        ordinary_file.write_bytes(b'fake')
        with self.assertRaisesRegex(ValueError, 'ordinary directory'):
            require_private_dino_entry(ordinary_file)

    def test_reports_no_content_or_local_private_paths(self):
        import json
        (self.root / 'dino.zip').write_bytes(b'original-secret-digest-data')
        report = require_private_dino_entry(self.root)
        text = json.dumps(report)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn('original-secret-digest-data', text)
        self.assertNotIn('dino.zip', text)
        self.assertFalse(report['original_game_authenticity_verified'])
