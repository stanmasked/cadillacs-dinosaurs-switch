"""ROM-free tests for local-only MAME dino/QSound dependency triage.

All ZIP metadata is fabricated; no actual original game payload is needed.
"""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipInfo

from tools.verify_rom import EXPECTED
from tools.mame_private_rom_blocker_triage import (
    triage_private_dino_rom_blockers, main,
)


class PrivateDinoRomBlockerTriageTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'dino.zip').write_bytes(b'FABRICATED_NOT_ROM_ZIP_CONTENT')
        self.device = self.root / 'qsound_hle.zip'

    def headers(self, *, missing=(), changes=None):
        records = {}
        for name, (size, crc) in EXPECTED.items():
            if name in missing:
                continue
            value = changes.get(name) if changes else None
            if value is None:
                value = size, crc
            item = ZipInfo(name)
            item.file_size, item.CRC = value
            records[name] = item
        return list(records.values())

    def device_headers(self, *, has_member=True):
        if not has_member:
            name = 'FABRICATED_NOT_QSOUND_MEMBER.bin'
        else:
            name = 'dl-1425.bin'
        item = ZipInfo(name)
        item.file_size = 17
        item.CRC = 1234
        return [item]

    def run_fake(self, *, game=None, device=None, add_device=True):
        if add_device:
            self.device.write_bytes(b'FAKE_QSOUND_TEST')
        mapping = {
            'dino.zip': self.headers() if game is None else game,
            'qsound_hle.zip': self.device_headers() if device is None else device,
        }

        class FakeZip:
            def __init__(self, name, mode):
                self.name = Path(name).name
                self.mode = mode
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def infolist(self):
                return mapping[self.name]

        with patch(
                'tools.mame_private_rom_blocker_triage.zipfile.ZipFile',
                side_effect=FakeZip):
            return triage_private_dino_rom_blockers(self.root)

    def test_complete_synthetic_catalog_never_claims_mame_verified(self):
        out = self.run_fake()
        self.assertEqual(out['status'],
                         'PRIVATE_KNOWN_MAME_ROM_BLOCKERS_NOT_OBSERVED_METADATA_ONLY')
        self.assertEqual(out['game_catalog_expected_entries'], 28)
        self.assertEqual(out['game_catalog_matching_headers'], 28)
        self.assertEqual(out['game_catalog_missing_entries'], 0)
        self.assertEqual(out['game_catalog_mismatching_headers'], 0)
        self.assertTrue(out['pld_catalog_header_matches'])
        self.assertTrue(out['qsound_hle_device_member_observed'])
        self.assertEqual(out['next_local_action_code'],
                         'RUN_GENUINE_LOCAL_MAME_VERIFYROMS')
        self.assertFalse(out['mame_verifyroms_executed'])
        self.assertFalse(out['gameplay_executed'])
        self.assertFalse(out['rom_payload_crc_independently_verified'])
        self.assertFalse(out['individual_game_rom_payload_bytes_read'])

    def test_original_pld_shaped_mismatch_and_missing_hle_isolated(self):
        out = self.run_fake(
            game=self.headers(changes={'ioc1.ic1': (279, 0x0d182081)}),
            add_device=False)
        self.assertEqual(out['game_catalog_matching_headers'], 27)
        self.assertEqual(out['game_catalog_mismatching_headers'], 1)
        self.assertFalse(out['pld_catalog_header_matches'])
        self.assertFalse(out['other_game_catalog_issues_observed'])
        self.assertFalse(out['separate_qsound_hle_archive_observed'])
        self.assertFalse(out['qsound_hle_device_member_observed'])
        self.assertEqual(out['next_local_action_code'],
                         'REVIEW_PRIVATE_PLD_AND_QSOUND_DEPENDENCIES')
        self.assertTrue(out['known_dependency_layout_requires_attention'])

    def test_pld_only_and_missing_sound_only_are_distinct(self):
        pld = self.run_fake(
            game=self.headers(missing={'ioc1.ic1'}))
        self.assertEqual(pld['game_catalog_missing_entries'], 1)
        self.assertEqual(pld['next_local_action_code'],
                         'REVIEW_PRIVATE_PLD_CATALOG_ENTRY')
        sound = self.run_fake(device=self.device_headers(has_member=False))
        self.assertTrue(sound['pld_catalog_header_matches'])
        self.assertTrue(sound['separate_qsound_hle_archive_observed'])
        self.assertFalse(sound['qsound_hle_device_member_observed'])
        self.assertEqual(sound['next_local_action_code'],
                         'CHECK_PRIVATE_QSOUND_DEVICE_ARCHIVE')

    def test_non_pld_program_issue_is_not_mislabeled_as_pld_only(self):
        out = self.run_fake(game=self.headers(
            changes={'cde_22a.7f': (524288, 0)}))
        self.assertTrue(out['pld_catalog_header_matches'])
        self.assertTrue(out['other_game_catalog_issues_observed'])
        self.assertEqual(out['game_catalog_mismatching_headers'], 1)
        self.assertEqual(out['next_local_action_code'],
                         'REVIEW_PRIVATE_GAME_CATALOG_THEN_LOCAL_MAME_VERIFYROMS')

    def test_real_tiny_synthetic_zip_headers_need_no_member_reads(self):
        # Exercise stdlib ZIP directory parsing, not just mocked ZipInfo.
        import zipfile
        (self.root / 'dino.zip').unlink()
        with zipfile.ZipFile(self.root / 'dino.zip', 'w') as out:
            out.writestr('ioc1.ic1', b'NOT_ORIGINAL_GAME_ROM')
        with zipfile.ZipFile(self.device, 'w') as out:
            out.writestr('dl-1425.bin', b'NOT_ORIGINAL_QSOUND_ROM')
        with patch.object(zipfile.ZipFile, 'open',
                          side_effect=AssertionError('ROM member payload opened')):
            report = triage_private_dino_rom_blockers(self.root)
        self.assertEqual(report['game_catalog_matching_headers'], 0)
        self.assertEqual(report['game_catalog_missing_entries'], 27)
        self.assertEqual(report['game_catalog_mismatching_headers'], 1)
        self.assertTrue(report['qsound_hle_device_member_observed'])
        self.assertFalse(report['rom_payload_crc_independently_verified'])
        self.assertFalse(report['individual_game_rom_payload_bytes_read'])

    def test_missing_game_or_symlink_is_refused(self):
        (self.root / 'dino.zip').unlink()
        with self.assertRaises(ValueError):
            triage_private_dino_rom_blockers(self.root)
        target = self.root / 'target'
        target.write_bytes(b'SYNTHETIC')
        (self.root / 'dino.zip').symlink_to(target)
        with self.assertRaises(ValueError):
            triage_private_dino_rom_blockers(self.root)

    def test_hardlink_to_existing_game_archive_is_refused(self):
        original = self.root / 'dino.zip'
        os.link(original, self.root / 'another-name')
        with self.assertRaises(ValueError):
            triage_private_dino_rom_blockers(self.root)

    def test_duplicate_and_nested_zip_directory_entries_are_refused(self):
        for additions in (
            [self.headers()[0]],
            [ZipInfo('nested/private.bin')],
            [ZipInfo('../private.bin')],
            [ZipInfo('subdir/')],
        ):
            fake = self.headers() + additions
            fake[-1].file_size = max(1, fake[-1].file_size)
            with self.subTest(additions=additions[-1].filename):
                with self.assertRaises(ValueError):
                    self.run_fake(game=fake)

    def test_excessive_zip_headers_are_refused(self):
        entries = self.headers()
        for i in range(140):
            item = ZipInfo('FAKE_SYNTHETIC_EXTRA_%03d' % i)
            item.file_size = 1
            entries.append(item)
        with self.assertRaises(ValueError):
            self.run_fake(game=entries)

    def test_corrupt_private_zip_returns_only_fixed_cli_refusal(self):
        text = io.StringIO()
        with contextlib.redirect_stderr(text):
            ret = main(['--rom-dir', str(self.root)])
        self.assertEqual(ret, 2)
        payload = json.loads(text.getvalue())
        self.assertEqual(payload['status'],
                         'PRIVATE_DINO_ROM_BLOCKER_TRIAGE_REFUSED')
        self.assertFalse(payload['individual_game_rom_payload_bytes_read'])
        self.assertNotIn(str(self.root), text.getvalue())
        self.assertNotIn('dino.zip', text.getvalue())

    def test_private_paths_names_crc_never_appear_in_success_schema(self):
        self.device.write_bytes(b'SENSITIVE_FAKE_SECRET')
        out = self.run_fake(game=self.headers(changes={
            'ioc1.ic1': (279, 0x0d182081),
        }))
        report = json.dumps(out, sort_keys=True)
        self.assertNotIn(str(self.root), report)
        self.assertNotIn('ioc1.ic1', report)
        self.assertNotIn('qsound_hle.zip', report)
        self.assertNotIn('dl-1425.bin', report)
        self.assertNotIn('0d182081', report)
        self.assertNotIn('SENSITIVE_FAKE_SECRET', report)
        self.assertFalse(out['private_paths_names_and_digests_in_report'])


if __name__ == '__main__':
    unittest.main()
