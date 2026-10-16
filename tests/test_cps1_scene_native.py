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
