"""ROM-free metadata-only stability checks for user-owned private dino entries."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_private_rom_metadata import (
    snapshot_private_dino_rom_entries,
    require_stable_private_dino_rom_entries,
)


class PrivateRomMetadataTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def zip_entry(self):
        archive = self.root / 'dino.zip'
        archive.write_bytes(b'SYNTHETIC_TEST_NOT_A_ROM')
        return archive

    def test_unchanged_zip_is_stable_and_no_bytes_are_opened(self):
        self.zip_entry()
        with patch('builtins.open', side_effect=AssertionError('no ROM reads')):
            first = snapshot_private_dino_rom_entries(self.root)
            self.assertTrue(require_stable_private_dino_rom_entries(
                self.root, first))
        self.assertEqual(len(first), 4)

    def test_modified_zip_is_rejected(self):
        archive = self.zip_entry()
        first = snapshot_private_dino_rom_entries(self.root)
        archive.write_bytes(b'SYNTHETIC_MODIFIED_CONTENT_WITH_EXTRA_LENGTH')
        with self.assertRaisesRegex(ValueError, 'metadata changed'):
            require_stable_private_dino_rom_entries(self.root, first)

    def test_swapped_archive_with_same_bytes_is_rejected(self):
        archive = self.zip_entry()
        first = snapshot_private_dino_rom_entries(self.root)
        replacement = self.root / 'replacement'
        replacement.write_bytes(archive.read_bytes())
        replacement.replace(archive)
        with self.assertRaisesRegex(ValueError, 'metadata changed'):
            require_stable_private_dino_rom_entries(self.root, first)

    def test_missing_and_linked_archive_are_refused(self):
        archive = self.zip_entry()
        first = snapshot_private_dino_rom_entries(self.root)
        archive.unlink()
        with self.assertRaises(ValueError):
            require_stable_private_dino_rom_entries(self.root, first)
        archive.symlink_to(self.root / 'missing')
        with self.assertRaises(ValueError):
            snapshot_private_dino_rom_entries(self.root)

    def test_unpacked_set_can_be_checked_without_file_content_reads(self):
        folder = self.root / 'dino'
        folder.mkdir()
        (folder / 'a').write_bytes(b'SYNTHETIC_A')
        (folder / 'b').write_bytes(b'SYNTHETIC_B')
        first = snapshot_private_dino_rom_entries(self.root)
        with patch('builtins.open', side_effect=AssertionError('no ROM reads')):
            self.assertTrue(require_stable_private_dino_rom_entries(
                self.root, first))
        (folder / 'c').write_bytes(b'SYNTHETIC_C')
        with self.assertRaisesRegex(ValueError, 'metadata changed'):
            require_stable_private_dino_rom_entries(self.root, first)

    def test_unpacked_missing_entry_is_rejected(self):
        folder = self.root / 'dino'
        folder.mkdir()
        (folder / 'a').write_bytes(b'SYNTHETIC_A')
        first = snapshot_private_dino_rom_entries(self.root)
        (folder / 'a').unlink()
        with self.assertRaises(ValueError):
            require_stable_private_dino_rom_entries(self.root, first)

    def test_unpacked_nested_subdirectory_is_not_silently_ignored(self):
        folder = self.root / 'dino'
        folder.mkdir()
        (folder / 'a').write_bytes(b'SYNTHETIC_A')
        (folder / 'nested').mkdir()
        with self.assertRaisesRegex(ValueError, 'type or size'):
            snapshot_private_dino_rom_entries(self.root)

    def test_hardlinked_game_archive_rejected_for_guarded_path(self):
        target = self.root / 'original'
        target.write_bytes(b'SYNTHETIC')
        os.link(target, self.root / 'dino.zip')
        with self.assertRaisesRegex(ValueError, 'multiple hard links'):
            snapshot_private_dino_rom_entries(self.root)

    def test_metadata_never_escapes_into_machine_readable_report(self):
        archive = self.zip_entry()
        snapshot = snapshot_private_dino_rom_entries(self.root)
        self.assertNotIn(str(self.root), json.dumps(
            {'status': 'METADATA_STABLE', 'stable': True}))
        self.assertTrue(require_stable_private_dino_rom_entries(self.root, snapshot))
        self.assertEqual(archive.read_bytes(), b'SYNTHETIC_TEST_NOT_A_ROM')
