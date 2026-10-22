"""Stage313 source and optical-decoder regression checks; only mock images."""
from pathlib import Path
import unittest

from tools import nexium_optical_frame_capture_313 as optical
from tools import cps1_synthetic_gfx_fixture_308 as graphics
from tools import cps1_private_scene_compositor_parity as scenes
from tools import cps1_frame


@unittest.skipUnless(optical.Image is not None, "Pillow only in real X11 workflow")
class Stage313OpticalMockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gfx,_ = graphics.build()
        scene=scenes.synthetic_scene(scenes.CASES[0])
        cls.reference=cps1_frame.render_frame(
            gfx,[tuple(p) for p in scene["palette_rgb"]],scene)

    def render_mock(self,index=0,correct_pixels=True,scale=1):
        from PIL import Image,ImageDraw
        canvas=Image.new("RGB",(1280,720),(9,14,22))
        d=ImageDraw.Draw(canvas)
        d.rectangle((8,188,25,205),fill=(255,0,255))
        for bit in range(4):
            y=214+bit*26
            color=(0,255,0) if index&(1<<bit) else (255,0,0)
            d.rectangle((8,y,25,y+17),fill=color)
        for x,y in optical.POINTS:
            p=self.reference[4*(384*y+x):4*(384*y+x)+3]
            if not correct_pixels:p=(0,0,0)
            d.rectangle((64+3*x,24+3*y,64+3*x+2,24+3*y+2),
                        fill=tuple(p))
        if scale!=1:
            canvas=canvas.resize((int(1280*scale),int(720*scale)),
                                 Image.Resampling.NEAREST)
        return canvas

    def test_optical_id_and_scene_samples_are_independent(self):
        image=self.render_mock(index=0)
        self.assertEqual(optical.decode_optical(image)[0][0],0)
        self.assertEqual(
            optical.verify_optical_image(image,0,self.reference),
            len(optical.POINTS))

    def test_frame_identity_rejects_wrong_id_even_with_pixels(self):
        image=self.render_mock(index=3)
        with self.assertRaises(ValueError):
            optical.verify_optical_image(image,2,self.reference)

    def test_optical_barcode_without_scene_pixels_cannot_pass(self):
        image=self.render_mock(index=0,correct_pixels=False)
        with self.assertRaises(ValueError):
            optical.verify_optical_image(image,0,self.reference)

    def test_missing_barcode_fails_even_with_scene_colors(self):
        from PIL import ImageDraw
        image=self.render_mock()
        d=ImageDraw.Draw(image)
        d.rectangle((8,188,25,205),fill=(9,14,22))
        with self.assertRaises(ValueError):
            optical.decode_optical(image)

    def test_scaled_screen_barcode_and_scene(self):
        image=self.render_mock(index=0,scale=.75)
        self.assertEqual(optical.decode_optical(image)[0][0],0)
        self.assertGreaterEqual(optical.verify_optical_image(
            image,0,self.reference),10)


class Stage313SourceGates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.code=(Path(__file__).resolve().parents[1]/"source/main.c").read_text()

    def test_guest_optical_mode_is_compile_time_opt_in(self):
        code=self.code
        self.assertIn("#ifdef DINO_SYNTHETIC_SCENE_HOST_VISIBLE_313",code)
        self.assertIn("synthetic_guest_rows>0u",code)
        self.assertIn("playback.paused=true;",code)
        self.assertIn('fopen("sdmc:/cadillacs-synthetic-scene-next.txt","rb")',code)

    def test_guest_emits_optical_bits_into_submitted_framebuffer(self):
        code=self.code
        source=code.index("scene_frame(frame,stride/sizeof(uint32_t),scene_rgba,")
        beacon=code.index("rectangle(frame,pitch,8,188,18,18,rgb(255,0,255));")
        end=code.index("framebufferEnd(&fb);",source)
        self.assertLess(source,beacon)
        self.assertLess(beacon,end)


if __name__=="__main__":
    unittest.main()
