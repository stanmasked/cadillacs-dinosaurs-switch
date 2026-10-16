"""Run the actual portable C renderer on synthetic captures and compare with Python.

Requires a host C compiler; tests use only ROM-free synthetic data.
"""
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zlib

from tools.cps1_scene_export import pack_scene, FILE_BYTES, PAYLOAD_BYTES
from tools.cps1_frame import render_frame, tile_ram_index
from tools.cps1_video import TOTAL_COLORS

ROOT=Path(__file__).resolve().parents[1]
GFX_SIZE=0x400000
W,H=384,224


def blank_scene():
    palette=[[0,0,0] for _ in range(TOTAL_COLORS)]
    palette[0xbff]=[5,6,7]
    palette[1]=[255,0,0]
    palette[0x400+1]=[0,255,0]
    return {'layer_control': (2<<6)|(3<<8)|(1<<10)|(0<<12),
            'video_control':0,'palette_rgb':palette,
            'buffered_obj_words':[0,0,0,0xff00]}


def synthetic_graphics():
    gfx=bytearray(GFX_SIZE)
    # Fill first 16x16 tile with pen 1 via the third data plane.
    for y in range(16):
        gfx[y*8+3]=255
        gfx[y*8+7]=255
    # Second 16x16 tile remains pen 0.
    # Code 2 is all pen 15 (transparent).
    for y in range(16):
        for plane in range(8):
            gfx[256+y*8+plane]=255
    return bytes(gfx)


