"""Stage 250 host X11 witness: mocks only, not actual emulator proof."""
import json
from pathlib import Path
import tempfile
import unittest

from tools import nexium_host_live_counter_pixel as pixel

BASE={
    'caption':(11,18,29),'impact':(62,83,74),
    'player':(62,180,208),'ground':(62,83,74),
}
GOOD=pixel.EXPECTED

class FakeSampler:
    def __init__(self,window):
        assert window=='987'
        self.samples=[BASE,BASE,GOOD]
        self.closed=False

    def sample(self):
        return self.samples.pop(0) if self.samples else GOOD

    def close(self):
        self.closed=True

class Tests(unittest.TestCase):
    def test_four_expected_pixels_same_frame(self):
        self.assertEqual(pixel.classify(BASE,[GOOD]),pixel.STATUS)

    def test_no_mixing_colors_from_different_frames(self):
        a=dict(BASE,caption=GOOD['caption'])
        b=dict(BASE,impact=GOOD['impact'])
        c=dict(BASE,ground=GOOD['ground'],player=GOOD['player'])
        self.assertEqual(pixel.classify(BASE,[a,b,c]),pixel.INCONCLUSIVE)

    def test_preexisting_counter_is_rejected(self):
        self.assertEqual(pixel.classify(GOOD,[GOOD]),pixel.INCONCLUSIVE)
        self.assertEqual(pixel.classify(dict(BASE,impact=GOOD['impact']),[GOOD]),pixel.INCONCLUSIVE)

    def test_ground_calibration_mandatory(self):
        self.assertEqual(pixel.classify(dict(BASE,ground=(0,0,0)),[GOOD]),pixel.INCONCLUSIVE)
        self.assertEqual(pixel.classify(None,[GOOD]),pixel.INCONCLUSIVE)

    def test_mismatched_single_pixel_rejected(self):
        for key in GOOD:
            with self.subTest(key=key):
                bad=dict(GOOD,**{key:(0,0,0)})
                self.assertEqual(pixel.classify(BASE,[bad]),pixel.INCONCLUSIVE)

    def test_observer_arm_then_sample(self):
        w=pixel.CounterWindowWatcher('987',sampler_factory=FakeSampler,seconds=0.2)
        self.assertTrue(w.start())
        w.trigger()
        report=w.finish()
        self.assertEqual(report['status'],pixel.STATUS)
        self.assertTrue(report['same_x11_image_four_pixel_match'])
        self.assertFalse(report['native_guest_counter_event_bound'])
        self.assertFalse(report['physical_display_verified'])

    def test_invalid_window_and_safe_result(self):
        for window in ('0','-7','foo',str(2**32)):
            with self.subTest(window=window):
                with self.assertRaises(ValueError):
                    pixel.X11Window(window)
        rec=pixel.result(pixel.INCONCLUSIVE,reason='X11_UNAVAILABLE')
        self.assertNotIn('window_id',rec)
        self.assertFalse(rec['host_x11_window_counter_pixels_observed'])
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'summary.json'
            pixel.save(path,rec)
            self.assertEqual(json.loads(path.read_text()),rec)

if __name__=='__main__':
    unittest.main()
