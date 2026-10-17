"""Synthetic-only tests for the opt-in local original-ROM payload CRC gate."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile
import zlib

from tools import mame_private_rom_payload_audit as audit


class PrivateDinoPayloadAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.game_data = {
            'fake-program.bin': b'ROM-FREE-TEST-ABC' * 4,
            'fake-graphics.bin': bytes(range(16)) * 7,
        }
        self.device_data = {'fake-qsound.bin': b'SYNTHETIC-SOUND-DATA'}
        self.game_catalog = {
            n: (len(data), zlib.crc32(data)) for n, data in self.game_data.items()
        }
        self.sound_header = (
            len(self.device_data['fake-qsound.bin']),
            zlib.crc32(self.device_data['fake-qsound.bin']))
        self._make_zip('dino.zip', self.game_data)
        self._make_zip('qsound_hle.zip', self.device_data)

    def _make_zip(self, name, entries):
        with zipfile.ZipFile(self.root / name, 'w',
                             compression=zipfile.ZIP_STORED) as out:
            for member, value in entries.items():
                out.writestr(member, value)

    def _audit(self, **kwargs):
        with patch.object(audit, 'EXPECTED', self.game_catalog), \
             patch.object(audit, 'DEVICE_MEMBER', 'fake-qsound.bin'), \
             patch.object(audit, 'DEVICE_HEADER', self.sound_header):
            return audit.audit_private_dino_rom_payloads(
                self.root, allow_private_reads=True, **kwargs)

    def test_explicit_consent_is_required_before_opening_any_rom(self):
        with patch.object(audit, '_catalog_payload_check',
                          side_effect=AssertionError('private reads forbidden')):
            with self.assertRaisesRegex(ValueError, 'Explicit private'):
                audit.audit_private_dino_rom_payloads(self.root)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = audit.main(['--rom-dir', str(self.root)])
        self.assertEqual(exit_code, 2)
        self.assertEqual(json.loads(stderr.getvalue())['status'],
                         'PRIVATE_DINO_ROM_PAYLOAD_CRC_AUDIT_REFUSED')
        self.assertNotIn(str(self.root), stderr.getvalue())

    def test_owned_synthetic_payloads_match_without_mame_authentication(self):
        result = self._audit()
        self.assertEqual(result['status'],
                         'PRIVATE_DINO_ROM_PAYLOAD_CRC_CATALOG_MATCH_ONLY')
        self.assertEqual(result['expected_member_count'], 3)
        self.assertEqual(result['payload_catalog_verified_count'], 3)
        self.assertEqual(result['mismatching_member_count'], 0)
        self.assertEqual(result['missing_member_count'], 0)
        self.assertTrue(result['private_payload_bytes_read_locally'])
        self.assertTrue(result['private_payload_crc_matches_pinned_catalog'])
        for key in ('mame_verifyroms_executed', 'original_game_authenticity_verified',
                    'gameplay_executed', 'pixel_parity_eligible'):
            self.assertFalse(result[key])
        report = json.dumps(result)
        self.assertNotIn(str(self.root), report)
        self.assertNotIn('fake-program.bin', report)
        self.assertNotIn('fake-qsound.bin', report)
        self.assertNotIn('SYNTHETIC', report)
        self.assertNotIn(str(self.game_catalog['fake-program.bin'][1]), report)

    def test_missing_device_is_a_mismatch_not_a_mame_pass(self):
        (self.root / 'qsound_hle.zip').unlink()
        out = self._audit()
        self.assertEqual(out['payload_catalog_verified_count'], 2)
        self.assertEqual(out['missing_member_count'], 1)
        self.assertFalse(out['private_payload_crc_matches_pinned_catalog'])
        self.assertEqual(out['status'],
                         'PRIVATE_DINO_ROM_PAYLOAD_CRC_CATALOG_MISMATCH')

    def test_catalog_crc_disagreement_does_not_claim_verified_payload(self):
        broken = dict(self.game_catalog)
        size, crc = broken['fake-program.bin']
        broken['fake-program.bin'] = (size, crc ^ 1)
        self.game_catalog = broken
        out = self._audit()
        self.assertEqual(out['payload_catalog_verified_count'], 2)
        self.assertEqual(out['mismatching_member_count'], 1)
        self.assertFalse(out['private_payload_crc_matches_pinned_catalog'])

    def test_catalog_length_disagreement_is_bounded(self):
        broken = dict(self.game_catalog)
        size, crc = broken['fake-program.bin']
        broken['fake-program.bin'] = (size - 1, crc)
        self.game_catalog = broken
        out = self._audit()
        self.assertEqual(out['mismatching_member_count'], 1)
        self.assertEqual(out['payload_catalog_verified_count'], 2)

    def test_actual_payload_corruption_is_refused_even_with_old_zip_crc(self):
        path = self.root / 'dino.zip'
        with zipfile.ZipFile(path) as arc:
            item = arc.getinfo('fake-program.bin')
        # Test ZIP_STORED local-file header, leaving central-directory
        # size/CRC and member name untouched while corrupting raw payload.
        contents = bytearray(path.read_bytes())
        import struct
        name_len, extra_len = struct.unpack_from(
            '<HH', contents, item.header_offset + 26)
        index = item.header_offset + 30 + name_len + extra_len
        contents[index] ^= 0x01
        path.write_bytes(contents)
        with self.assertRaises(zipfile.BadZipFile):
            self._audit()
        text = io.StringIO()
        with contextlib.redirect_stderr(text):
            self.assertEqual(audit.main([
                '--rom-dir', str(self.root),
                '--verify-private-payloads']), 2)
        refusal = json.loads(text.getvalue())
        self.assertEqual(refusal['status'],
                         'PRIVATE_DINO_ROM_PAYLOAD_CRC_AUDIT_REFUSED')
        self.assertFalse(refusal['original_rom_bytes_or_digests_in_report'])
        self.assertNotIn(str(self.root), text.getvalue())

    def test_duplicate_zip_member_and_path_traversal_fail_closed(self):
        self._make_zip('dino.zip', self.game_data)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.root / 'dino.zip', 'a') as arc:
                arc.writestr('fake-program.bin', b'DUPLICATE')
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            self._audit()
        self._make_zip('dino.zip', self.game_data)
        with zipfile.ZipFile(self.root / 'dino.zip', 'a') as arc:
            arc.writestr('../private.bin', b'NEVER-EXTRACT')
        with self.assertRaisesRegex(ValueError, 'unsafe'):
            self._audit()

    def test_symlink_and_hardlink_archives_are_refused(self):
        game = self.root / 'dino.zip'
        saved = self.root / 'backing.zip'
        game.rename(saved)
        game.symlink_to(saved)
        with self.assertRaises(ValueError):
            self._audit()
        game.unlink()
        os.link(saved, game)
        with self.assertRaises(ValueError):
            self._audit()

    def test_excessively_large_catalog_member_is_refused(self):
        broken = dict(self.game_catalog)
        broken['fake-program.bin'] = (audit.MAX_MEMBER_BYTES + 1, 0)
        self.game_catalog = broken
        with self.assertRaisesRegex(ValueError, 'size'):
            self._audit()

    def test_exact_one_byte_extra_or_missing_is_mismatch(self):
        bad = dict(self.game_data)
        bad['fake-program.bin'] += b'X'
        self._make_zip('dino.zip', bad)
        out = self._audit()
        self.assertEqual(out['mismatching_member_count'], 1)
        self.assertFalse(out['private_payload_crc_matches_pinned_catalog'])


if __name__ == '__main__':
    unittest.main()