@unittest.skipUnless(shutil.which('gcc'), 'Host gcc required for portable C parity')
class NativeSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='cps1-native-scene-')
        cls.libpath=Path(cls.tmp.name)/'libcps1scene.so'
        compiled=subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                                 '-fPIC','-shared','-Isource',
                                 'source/cps1_scene.c','source/cps1_tile.c',
                                 '-o',str(cls.libpath)],cwd=ROOT,check=False,
                                capture_output=True,text=True)
        if compiled.returncode:
            raise AssertionError('Host C compiler failed:\\n' + compiled.stderr)
        cls.dll=ctypes.CDLL(str(cls.libpath))
        cls.dll.cps1_scene_decode.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p]
        cls.dll.cps1_scene_decode.restype=ctypes.c_bool
        cls.dll.cps1_scene_render.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,
                                             ctypes.c_void_p,ctypes.c_size_t]
        cls.dll.cps1_scene_render.restype=ctypes.c_bool
        cls.dll.cps1_scene_pan.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int]
        cls.dll.cps1_scene_pan.restype=ctypes.c_bool
        cls.gfx=synthetic_graphics()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def native_frame(self,snapshot):
        source=pack_scene(snapshot)
        self.assertEqual(len(source),FILE_BYTES)
        scenebuf=ctypes.create_string_buffer(70000)
        self.assertTrue(self.dll.cps1_scene_decode(source,len(source),scenebuf))
        out=ctypes.create_string_buffer(W*H*4)
        self.assertTrue(self.dll.cps1_scene_render(self.gfx,len(self.gfx),scenebuf,
                                                    out,len(out)))
        return out.raw

    def parity(self,snapshot):
        cpp=self.native_frame(snapshot)
        pal=[tuple(x) for x in snapshot['palette_rgb']]
        py=render_frame(self.gfx,pal,snapshot)
        self.assertEqual(cpp,py)


    def test_pan_is_noop_for_zero_and_null(self):
        scene=ctypes.create_string_buffer(70000)
        self.assertTrue(self.dll.cps1_scene_decode(
            pack_scene(blank_scene()), FILE_BYTES, scene))
        self.assertFalse(self.dll.cps1_scene_pan(scene,0,0))
        self.assertFalse(self.dll.cps1_scene_pan(None,1,0))

    def test_pan_wraps_all_three_unsigned_scroll_registers(self):
        original=blank_scene()
        original['scroll2']={'words':[0]*8192,'scrollx':65535,'scrolly':0,
                             'enabled':True}
        src=pack_scene(original)
        scene=ctypes.create_string_buffer(70000)
        self.assertTrue(self.dll.cps1_scene_decode(src,len(src),scene))
        self.assertTrue(self.dll.cps1_scene_pan(scene,3,-1))
        # Cps1Scene starts with layer/video words, followed by scrollx[3]
        # and scrolly[3]. Do not inspect opaque padding beyond this prefix.
        values=__import__('struct').unpack_from('<8H',scene.raw)
        self.assertEqual(values[2:5],(3,2,3))
        self.assertEqual(values[5:8],(65535,65535,65535))

    def test_native_pan_frame_equals_python_scrolled_frame(self):
        import copy
        snapshot=blank_scene()
        words=[0]*8192
        words[tile_ram_index('scroll2',5,1)*2]=2
        snapshot['scroll2']={'words':words,'scrollx':0,'scrolly':0,'enabled':True}
        binary=pack_scene(snapshot)
        mem=ctypes.create_string_buffer(70000)
        self.assertTrue(self.dll.cps1_scene_decode(binary,len(binary),mem))
        initial=ctypes.create_string_buffer(W*H*4)
        self.assertTrue(self.dll.cps1_scene_render(
            self.gfx,len(self.gfx),mem,initial,len(initial)))
        self.assertTrue(self.dll.cps1_scene_pan(mem,16,0))
        panned=ctypes.create_string_buffer(W*H*4)
        self.assertTrue(self.dll.cps1_scene_render(
            self.gfx,len(self.gfx),mem,panned,len(panned)))
        shifted=copy.deepcopy(snapshot)
        shifted['scroll2']['scrollx']=16
        expected=render_frame(self.gfx,
                              [tuple(c) for c in shifted['palette_rgb']],
                              shifted)
        self.assertEqual(panned.raw,expected)
        self.assertNotEqual(panned.raw,initial.raw)

    def test_pan_accumulates_and_reverses_exactly(self):
        scene=ctypes.create_string_buffer(70000)
        binary=pack_scene(blank_scene())
        self.assertTrue(self.dll.cps1_scene_decode(binary,len(binary),scene))
        original=scene.raw
        for delta in ((3,-1),(12,4),(-15,-3)):
            self.assertTrue(self.dll.cps1_scene_pan(scene,*delta))
        self.assertEqual(scene.raw,original)

    def test_export_size_and_valid_header(self):
        snapshot=blank_scene()
        blob=pack_scene(snapshot)
        self.assertEqual(blob[:8],b'CPS1SCN1')
        self.assertEqual(int.from_bytes(blob[8:12],'little'),PAYLOAD_BYTES)
        self.assertEqual(zlib.crc32(blob[16:]),int.from_bytes(blob[12:16],'little'))
        dst=ctypes.create_string_buffer(70000)
        self.assertTrue(self.dll.cps1_scene_decode(blob,len(blob),dst))

    def test_rejects_corruption_and_truncation(self):
        original=pack_scene(blank_scene())
        dst=ctypes.create_string_buffer(70000)
        for wrong in (original[:-1],b'X'+original[1:],
                      original[:100]+bytes([original[100]^1])+original[101:],
                      original[:8]+b'BAD!'+original[12:]):
            with self.subTest(length=len(wrong)):
                self.assertFalse(self.dll.cps1_scene_decode(wrong,len(wrong),dst))

    def test_empty_scene_matches_reference(self):
        self.parity(blank_scene())

    def _with_wrap_graphics(self, callback):
        # Two different real-layout 16x16 test cells at 0x7ff0 and 0x0000;
        # ALL ROM bytes are synthetic. Keep this scoped to one test.
        buf=bytearray(self.gfx)
        for row in range(16):
            for part in (0,4):
                buf[row*8+part:row*8+part+4]=b'\x00'*4
                buf[row*8+part+2]=255 # Code0 pen2
                buf[0x7ff0*128+row*8+part+3]=255 # Code0x7ff0 pen1
        old=self.gfx
        self.gfx=bytes(buf)
        try:
            callback()
        finally:
            self.gfx=old

    def test_composite_last_tile_wrap_native_python_identically(self):
        snap=blank_scene()
        snap['palette_rgb'][2]=[0,220,70]
        snap['buffered_obj_words']=[64,16,0x7ff0,0x1000,0,0,0,0xff00]
        def verify():
            self.parity(snap)
            picture=self.native_frame(snap)
            self.assertEqual(picture[:4],bytes((255,0,0,255)))
            self.assertEqual(picture[16*W*4:16*W*4+4],bytes((0,220,70,255)))
        self._with_wrap_graphics(verify)

    def test_composite_vertical_flip_wrap_native_python_identically(self):
        snap=blank_scene()
        snap['palette_rgb'][2]=[0,220,70]
        snap['buffered_obj_words']=[64,16,0x7ff0,0x1040,0,0,0,0xff00]
        def verify():
            self.parity(snap)
            picture=self.native_frame(snap)
            self.assertEqual(picture[:4],bytes((0,220,70,255)))
            self.assertEqual(picture[16*W*4:16*W*4+4],bytes((255,0,0,255)))
        self._with_wrap_graphics(verify)

    def test_unmapped_original_obj_base_stays_blank_in_both_engines(self):
        snap=blank_scene()
        snap['buffered_obj_words']=[64,16,0x8000,0x1000,0,0,0,0xff00]
        self.parity(snap)
        self.assertEqual(self.native_frame(snap)[:4],bytes((5,6,7,255)))

    def test_priority_scroll2_masks_entire_two_row_sprite(self):
        scene=blank_scene()
        # Scroll2 immediately before OBJ in CPS-B draw order.
        scene['layer_control']=(2<<6)|(0<<8)|(1<<10)|(3<<12)
        scene['scroll2']={'words':[0]*8192,'enabled':True,
                          'scrollx':0,'scrolly':0}
        scene['priority_masks']=[2,0,0,0]  # pen1 in priority group0
        scene['buffered_obj_words']=[
            64,16,0,0x1000,  # two vertically stacked 16x16 cells
            64,16,0,1,       # another OBJ would otherwise overwrite
            0,0,0,0xff00]
        scene['palette_rgb'][1025]=[15,25,220]
        scene['palette_rgb'][17]=[30,220,70]
        self.parity(scene)
        native=self.native_frame(scene)
        self.assertEqual(native[:4],bytes((15,25,220,255)))
        self.assertEqual(native[16*W*4:16*W*4+4],bytes((15,25,220,255)))

    def test_priority_mask_disabled_first_sprite_wins_both_rows(self):
        scene=blank_scene()
        scene['layer_control']=(2<<6)|(0<<8)|(1<<10)|(3<<12)
        scene['scroll2']={'words':[0]*8192,'enabled':True,
                          'scrollx':0,'scrolly':0}
        scene['priority_masks']=[0,0,0,0]
        scene['buffered_obj_words']=[
            64,16,0,0x1000, 64,16,0,1, 0,0,0,0xff00]
        scene['palette_rgb'][1025]=[15,25,220]
        scene['palette_rgb'][17]=[30,220,70]
        self.parity(scene)
        native=self.native_frame(scene)
        self.assertEqual(native[:4],bytes((255,0,0,255)))
        # Code16 is synthetic pen0 and remains opaque, not transparent.
        self.assertEqual(native[16*W*4:16*W*4+4],bytes((0,0,0,255)))

    def test_priority_group_one_mask_applies_only_group_one(self):
        scene=blank_scene()
        scene['layer_control']=(2<<6)|(0<<8)|(1<<10)|(3<<12)
        words=[0]*8192
        for i in range(4096): words[2*i+1]=0x80 # priority group1
        scene['scroll2']={'words':words,'enabled':True,
                          'scrollx':0,'scrolly':0}
        scene['priority_masks']=[2,0,0,0]
        scene['buffered_obj_words']=[64,16,0,0x1000,0,0,0,0xff00]
        scene['palette_rgb'][1025]=[15,25,220]
        self.parity(scene)
        self.assertEqual(self.native_frame(scene)[:4],bytes((255,0,0,255)))
        scene['priority_masks']=[0,2,0,0]
        self.parity(scene)
        self.assertEqual(self.native_frame(scene)[:4],bytes((15,25,220,255)))

    def test_transparent_foreground_tile_unmasks_sprite_only_there(self):
        scene=blank_scene()
        scene['layer_control']=(2<<6)|(0<<8)|(1<<10)|(3<<12)
        words=[0]*8192
        # Synthetic code2 has all pen15: transparent at (X64,Y16).
        idx=tile_ram_index('scroll2',4,1)
        words[2*idx]=2
        scene['scroll2']={'words':words,'enabled':True,
                          'scrollx':0,'scrolly':0}
        scene['priority_masks']=[2,0,0,0]
        scene['buffered_obj_words']=[64,16,0,0x1000,0,0,0,0xff00]
        scene['palette_rgb'][1025]=[15,25,220]
        self.parity(scene)
        native=self.native_frame(scene)
        self.assertEqual(native[:4],bytes((255,0,0,255)))
        self.assertEqual(native[16*W*4:16*W*4+4],bytes((15,25,220,255)))

    def test_native_priority_masks_16_deterministic_full_frames(self):
        import random
        rng=random.Random(31032)
        for scenario in range(16):
            with self.subTest(scenario=scenario):
                scene=blank_scene()
                scene['layer_control']=(2<<6)|(0<<8)|(1<<10)|(3<<12)
                words=[0]*8192
                for i in range(4096):
                    words[2*i+1]=(((scenario+i)%4)<<7)
                scene['scroll2']={
                    'words':words,'enabled':True,
                    'scrollx':rng.randrange(0,16),
                    'scrolly':rng.randrange(0,16)}
                scene['priority_masks']=[
                    rng.choice((0,2,0x8000)) for _ in range(4)]
                attr=0x1000 | (0x20 if scenario&1 else 0) | (
                    0x40 if scenario&2 else 0)
                scene['buffered_obj_words']=[
                    64+(scenario*4),16+(scenario*2),0,attr,
                    64+(scenario*4),16+(scenario*2),0,1,
                    0,0,0,0xff00]
                self.parity(scene)

    def test_first_opaque_sprite_owns_overlap_in_native_and_python(self):
        snap=blank_scene()
        snap['palette_rgb'][17]=[0,230,60]
        snap['buffered_obj_words']=[
            64,16,0,0,  # First OBJ: opaque red pen1, group0
            64,16,0,1,  # Later OBJ: same pixels, green group1
            0,0,0,0xff00]
        self.parity(snap)
        self.assertEqual(self.native_frame(snap)[:4],bytes((255,0,0,255)))

    def test_first_transparent_sprite_leaves_later_obj_visible(self):
        snap=blank_scene()
        snap['palette_rgb'][17]=[0,230,60]
        snap['buffered_obj_words']=[
            64,16,2,0,  # Code2 is pen15, does not stamp priority
            64,16,0,1,
            0,0,0,0xff00]
        self.parity(snap)
        self.assertEqual(self.native_frame(snap)[:4],bytes((0,230,60,255)))

    def test_pen_zero_opaque_sprite_stamps_priority(self):
        snap=blank_scene()
        snap['palette_rgb'][17]=[0,230,60]
        snap['buffered_obj_words']=[
            64,16,1,0,  # Code1 is pen0, still opaque
            64,16,0,1,
            0,0,0,0xff00]
        self.parity(snap)
        self.assertEqual(self.native_frame(snap)[:4],bytes((0,0,0,255)))

    def test_scroll2_with_sprite_matches_reference(self):
        scene=blank_scene()
        scene['scroll2']={'words':[0]*8192,'enabled':True,'scrollx':0,'scrolly':0}
        scene['buffered_obj_words']=[64,16,0,0,0,0,0,0xff00]
        self.parity(scene)

    def test_priority_occlusion_matches_reference(self):
        scene=blank_scene()
        scene['scroll2']={'words':[0]*8192,'enabled':True,'scrollx':0,'scrolly':0}
        scene['priority_masks']=[0x0002,0,0,0]
        scene['buffered_obj_words']=[64,16,0,0,0,0,0,0xff00]
        self.parity(scene)

    def test_rowscroll_matches_reference(self):
        scene=blank_scene()
        words=[0]*8192
        words[tile_ram_index('scroll2',5,1)*2]=2
        scene['scroll2']={'words':words,'enabled':True,'scrollx':0,'scrolly':0}
        scene['video_control']=1
        scene['rowscroll_offset']=5
        scene['rowscroll']=[0]*1024
        scene['rowscroll'][21]=16
        self.parity(scene)

    def test_composite_flipped_sprite_matches_reference(self):
        scene=blank_scene()
        scene['buffered_obj_words']=[64,16,0,0x1160,0,0,0,0xff00]
        self.parity(scene)

    def test_requires_effective_palette(self):
        scene=blank_scene()
        del scene['palette_rgb']
        scene['palette_source']={'control':1,'words':[0]*512}
        with self.assertRaises(ValueError): pack_scene(scene)

    def test_reject_bad_scroll_table(self):
        scene=blank_scene()
        scene['scroll2']={'words':[0]*5}
        with self.assertRaises(ValueError): pack_scene(scene)

    def test_reject_bad_sprite_group(self):
        scene=blank_scene()
        scene['buffered_obj_words']=[1,2,3]
        with self.assertRaises(ValueError): pack_scene(scene)


if __name__=='__main__':
    unittest.main()
