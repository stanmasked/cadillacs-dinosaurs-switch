"""Stage 250 host X11 witness: mocks only, not actual emulator proof."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

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

    def test_live_probe_arms_before_waiting_for_ready_marker(self):
        from tools import nexium_live_counter_hid_press as live_probe
        events=[]
        class Watcher:
            def __init__(self, window):
                self.window=window
            def start(self):
                events.append('arm')
                return True
            def trigger(self):
                events.append('trigger')
            def cancel(self, reason):
                events.append('cancel:'+reason)
            def finish(self):
                events.append('finish')
                return pixel.result(pixel.INCONCLUSIVE)
        def fake_until(fn, roots, seconds, interval):
            if fn is live_probe.previous_guest_natural_witness:
                events.append('prior')
                return True
            events.append('ready')
            return True
        def fake_press(key, duration=0.18, after_keydown=None):
            events.append('press:'+key)
            if after_keydown:
                after_keydown()
        with patch.object(live_probe,'until',side_effect=fake_until), \
             patch.object(live_probe,'press',side_effect=fake_press), \
             patch.object(live_probe.subprocess,'run'), \
             patch.object(live_probe.pixels,'CounterWindowWatcher',Watcher), \
             patch.object(live_probe.pixels,'save'):
            rec=live_probe.probe('987',[Path('.')],host_counter_out=Path('optional.json'))
        self.assertEqual(rec['status'],'HOST_LIVE_SCENE_ZR_ATTEMPT_AFTER_REAL_Y_X')
        self.assertLess(events.index('arm'),events.index('ready'))
        self.assertLess(events.index('ready'),events.index('press:t'))
        self.assertLess(events.index('press:t'),events.index('trigger'))
        self.assertEqual(events[-1],'finish')

    def test_no_ready_marker_cancels_observer_without_host_success(self):
        from tools import nexium_live_counter_hid_press as live_probe
        events=[]
        class Watcher:
            def __init__(self, window): pass
            def start(self): events.append('arm')
            def cancel(self, reason): events.append(reason)
            def finish(self):
                events.append('finish')
                return pixel.result(pixel.INCONCLUSIVE,reason='NO_LIVE_ARENA_WINDUP_MARKER')
        def fake_until(fn, roots, seconds, interval):
            return fn is live_probe.previous_guest_natural_witness
        with patch.object(live_probe,'until',side_effect=fake_until), \
             patch.object(live_probe,'press'), \
             patch.object(live_probe.subprocess,'run'), \
             patch.object(live_probe.pixels,'CounterWindowWatcher',Watcher), \
             patch.object(live_probe.pixels,'save') as save:
            rec=live_probe.probe('987',[Path('.')],host_counter_out=Path('optional.json'))
        self.assertEqual(rec['status'],'INCONCLUSIVE_NO_LIVE_ARENA_WINDUP_MARKER')
        self.assertEqual(events,['arm','NO_LIVE_ARENA_WINDUP_MARKER','finish'])
        self.assertFalse(save.call_args.args[1]['host_x11_window_counter_pixels_observed'])

if __name__=='__main__':
    unittest.main()
