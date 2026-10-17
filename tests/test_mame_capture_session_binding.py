"""ROM-free regression of dual-probe MAME session labeling, not VBlank age."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.mame_capture_session_binding import require_private_capture_session
from tools.mame_obj_latch_evidence import obj_fnv1a64, latch_counter_diagnostic
from test_mame_obj_cli_end_to_end import make_capture

SESSION_A = '0123456789abcdef0123456789abcdef'
SESSION_B = 'fedcba9876543210fedcba9876543210'


class CaptureCrossProbeSessionTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        make_capture(self.root)
        self.stamp(SESSION_A)

    def stamp(self, session, *, frame=None, change_lua=True, change_cpp=True):
        for n in ([frame] if frame is not None else range(900, 912, 2)):
            stem = f'frame-{n:08d}'
            if change_lua:
                path = self.root / f'{stem}.manifest.json'
                document = json.loads(path.read_text())
                document['capture_session'] = session
                path.write_text(json.dumps(document))
            if change_cpp:
                obj = (self.root / f'{stem}.buffered-obj-be.bin').read_bytes()
                (self.root / f'{stem}.obj-latch-count.txt').write_text(
                    f'CPS1_DINO_LATCH_V2 {n} {obj_fnv1a64(obj)}\n'
                    f'CPS1_DINO_SESSION {session}\n')

    def test_six_matching_lua_cpp_frames_have_local_only_consistency(self):
        out = require_private_capture_session(self.root, SESSION_A)
        self.assertEqual(out['cpp_latch_session_samples'], 6)
        self.assertEqual(out['lua_manifest_session_samples'], 6)
        self.assertTrue(out['shared_session_label_consistent'])
        self.assertFalse(out['label_is_authenticated_game_provenance'])
        self.assertFalse(out['hardware_vblank_observed'])
        self.assertFalse(out['frame_sync_verified'])
        self.assertNotIn(SESSION_A, json.dumps(out))
        objs = [(self.root / f'frame-{n:08d}.buffered-obj-be.bin').read_bytes()
                for n in range(900, 912, 2)]
        counters = latch_counter_diagnostic(
            self.root, 900, 6, 2, [0]*5, objs)
        self.assertEqual(counters['capture_session_tagged_samples'], 6)
        self.assertTrue(counters['capture_session_label_consistent'])
        self.assertNotIn(SESSION_A, json.dumps(counters))

    def test_a_different_lua_session_in_one_frame_is_rejected(self):
        self.stamp(SESSION_B, frame=904, change_cpp=False)
        with self.assertRaisesRegex(ValueError, 'Lua capture session'):
            require_private_capture_session(self.root, SESSION_A)

    def test_a_different_cpp_session_in_one_frame_is_rejected(self):
        self.stamp(SESSION_B, frame=904, change_lua=False)
        with self.assertRaisesRegex(ValueError, 'C\\+\\+ capture session'):
            require_private_capture_session(self.root, SESSION_A)

    def test_mixed_cpp_sessions_rejected_by_generic_v2_counter_reader(self):
        self.stamp(SESSION_B, frame=906, change_lua=False)
        objs = [(self.root / f'frame-{n:08d}.buffered-obj-be.bin').read_bytes()
                for n in range(900, 912, 2)]
        with self.assertRaisesRegex(ValueError, 'Mixed or missing'):
            latch_counter_diagnostic(self.root, 900, 6, 2, [0]*5, objs)

    def test_legacy_unstamped_v2_may_parse_but_private_session_must_refuse(self):
        path = self.root / 'frame-00000904.obj-latch-count.txt'
        path.write_text(path.read_text().splitlines(keepends=True)[0])
        with self.assertRaisesRegex(ValueError, 'C\\+\\+ capture session'):
            require_private_capture_session(self.root, SESSION_A)

    def test_missing_lua_stamp_is_refused(self):
        path = self.root / 'frame-00000910.manifest.json'
        manifest = json.loads(path.read_text())
        del manifest['capture_session']
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'Lua capture session'):
            require_private_capture_session(self.root, SESSION_A)

    def test_invalid_session_label_rejected_without_looking_at_rom_data(self):
        for malformed in ('', 'UPPERCASE01234567890123456789012',
                          '0'*31, 'g'*32, True, 3):
            with self.subTest(label=str(malformed)[:15]):
                with self.assertRaisesRegex(ValueError, 'Invalid local'):
                    require_private_capture_session(self.root, malformed)

    def test_wrong_same_length_expected_token_cannot_validate(self):
        with self.assertRaises(ValueError):
            require_private_capture_session(self.root, SESSION_B)

    def test_malformed_or_oversized_cpp_line_fails_closed(self):
        path = self.root / 'frame-00000900.obj-latch-count.txt'
        for invalid in (
            b'CPS1_DINO_LATCH_V2 900 0123456789abcdef\n'
            b'CPS1_DINO_SESSION 0\n',
            b'x' * 129,
            b'CPS1_DINO_LATCH_V2 900 0123456789abcdef\n'
            b'CPS1_DINO_SESSION ' + SESSION_A.upper().encode() + b'\n',
        ):
            with self.subTest(length=len(invalid)):
                path.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    require_private_capture_session(self.root, SESSION_A)


if __name__ == '__main__':
    unittest.main()
