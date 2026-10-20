"""Stage 248 submitted guest framebuffer witness: parser mock tests only.

No fixture proves actual guest execution, visible emulator window pixels,
physical Switch hardware or speaker audio.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_nexium_guest_counter_framebuffer as v
from tools import verify_nexium_guest_live_counter_hid as live

HEADER=','.join(v.COLUMNS)+'\n'
LIVE_HEADER=','.join(live.FIELDS)+'\n'
LIVE_ROW=('LIVE_HID_COUNTER,118,90,134,11,5,3,0,9,48,'
          '2048,1,1,1169E164EDF5FD7D\n')


def row(packing='ABGR',tick=1589,ttl=5,impact=5):
    colors=v.EXPECTED_PACKED[packing]
    return (f'SUBMITTED_COUNTER_FRAME,802,{tick},{ttl},{impact},'+
            ','.join(colors[key] for key in v.COLORS)+'\n')


class GuestSubmittedPixelsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.live=self.root/'live.csv'
        self.live.write_text(LIVE_HEADER+LIVE_ROW,encoding='ascii')
        self.proof=self.root/'framebuffer.csv'
        self.out=self.root/'verdict.json'

    def tearDown(self):
        self.tmp.cleanup()

    def test_both_consistent_native_rgba8_byte_orderings(self):
        for kind in ('ABGR','ARGB'):
            with self.subTest(packing=kind):
                self.proof.write_text(HEADER+row(kind),encoding='ascii')
                evidence=v.verify(self.proof,self.live)
                self.assertEqual(evidence['status'],v.STATUS)
                self.assertEqual(evidence['rgba8_packing'],kind)
                self.assertTrue(evidence['native_guest_framebuffer_pixels_verified'])
                self.assertTrue(evidence['real_rendered_arena_zr_counter_required'])
                self.assertFalse(evidence['host_emulator_screen_pixel_verified'])
                self.assertFalse(evidence['physical_display_verified'])
                self.assertFalse(evidence['physical_joycon_verified'])

    def test_no_frame_during_lost_counter_visual_ttl(self):
        for broken in (
            HEADER,
            HEADER+row(ttl=0),
            HEADER+row(ttl=7),
            HEADER+row(impact=0),
            HEADER+row(impact=7),
            HEADER+row(tick=117),
            HEADER+row().replace('SUBMITTED_COUNTER_FRAME,802,',
                                 'SUBMITTED_COUNTER_FRAME,0,'),
        ):
            with self.subTest(broken=broken[-48:]):
                self.proof.write_text(broken,encoding='ascii')
                with self.assertRaises(ValueError):
                    v.verify(self.proof,self.live)

    def test_change_of_each_color_or_packing_mismatch_rejected(self):
        good=HEADER+row()
        for name in v.COLORS:
            expected=v.EXPECTED_PACKED['ABGR'][name]
            mutated=good.replace(expected,'00000000')
            with self.subTest(name=name):
                self.proof.write_text(mutated,encoding='ascii')
                with self.assertRaises(ValueError):
                    v.verify(self.proof,self.live)
        # All colors individually plausible but cannot mix byte orders.
        mixed=good.replace('FFC9EB5B','FF5BEBC9')
        self.proof.write_text(mixed,encoding='ascii')
        with self.assertRaises(ValueError):
            v.verify(self.proof,self.live)

    def test_reject_duplicate_ragged_lowercase_and_bad_header(self):
        good=HEADER+row()
        for broken in (
            good+row(),
            good.replace('caption_rgba','raw_input'),
            good.replace('SUBMITTED_COUNTER_FRAME,802,',
                         'SUBMITTED_COUNTER_FRAME,0802,'),
            good.replace('FFC9EB5B','ffc9eb5b'),
            good.replace('SUBMITTED_COUNTER_FRAME','LIVE_COUNTER'),
            good.replace(',5,5,',',5,5,')+'X\n',
        ):
            with self.subTest(broken=broken[-50:]):
                self.proof.write_text(broken,encoding='ascii')
                with self.assertRaises(ValueError):
                    v.verify(self.proof,self.live)

    def test_missing_symlinked_frame_or_missing_live_guest_event_rejected(self):
        with self.assertRaises(ValueError):
            v.verify(self.proof,self.live)
        source=self.root/'outside.csv'
        source.write_text(HEADER+row(),encoding='ascii')
        self.proof.symlink_to(source)
        with self.assertRaises(ValueError):
            v.verify(self.proof,self.live)
        self.proof.unlink()
        self.proof.write_text(HEADER+row(),encoding='ascii')
        self.live.unlink()
        with self.assertRaises(ValueError):
            v.verify(self.proof,self.live)

    def test_inconclusive_missing_pixels_does_not_fake_submitted_frame(self):
        self.assertEqual(v.main([
            '--report',str(self.proof),
            '--live-csv',str(self.live),
            '--out',str(self.out)]),0)
        result=json.loads(self.out.read_text(encoding='ascii'))
        self.assertEqual(
            result['status'],
            'INCONCLUSIVE_NO_VALID_GUEST_COUNTER_FRAMEBUFFER_PIXELS')
        self.assertFalse(result['native_guest_framebuffer_pixels_verified'])

    def test_source_observes_real_rendered_buffer_after_live_counter(self):
        source=Path('source/main.c').read_text(encoding='utf-8')
        self.assertIn('guest_live_counter_done &&',source)
        self.assertIn('frame[670u*pitch_px+801u]',source)
        self.assertIn('frame[335u*pitch_px+465u]',source)
        self.assertIn('frame[425u*pitch_px+334u]',source)
        self.assertIn('frame[640u*pitch_px+100u]',source)
        self.assertIn('caption==rgb(91,235,201)',source)
        self.assertIn('impact==rgb(255,243,164)',source)
        self.assertIn('framebufferEnd(&fb);',source)
        self.assertIn('sdmc:/cadillacs-live-counter-framebuffer.csv',source)
        self.assertLess(
            source.index('framebufferEnd(&fb);'),
            source.index('sdmc:/cadillacs-live-counter-framebuffer.csv'))
        shell=Path('tools/nexium_guest_replay_probe.sh').read_text(
            encoding='utf-8')
        self.assertIn('verify_nexium_guest_counter_framebuffer.py',shell)
        workflow=Path('.github/workflows/nexium-guest-replay.yml').read_text(
            encoding='utf-8')
        self.assertIn('guest-live-counter-framebuffer-evidence.json',workflow)


if __name__=='__main__':
    unittest.main()
