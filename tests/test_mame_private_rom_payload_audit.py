"""Synthetic-only tests for the opt-in local original-ROM payload CRC gate."""
import contextlib
import hashlib
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
        self.sound_sha1 = hashlib.sha1(self.device_data['fake-qsound.bin']).digest()
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
             patch.object(audit, 'DEVICE_HEADER', self.sound_header), \
             patch.object(audit, 'DEVICE_SHA1', self.sound_sha1):
            return audit.audit_private_dino_rom_payloads(
                self.root, allow_private_reads=True, **kwargs)

    def test_private_archive_location_must_not_overlap_public_checkout(self):
        source = self.root / 'public-project'
        source.mkdir()
        # ROM directory equal to project root; project is within ROM
        # directory; ROM directory is within project root.
        inner = source / 'private-roms'
        inner.mkdir()
        for project_root, roms in (
            (self.root, self.root),
            (source, self.root),
            (self.root, inner),
        ):
            with self.subTest(project_root=project_root, roms=roms), \
                 patch.object(audit, 'PROJECT_ROOT', project_root), \
                 patch.object(audit, '_catalog_payload_check',
                              side_effect=AssertionError('ROM read forbidden')) as scan:
                with self.assertRaisesRegex(ValueError,
                                            'outside the project tree'):
                    audit.audit_private_dino_rom_payloads(
                        roms, allow_private_reads=True)
                scan.assert_not_called()

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

    def test_opt_in_refusal_does_not_falsely_claim_no_rom_read(self):
        # A failure after the dino archive was processed has ambiguous
        # partial-read history. Preserve the fact that permission was given.
        error = io.StringIO()
        original = audit._catalog_payload_check

        def fail_after_first_zip(path, catalog):
            if path.name == 'qsound_hle.zip':
                raise OSError('PRIVATE_LOCAL_PATH_AND_SECRET_DATA')
            return original(path, catalog)

        with patch.object(audit, 'EXPECTED', self.game_catalog), \
             patch.object(audit, 'DEVICE_MEMBER', 'fake-qsound.bin'), \
             patch.object(audit, 'DEVICE_HEADER', self.sound_header), \
             patch.object(audit, '_catalog_payload_check',
                          side_effect=fail_after_first_zip), \
             contextlib.redirect_stderr(error):
            code = audit.main([
                '--rom-dir', str(self.root), '--verify-private-payloads'])
        self.assertEqual(code, 2)
        refusal = json.loads(error.getvalue())
        self.assertEqual(refusal['status'],
                         'PRIVATE_DINO_ROM_PAYLOAD_CRC_AUDIT_REFUSED')
        self.assertTrue(refusal['explicit_private_payload_read_authorized'])
        self.assertIsNone(refusal['private_payload_bytes_read_locally'])
        self.assertTrue(refusal['private_payload_bytes_may_have_been_read_locally'])
        self.assertFalse(refusal['private_payload_read_completion_verified'])
        self.assertFalse(refusal['private_payload_crc_matches_pinned_catalog'])
        self.assertNotIn(str(self.root), error.getvalue())
        self.assertNotIn('PRIVATE_LOCAL_PATH_AND_SECRET_DATA', error.getvalue())

    def test_permission_refusal_still_confirms_no_private_reads(self):
        error = io.StringIO()
        with patch.object(audit, '_catalog_payload_check',
                          side_effect=AssertionError('must never read')) as reader, \
             contextlib.redirect_stderr(error):
            code = audit.main(['--rom-dir', str(self.root)])
        self.assertEqual(code, 2)
        reader.assert_not_called()
        refusal = json.loads(error.getvalue())
        self.assertFalse(refusal['explicit_private_payload_read_authorized'])
        self.assertFalse(refusal['private_payload_bytes_read_locally'])
        self.assertFalse(refusal['private_payload_bytes_may_have_been_read_locally'])
        self.assertFalse(refusal['private_payload_read_completion_verified'])

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
        self.assertTrue(result['qsound_sha1_checked_locally'])
        self.assertTrue(result['qsound_sha1_matches_pinned_mame_catalog'])
        for key in ('mame_verifyroms_executed', 'original_game_authenticity_verified',
                    'gameplay_executed', 'pixel_parity_eligible'):
            self.assertFalse(result[key])
        report = json.dumps(result)
        self.assertNotIn(str(self.root), report)
        self.assertNotIn('fake-program.bin', report)
        self.assertNotIn('fake-qsound.bin', report)
        self.assertNotIn('SYNTHETIC', report)
        self.assertNotIn(str(self.game_catalog['fake-program.bin'][1]), report)

    def test_qsound_sha1_mismatch_rejected_despite_valid_crc_headers(self):
        # Independently reject a wrong pinned SHA-1 even though all ZIP
        # headers and streamed CRC32 values match the synthetic catalog.
        with patch.object(audit, 'DEVICE_SHA1', bytes(20)), \
             patch.object(audit, 'EXPECTED', self.game_catalog), \
             patch.object(audit, 'DEVICE_MEMBER', 'fake-qsound.bin'), \
             patch.object(audit, 'DEVICE_HEADER', self.sound_header):
            result = audit.audit_private_dino_rom_payloads(
                self.root, allow_private_reads=True)
        self.assertEqual(result['payload_catalog_verified_count'], 2)
        self.assertEqual(result['mismatching_member_count'], 1)
        self.assertTrue(result['qsound_sha1_checked_locally'])
        self.assertFalse(result['qsound_sha1_matches_pinned_mame_catalog'])
        self.assertFalse(result['private_payload_crc_matches_pinned_catalog'])
        self.assertEqual(result['status'],
                         'PRIVATE_DINO_ROM_PAYLOAD_CRC_CATALOG_MISMATCH')

    def test_invalid_qsound_sha1_catalog_refused_before_rom_reads(self):
        game = self.root / 'qsound_hle.zip'
        for invalid in ('not-bytes', b'x' * 19, b'x' * 21):
            with self.subTest(invalid=invalid), \
                 patch.object(audit, '_open_stable_private_zip',
                              side_effect=AssertionError('must not open ZIP')) as opener:
                with self.assertRaisesRegex(ValueError, 'SHA1 catalog invalid'):
                    audit._catalog_payload_check(
                        game, {'fake-qsound.bin': self.sound_header},
                        sha1_catalog={'fake-qsound.bin': invalid})
                opener.assert_not_called()

    def test_missing_device_is_a_mismatch_not_a_mame_pass(self):
        (self.root / 'qsound_hle.zip').unlink()
        out = self._audit()
        self.assertEqual(out['payload_catalog_verified_count'], 2)
        self.assertEqual(out['missing_member_count'], 1)
        self.assertFalse(out['private_payload_crc_matches_pinned_catalog'])
        self.assertFalse(out['qsound_sha1_checked_locally'])
        self.assertFalse(out['qsound_sha1_matches_pinned_mame_catalog'])
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
        # CLI must see the same synthetic catalog as the direct call;
        # otherwise a mismatch against the genuine 28-file catalog
        # prevents the deliberately corrupted member from being opened.
        # Assert the payload was actually opened in this CLI invocation.
        text = io.StringIO()
        original_member_open = zipfile.ZipFile.open
        with patch.object(audit, 'EXPECTED', self.game_catalog), \
             patch.object(audit, 'DEVICE_MEMBER', 'fake-qsound.bin'), \
             patch.object(audit, 'DEVICE_HEADER', self.sound_header), \
             patch.object(audit, 'DEVICE_SHA1', self.sound_sha1), \
             patch.object(zipfile.ZipFile, 'open', autospec=True,
                          side_effect=original_member_open) as member_open, \
             contextlib.redirect_stderr(text):
            self.assertEqual(audit.main([
                '--rom-dir', str(self.root),
                '--verify-private-payloads']), 2)
        self.assertGreater(member_open.call_count, 0)
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

    def test_first_archive_changed_during_device_scan_refuses_result(self):
        original = audit._catalog_payload_check

        def mutate_first_during_second(path, catalog, **kwargs):
            counts = original(path, catalog, **kwargs)
            if path.name == 'qsound_hle.zip':
                # Each per-file scan has finished; only the pair-wide
                # follow-up gate can catch this later first-ZIP change.
                with (self.root / 'dino.zip').open('ab') as target:
                    target.write(b'FABRICATED_TRAILER')
            return counts

        with patch.object(audit, '_catalog_payload_check',
                          side_effect=mutate_first_during_second):
            with self.assertRaisesRegex(ValueError, 'paired ROM archives changed'):
                self._audit()

    def test_second_archive_swapped_after_game_scan_is_detected(self):
        original = audit._catalog_payload_check

        def swap_device_between_scans(path, catalog, **kwargs):
            counts = original(path, catalog, **kwargs)
            if path.name == 'dino.zip':
                previous = self.root / 'qsound_hle.zip'
                replacement = self.root / 'synthetic-replacement.zip'
                replacement.write_bytes(previous.read_bytes())
                replacement.replace(previous)
            return counts

        with patch.object(audit, '_catalog_payload_check',
                          side_effect=swap_device_between_scans):
            with self.assertRaisesRegex(ValueError, 'paired ROM archives changed'):
                self._audit()

    def test_symlinked_device_is_refused_before_any_payload_scan(self):
        device = self.root / 'qsound_hle.zip'
        backing = self.root / 'synthetic-device.zip'
        device.rename(backing)
        device.symlink_to(backing)
        with patch.object(audit, '_catalog_payload_check',
                          side_effect=AssertionError('must not read a ROM')) as read:
            with self.assertRaisesRegex(ValueError, 'pair entry unsafe'):
                self._audit()
        read.assert_not_called()

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
