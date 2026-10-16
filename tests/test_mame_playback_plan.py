"""Synthetic checks of safe MAME playback file planning."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from tools.mame_playback_plan import (
    playback_plan, confirm_playback_unchanged, read_header,
    MAX_INPUT_BYTES, HEADER_BYTES, MAGIC,
)


def fake_inp(system='dino', *, major=3, minor=0,
             payload=b'local synthetic test input'):
    """Header fixture, not a genuine recorded game session."""
    header = bytearray(HEADER_BYTES)
    header[:8] = MAGIC
    header[0x10] = major
    header[0x11] = minor
    header[0x14:0x20] = system.encode('ascii').ljust(12, b'\0')
    header[0x20:0x40] = b'test fake MAME stub'.ljust(32, b'\0')
    return bytes(header) + payload


class PlaybackPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'first-stage.inp'
        self.data = fake_inp()
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
        self.assertEqual(report['system'], 'dino')
        self.assertEqual(report['format_major'], 3)
        self.assertEqual(report['format_minor'], 0)
        self.assertTrue(report['header_validated'])
        self.assertNotIn(str(self.path), str(report))
        self.assertNotIn('synthetic test input', str(report))

    def test_detect_change_after_initial_check(self):
        _, report = playback_plan(self.path)
        self.assertTrue(confirm_playback_unchanged(self.path, report))
        self.path.write_bytes(self.data.replace(b'local', b'other'))
        self.assertFalse(confirm_playback_unchanged(self.path, report))

    def test_reject_wrong_system_game_id(self):
        self.path.write_bytes(fake_inp(system='sf2'))
        with self.assertRaisesRegex(ValueError,'different system'):
            playback_plan(self.path)

    def test_reject_unsupported_mame_major_version(self):
        self.path.write_bytes(fake_inp(major=2))
        with self.assertRaisesRegex(ValueError,'major version'):
            playback_plan(self.path)

    def test_reject_arbitrary_non_inp_payload(self):
        self.path.write_bytes(b'fake MAME data ' * 9)
        with self.assertRaisesRegex(ValueError,'magic'):
            playback_plan(self.path)

    def test_reject_header_without_replay_payload(self):
        self.path.write_bytes(fake_inp(payload=b''))
        with self.assertRaisesRegex(ValueError,'header'):
            playback_plan(self.path)

    def test_record_minor_version_without_claiming_replay_success(self):
        self.path.write_bytes(fake_inp(minor=2))
        _, report=playback_plan(self.path)
        self.assertEqual(report['format_minor'],2)
        self.assertFalse(report['input_replay_verified'])

    def test_reject_truncated_header(self):
        with self.assertRaisesRegex(ValueError,'64-byte header'):
            read_header(b'MAMEINP\0')

    def test_replaced_corrupt_replay_is_marked_changed(self):
        _, metadata=playback_plan(self.path)
        self.path.write_bytes(b'X'*100)
        self.assertFalse(confirm_playback_unchanged(self.path,metadata))

    def test_deleted_recording_is_detected_as_changed(self):
        _, metadata = playback_plan(self.path)
        self.path.unlink()
        self.assertFalse(confirm_playback_unchanged(self.path,metadata))

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
