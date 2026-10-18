"""ROM-free proof that optional host fallback cannot reset active guest sound."""
from pathlib import Path
import tempfile
import unittest

from tools import nexium_hid_fallback_guard as guard


class FallbackHidGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='dino-hid-fallback-')
        self.root=Path(self.temp.name)
        self.sd=self.root/'xdg-config'/'nexium'/'sdmc'
        self.sd.mkdir(parents=True)
        self.hid=self.sd/guard.WITNESS
        self.stress=self.sd/guard.STRESS

    def tearDown(self):
        self.temp.cleanup()

    def test_no_guest_hid_evidence_allows_original_recovery(self):
        self.assertTrue(guard.may_send_fallback([self.root]))
        self.assertEqual(guard.main([str(self.root)]),0)

    def test_incomplete_controller_sequence_still_allows_recovery(self):
        self.hid.write_text(
            'event,flags,player_x,sparring\n'
            'RESET,1,90,0\n',encoding='ascii')
        self.assertTrue(guard.may_send_fallback([self.root]))

    def test_completed_guest_hid_never_receives_second_reset(self):
        self.hid.write_text(
            'event,flags,player_x,sparring\n'
            'RESET,1,90,0\n'
            'INPUT_DONE,31,184,1\n',encoding='ascii')
        self.assertFalse(guard.may_send_fallback([self.root]))
        self.assertEqual(guard.main([str(self.root)]),1)

    def test_guest_audio_window_blocks_fallback_even_without_completion(self):
        self.hid.write_text('RESET,1,90,0\n',encoding='ascii')
        self.stress.write_text('event,elapsed_ticks\nSTART,0\n',
                               encoding='ascii')
        self.assertFalse(guard.may_send_fallback([self.root]))
        self.stress.write_bytes(b'')
        self.assertFalse(guard.may_send_fallback([self.root]))

    def test_malformed_or_oversized_witness_fails_closed(self):
        for bytes_ in (b'\xffBAD\n',b'A'*1025,b''):
            with self.subTest(length=len(bytes_)):
                self.hid.write_bytes(bytes_)
                self.assertFalse(guard.may_send_fallback([self.root]))

    def test_existing_symlink_witness_blocks_input(self):
        source=self.root/'outside.json'
        source.write_text('INPUT_DONE,31,184,1\n',encoding='ascii')
        self.hid.symlink_to(source)
        self.assertFalse(guard.may_send_fallback([self.root]))

    def test_fallback_suppressed_from_nested_second_search_root(self):
        self.hid.write_text('INPUT_DONE,31,184,1\n',encoding='ascii')
        other=self.root/'isolated-home'
        other.mkdir()
        self.assertFalse(guard.may_send_fallback([other,self.root]))
        self.assertFalse(guard.may_send_fallback([other,self.root,self.root]))

    def test_cli_without_safe_root_fails_closed(self):
        self.assertEqual(guard.main([]),1)
        self.assertEqual(guard.main([str(self.root/'not-present')]),0)

    def test_probe_script_checks_guard_before_backup_reset(self):
        script=(Path(__file__).resolve().parents[1]/
                'tools/nexium_guest_replay_probe.sh').read_text(
                    encoding='utf-8')
        start=script.index('if ! grep -q HOST_PIXEL_CHANGE_OBSERVED_UNBOUND')
        guard_pos=script.index('python3 tools/nexium_hid_fallback_guard.py',
                                start)
        reset_pos=script.index('xdotool keydown z;',start)
        self.assertLess(guard_pos,reset_pos)
        self.assertIn('"$HOME" "$XDG_CONFIG_HOME"',script[guard_pos:reset_pos])


if __name__=='__main__':
    unittest.main()
