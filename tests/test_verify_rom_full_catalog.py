"""ROM-free tests: full 28-entry dino World 930201 ZIP catalog validation."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from tools.verify_rom import EXPECTED, verify


class FullDinoRomCatalogTests(unittest.TestCase):
    def test_expected_catalog_includes_plds_and_primary_regions(self):
        self.assertEqual(len(EXPECTED), 28)
        self.assertEqual(EXPECTED['ioc1.ic1'], (260, 0xa399772d))
        self.assertEqual(EXPECTED['cde_21a.6f'], (524288, 0x66d23de2))
        self.assertEqual(EXPECTED['cd_q.5k'], (131072, 0x605fdb0b))
        self.assertEqual(EXPECTED['rom1'], (279, 0x41dc73b9))

    def fake_zip(self, *, overrides=None, missing=()):
        records = {}
        for name, (size, crc) in EXPECTED.items():
            if name in missing:
                continue
            value = overrides.get(name) if overrides else None
            if value is None:
                value = size, crc
            zi = ZipInfo(name)
            zi.file_size, zi.CRC = value
            records[name] = zi
        return records

    def run_catalog(self, records):
        output = io.StringIO()
        class FakeZip:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def getinfo(self, name):
                if name not in records:
                    raise KeyError(name)
                return records[name]
        with patch('tools.verify_rom.zipfile.ZipFile', return_value=FakeZip()), \
             contextlib.redirect_stdout(output):
            status = verify('synthetic-do-not-read.zip')
        return status, output.getvalue()

    def test_complete_synthetic_matching_zip_catalog_is_only_metadata_match(self):
        status, printed = self.run_catalog(self.fake_zip())
        self.assertEqual(status, 0)
        self.assertEqual(printed.count('OK '), 28)
        self.assertIn('MATCH_ONLY_NOT_MAME_VERIFIED', printed)
        self.assertNotIn('ROM audit: PASS', printed)

    def test_known_ioc1_279_byte_crc_mismatch_is_detected(self):
        entries = self.fake_zip(overrides={
            'ioc1.ic1': (279, 0x0d182081),
        })
        status, printed = self.run_catalog(entries)
        self.assertEqual(status, 1)
        self.assertEqual(printed.count('OK '), 27)
        self.assertIn('FAIL ioc1.ic1', printed)
        self.assertIn('MISMATCH', printed)

    def test_missing_pld_fails_even_with_complete_graphics_and_program(self):
        status, printed = self.run_catalog(
            self.fake_zip(missing={'ioc1.ic1', 'rom1'}))
        self.assertEqual(status, 1)
        self.assertIn('MISSING ioc1.ic1', printed)
        self.assertIn('MISSING rom1', printed)

    def test_changed_program_crc_cannot_be_confused_with_pld_mismatch(self):
        status, printed = self.run_catalog(
            self.fake_zip(overrides={'cde_22a.7f': (524288, 0)}))
        self.assertEqual(status, 1)
        self.assertIn('FAIL cde_22a.7f', printed)
        self.assertIn('MISMATCH', printed)


if __name__ == '__main__':
    unittest.main()
