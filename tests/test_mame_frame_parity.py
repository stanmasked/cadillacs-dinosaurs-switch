"""ROM-free end-to-end tests: synthetic MAME RAM to pixel-parity report."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tools.mame_frame_parity import run_parity
from tools.mame_render_import import import_render
from tools.cps1_frame import render_frame
from tools.frame_compare import load_rgba_png

STEM='frame-00000900'
GFX=bytes(0x400000)


def fixture(root):
    meta={
        'game':'dino','frame':900,'capture_hook':'screen_update_cps1_complete',
        'full_cliprect':True,'buffered_obj_same_render_pass':True,
        'reference_pixel_encoding':'rgb24_palette_resolved',
        'raw_word_endianness':'big','palette_source':'MAME_effective_pen_color',
        'gfxram_bytes':0x30000,'cps_a_bytes':64,'cps_b_bytes':64,
        'buffered_obj_bytes':2048,'palette_bytes':9216,
        'reference_rgb_bytes':258048,'reference_width':384,
        'reference_height':224,'pixel_parity_verified':False}
    (root/(STEM+'.manifest.json')).write_text(json.dumps(meta))
    contents={
        'gfxram-be.bin':bytearray(0x30000),
        'cps-a-be.bin':bytearray(64),
        'cps-b-be.bin':bytearray(64),
        'buffered-obj-be.bin':bytearray(2048),
        'palette-rgb24.bin':bytearray(9216),
        'reference-rgb24.bin':bytearray(258048),
    }
    contents['gfxram-be.bin'][:2]=b'\xab\xcd'
    contents['cps-a-be.bin'][:]=struct.pack('>32H',*([0,0,0x40,0x80]+[0]*28))
    contents['buffered-obj-be.bin'][:8]=b'\x00\x40\x00\x10\x01\x00\x00\x00'
    contents['palette-rgb24.bin'][:3]=b'\x10\x20\x30'
    for suffix,raw in contents.items():
        (root/(STEM+'.'+suffix)).write_bytes(raw)


class FrameParityPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        fixture(self.root)

    def make_exact_capture(self):
        snap,_=import_render(self.root,STEM)
        rgba=render_frame(GFX,snap['palette_rgb'],snap)
        rgb=bytearray((len(rgba)//4)*3)
        for i in range(len(rgb)//3):
            rgb[i*3:i*3+3]=rgba[i*4:i*4+3]
        (self.root/(STEM+'.reference-rgb24.bin')).write_bytes(rgb)
        return rgb

    def test_exact_synthetic_frame(self):
        self.make_exact_capture()
        report,ref,candidate,heatmap=run_parity(self.root,STEM,GFX)
        self.assertEqual(report['comparison']['different_pixels'],0)
        self.assertTrue(report['pixel_parity_verified_for_this_frame'])
        self.assertFalse(report['game_wide_parity_verified'])
        self.assertFalse(report['native_switch_runtime_tested'])
        self.assertEqual(load_rgba_png(ref)[2],load_rgba_png(candidate)[2])
        w,h,diff=load_rgba_png(heatmap)
        self.assertEqual((w,h),(384,224))
        self.assertEqual(diff[:4],bytes((0,0,0,255)))

    def test_single_pixel_error(self):
        rgb=self.make_exact_capture()
        rgb[0]^=255
        (self.root/(STEM+'.reference-rgb24.bin')).write_bytes(rgb)
        report,_,_,heatmap=run_parity(self.root,STEM,GFX)
        stats=report['comparison']
        self.assertEqual(stats['different_pixels'],1)
        self.assertFalse(report['pixel_parity_verified_for_this_frame'])
        self.assertEqual(stats['first_difference_xy'],[0,0])
        self.assertEqual(load_rgba_png(heatmap)[2][:4],
                         bytes((stats['max_channel_error'],0,0,255)))

    def test_reject_invalid_region(self):
        with self.assertRaisesRegex(ValueError,'4194304'):
            run_parity(self.root,STEM,bytes(17))

    def test_reject_false_verified_claim(self):
        manifest=self.root/(STEM+'.manifest.json')
        data=json.loads(manifest.read_text())
        data['pixel_parity_verified']=True
        manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'pixel_parity_verified'):
            run_parity(self.root,STEM,GFX)

    def test_reject_truncated_obj(self):
        (self.root/(STEM+'.buffered-obj-be.bin')).write_bytes(bytes(2030))
        with self.assertRaisesRegex(ValueError,'buffered-obj-be.bin'):
            run_parity(self.root,STEM,GFX)


if __name__=='__main__':
    unittest.main()
