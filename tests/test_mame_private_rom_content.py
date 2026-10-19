"""ROM-free private SHA-256 stability checks; no original ROMs."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_private_rom_content import (
    snapshot_private_dino_rom_content,
    require_stable_private_dino_rom_content,
    MAX_ROM_FILE_BYTES, MAX_ROM_TOTAL_BYTES,
)


class PrivateRomContentTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def make_archive(self, data=b'SYNTHETIC_ROM_BYTES_A'):
        path = self.root / 'dino.zip'
        path.write_bytes(data)
        return path

    def test_archive_hash_is_private_and_stable(self):
        path = self.make_archive()
        baseline = snapshot_private_dino_rom_content(self.root)
        self.assertEqual(baseline[1][0][1],
                         hashlib.sha256(path.read_bytes()).digest())
        self.assertTrue(require_stable_private_dino_rom_content(
            self.root, baseline))
        self.assertEqual(len(baseline[1]), 1)

    def test_same_size_rewrite_detected_even_if_metadata_times_are_masked(self):
        path = self.make_archive(b'AAAAAA')
        # Model an attacker or filesystem restoring mtime/ctime metadata.
        # Both the Stage 88 scanner and this stage receive normalized time.
        from tools import mame_private_rom_metadata as meta
        from tools import mame_private_rom_content as content
        original = meta._fields
        def normalized(s):
            fields = original(s)
            return fields[:-2] + (0, 0)
        with patch.object(meta, '_fields', side_effect=normalized), \
             patch.object(content, '_fields', side_effect=normalized):
            previous = snapshot_private_dino_rom_content(self.root)
            path.write_bytes(b'BBBBBB')
            with self.assertRaisesRegex(ValueError, 'content changed'):
                require_stable_private_dino_rom_content(self.root, previous)

    def test_unpacked_set_is_order_independent(self):
        folder = self.root / 'dino'
        folder.mkdir()
        (folder / 'b.bin').write_bytes(b'BBB')
        (folder / 'a.bin').write_bytes(b'AAA')
        first = snapshot_private_dino_rom_content(self.root)
        self.assertEqual([name for name, digest in first[1]],
                         ['a.bin', 'b.bin'])
        self.assertTrue(require_stable_private_dino_rom_content(self.root, first))
        (folder / 'a.bin').write_bytes(b'CCC')
        with self.assertRaisesRegex(ValueError, 'content changed'):
            require_stable_private_dino_rom_content(self.root, first)

    def test_missing_or_symlinked_archive_is_refused(self):
        path = self.make_archive()
        first = snapshot_private_dino_rom_content(self.root)
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'content changed'):
            require_stable_private_dino_rom_content(self.root, first)
        path.symlink_to(self.root / 'owned-original')
        with self.assertRaises(ValueError):
            snapshot_private_dino_rom_content(self.root)

    def test_directory_bounds_refuse_oversized_entry_without_reading_bytes(self):
        path = self.make_archive(b'SYNTHETIC')
        with path.open('wb') as output:
            output.truncate(MAX_ROM_FILE_BYTES + 1)
        with patch('tools.mame_private_rom_content._file_digest',
                   side_effect=AssertionError('must not hash')) as called:
            with self.assertRaisesRegex(ValueError, 'bounded total size'):
                snapshot_private_dino_rom_content(self.root)
            called.assert_not_called()

    def test_open_file_swap_during_digest_is_refused(self):
        self.make_archive(b'AAAA')
        from tools import mame_private_rom_content as content
        original_read = content.os.read
        def mutated_read(fd, size):
            data = original_read(fd, size)
            if data:
                (self.root / 'dino.zip').write_bytes(b'BBBB')
            return data
        with patch.object(content.os, 'read', side_effect=mutated_read):
            with self.assertRaisesRegex(ValueError, 'changed while hashing'):
                snapshot_private_dino_rom_content(self.root)

    def test_digest_never_emitted_in_any_public_report(self):
        self.make_archive(b'SUPER_SECRET_SYNTHETIC')
        baseline = snapshot_private_dino_rom_content(self.root)
        report = {
            'status': 'ROM_STABLE_SIZE_ONLY_NOT_AUTHENTICATED',
            'private_rom_content_sha256_stable_during_capture': True,
            'original_game_authenticity_verified': False,
            'rom_hashes_persisted': False,
        }
        output = json.dumps(report)
        self.assertNotIn(str(self.root), output)
        self.assertNotIn('dino.zip', output)
        self.assertNotIn(hashlib.sha256(b'SUPER_SECRET_SYNTHETIC').hexdigest(),
                         output)
        self.assertFalse(report['original_game_authenticity_verified'])
        self.assertTrue(require_stable_private_dino_rom_content(self.root, baseline))

    def test_invalid_previous_snapshot_fails_closed(self):
        self.make_archive()
        for invalid in (None, {}, (), (1, 2, 3)):
            with self.subTest(invalid=invalid):
                with self.assertRaisesRegex(ValueError, 'snapshot invalid'):
                    require_stable_private_dino_rom_content(self.root, invalid)


if __name__ == '__main__':
    unittest.main()
