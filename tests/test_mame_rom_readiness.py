"""ROM-free tests for dino MAME readiness; no actual arcade ROM bytes."""
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from tools.mame_rom_readiness import CORE, ARCHIVAL_PLD, QSOUND_HLE, audit_zip, audit, main


def makezip(path, files):
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        for name, data in files.items():
            z.writestr(name, data)


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root / 'dino.zip'
        makezip(self.game, {'program.bin': b'abc', 'gfx.bin': b'xyz'})

    def test_known_core_and_device_contract(self):
        self.assertEqual(len(CORE), 16)
        self.assertEqual(len(ARCHIVAL_PLD), 12)
        self.assertEqual(QSOUND_HLE['dl-1425.bin'], (8192, 0xd6cf5ef5))
        self.assertEqual(CORE['cd-1m.3a'], (524288, 0x8da4f917))

    def test_crc_and_size_matching_with_synthetic_fixture(self):
        expected = {'program.bin': (3, 0x352441c2), 'gfx.bin': (3, 0xeb8eba67)}
        report = audit_zip(self.game, expected)
        self.assertEqual(report['matching_count'], 2)
        self.assertEqual(report['mismatches'], [])
        self.assertEqual(report['missing_names'], [])

    def test_warning_on_crc_difference_without_invented_good_data(self):
        expected = {'program.bin': (3, 0), 'gfx.bin': (4, 0xeb8eba67),
                    'absent.bin': (2, 0xabcdef01)}
        report = audit_zip(self.game, expected)
        self.assertEqual(report['matching_count'], 0)
        self.assertEqual(len(report['mismatches']), 2)
        self.assertEqual(report['missing_names'], ['absent.bin'])

    def test_missing_device_is_not_mislabeled_game_corruption(self):
        report = audit(self.game, None)
        self.assertEqual(report['qsound_hle']['status'], 'not_supplied')
        self.assertFalse(report['main_cpu_gfx_sound_roms_verified'])
        self.assertFalse(report['game_boot_verified'])
        self.assertFalse(report['modern_mame_rom_prerequisites_verified'])

    def test_device_archive_separate_check(self):
        p = self.root / 'qsound_hle.zip'
        makezip(p, {'dl-1425.bin': b'0' * 8192})
        report = audit(self.game, p)
        self.assertEqual(report['qsound_hle']['status'], 'invalid')
        self.assertEqual(report['qsound_hle']['roms']['matching_count'], 0)

    def test_block_path_traversal_and_duplicate_names(self):
        for names in ({'../bad': b'x'}, {'folder/nested': b'x'}):
            makezip(self.game, names)
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                audit_zip(self.game, {})
        with ZipFile(self.game, 'w') as z:
            z.writestr('duplicate', b'x')
            z.writestr('duplicate', b'y')
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            audit_zip(self.game, {})

    def test_reject_zip_bomb_metadata_size(self):
        makezip(self.game, {'big': b'x' * (32 * 1024 * 1024 + 1)})
        with self.assertRaisesRegex(ValueError, 'Unsafe|limit'):
            audit_zip(self.game, {})

    def test_invalid_archive_is_rejected(self):
        self.game.write_bytes(b'not-a-zip')
        with self.assertRaises(Exception):
            audit(self.game)

    def test_command_line_report_without_payload(self):
        out = self.root / 'report.json'
        self.assertEqual(main([str(self.game), '--out', str(out)]), 1)
        report = json.loads(out.read_text())
        self.assertEqual(report['game'], 'dino')
        self.assertFalse(report['capture_achieved'])
        self.assertNotIn('program.bin', json.dumps(report))
        self.assertEqual(main([str(self.game), '--out', str(out)]), 2)

    def test_name_and_crc_expectations_do_not_depend_on_zip_order(self):
        makezip(self.game, {'second': b'def', 'first': b'abc'})
        self.assertEqual(audit_zip(
            self.game, {'first': (3, 0x352441c2)})['matching_count'], 1)


if __name__ == '__main__':
    unittest.main()
