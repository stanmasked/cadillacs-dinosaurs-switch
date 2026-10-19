"""ROM-free file-set and TOCTOU guard regressions for private MAME captures."""
import json
import os
from pathlib import Path
import tempfile
import unittest

from tools.mame_obj_latch_evidence import obj_fnv1a64
from tools.mame_private_capture_stability import (
    EXPECTED_SIZES, private_capture_file_snapshot,
    require_stable_private_capture,
)
from test_mame_obj_cli_end_to_end import make_capture


class PrivateCaptureStabilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'cps1-captures'
        self.root.mkdir()
        make_capture(self.root)
        for i in range(6):
            stem = f'frame-{900 + i*2:08d}'
            obj = (self.root / f'{stem}.buffered-obj-be.bin').read_bytes()
            (self.root / f'{stem}.obj-latch-count.txt').write_text(
                f'CPS1_DINO_LATCH_V2 {20+i*2} {obj_fnv1a64(obj)}\n')
        self.target = self.root / 'frame-00000904.reference-rgb24.bin'

    def test_54_exact_files_can_be_hashed_twice_without_exporting_digests(self):
        snapshot = private_capture_file_snapshot(self.root)
        self.assertEqual(len(snapshot), 54)
        self.assertEqual(len(EXPECTED_SIZES), 9)
        result = require_stable_private_capture(self.root, snapshot)
        self.assertEqual(result['source_files_checked'], 54)
        self.assertTrue(result['source_files_unchanged_during_audit'])
        self.assertFalse(result['frame_sync_verified'])
        self.assertFalse(result['real_game_authenticity_verified'])
        serialized = json.dumps(result)
        for entry in snapshot.values():
            self.assertNotIn(entry[-1].hex(), serialized)

    def test_same_size_byte_edit_between_checks_refuses_publication(self):
        before = private_capture_file_snapshot(self.root)
        data = bytearray(self.target.read_bytes())
        data[111] ^= 0x80
        self.target.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'changed during the audit'):
            require_stable_private_capture(self.root, before)

    def test_changed_manifest_is_detected_even_if_it_remains_valid_json(self):
        before = private_capture_file_snapshot(self.root)
        manifest = self.root / 'frame-00000904.manifest.json'
        data = json.loads(manifest.read_text())
        data['warning'] = 'locally changed after the game finished'
        manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'changed during the audit'):
            require_stable_private_capture(self.root, before)

    def test_added_or_removed_unexpected_files_refuse_complete_snapshot(self):
        before = private_capture_file_snapshot(self.root)
        extra = self.root / 'frame-00000900.original-game.png'
        extra.write_bytes(b'\x89PNG')
        with self.assertRaisesRegex(ValueError, 'missing or unexpected'):
            private_capture_file_snapshot(self.root)
        extra.unlink()
        self.target.unlink()
        with self.assertRaisesRegex(ValueError, 'missing or unexpected'):
            require_stable_private_capture(self.root, before)

    def test_symlink_capture_rejected_without_following_target(self):
        source = self.target
        source.unlink()
        source.symlink_to(self.root / 'frame-00000900.reference-rgb24.bin')
        with self.assertRaisesRegex(ValueError, 'nonregular or linked'):
            private_capture_file_snapshot(self.root)

    def test_hardlinked_capture_refused_even_if_bytes_are_identical(self):
        with tempfile.TemporaryDirectory() as outside:
            external = Path(outside) / 'private-reference.bin'
            external.write_bytes(self.target.read_bytes())
            self.target.unlink()
            os.link(external, self.target)
            with self.assertRaisesRegex(ValueError, 'nonregular or linked'):
                private_capture_file_snapshot(self.root)

    def test_same_bytes_with_replaced_inode_are_rejected(self):
        before = private_capture_file_snapshot(self.root)
        data = self.target.read_bytes()
        old_path = self.root.parent / 'kept-old-frame.bin'
        self.target.rename(old_path)  # old inode remains allocated
        self.target.write_bytes(data)
        with self.assertRaisesRegex(ValueError, 'changed during the audit'):
            require_stable_private_capture(self.root, before)

    def test_zero_truncated_or_oversized_components_are_rejected(self):
        length = self.target.stat().st_size
        for value in (b'', b'\x00' * 10, b'\x00' * (length + 1)):
            with self.subTest(size=len(value)):
                self.target.write_bytes(value)
                with self.assertRaisesRegex(ValueError, 'size is invalid'):
                    private_capture_file_snapshot(self.root)

    def test_variable_length_manifest_and_latch_sidecar_are_bounded(self):
        for suffix, bad in (
            ('manifest.json', b'{'+b'x' * (16384+1)),
            ('obj-latch-count.txt', b'CPS1_DINO_LATCH_V2 '+b'x' * 200),
        ):
            path = self.root / ('frame-00000904.' + suffix)
            original = path.read_bytes()
            try:
                path.write_bytes(bad)
                with self.subTest(suffix=suffix):
                    with self.assertRaisesRegex(ValueError, 'size is invalid'):
                        private_capture_file_snapshot(self.root)
            finally:
                path.write_bytes(original)

    def test_invalid_nominal_selection_or_nonmapping_snapshot_rejected(self):
        for kwargs in (
            {'first_frame': True}, {'frame_count': True},
            {'frame_count': 3}, {'frame_count': 25},
            {'frame_step': 0}, {'frame_step': True},
            {'first_frame': 99999999},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(ValueError, 'interval'):
                    private_capture_file_snapshot(self.root, **kwargs)
        with self.assertRaisesRegex(ValueError, 'Invalid private capture snapshot'):
            require_stable_private_capture(self.root, [])


if __name__ == '__main__':
    unittest.main()
