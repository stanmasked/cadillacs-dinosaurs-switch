"""Synthetic checks of safe MAME playback file planning."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.mame_playback_plan import (playback_plan, confirm_playback_unchanged,
                                      MAX_INPUT_BYTES)


class PlaybackPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'first-stage.inp'
        self.data = b'local synthetic test input; not a genuine MAME replay'
        self.path.write_bytes(self.data)

    def test_absent_replay_is_explicitly_unverified(self):
        args, report = playback_plan(None)
        self.assertEqual(args, [])
        self.assertFalse(report['enabled'])
        self.assertFalse(report['input_replay_verified'])

    def test_direct_argv_and_hash_only_provenance(self):
        argv, report = playback_plan(self.path)
        self.assertEqual(argv, ['-playback', str(self.path.resolve())])
        self.assertEqual(report['bytes'], len(self.data))
        self.assertEqual(report['sha256'], hashlib.sha256(self.data).hexdigest())
        self.assertFalse(report['input_replay_verified'])
        self.assertNotIn(str(self.path), str(report))
        self.assertNotIn('synthetic test input', str(report))

    def test_detect_change_after_initial_check(self):
        _, report = playback_plan(self.path)
        self.assertTrue(confirm_playback_unchanged(self.path, report))
        self.path.write_bytes(self.data.replace(b'local', b'other'))
        self.assertFalse(confirm_playback_unchanged(self.path, report))

    def test_reject_empty(self):
        self.path.write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'size'):
            playback_plan(self.path)

    def test_reject_excessive_size_without_reading_it(self):
        with self.path.open('wb') as f:
            f.truncate(MAX_INPUT_BYTES + 1)
        with self.assertRaisesRegex(ValueError, 'size'):
            playback_plan(self.path)

    def test_reject_directory_missing_and_non_inp(self):
        for item in (Path(self.temp.name), Path(self.temp.name)/'missing.inp'):
            with self.subTest(item=str(item)), self.assertRaises(ValueError):
                playback_plan(item)
        bad = self.path.with_suffix('.zip')
        bad.write_bytes(self.data)
        with self.assertRaisesRegex(ValueError, '.inp'):
            playback_plan(bad)

    def test_reject_symlink_to_valid_inp(self):
        link = Path(self.temp.name)/'redirect.inp'
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            playback_plan(link)

    def test_extension_case_insensitive(self):
        renamed = self.path.with_suffix('.INP')
        self.path.rename(renamed)
        args, report = playback_plan(renamed)
        self.assertEqual(args[0], '-playback')
        self.assertTrue(report['enabled'])


if __name__ == '__main__':
    unittest.main()
