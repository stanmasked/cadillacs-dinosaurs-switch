"""ROM-free parity against Python reference for ALL CPS-1 planar tile layouts."""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools.cps1_tiles import decode_tile

ROOT=Path(__file__).resolve().parents[1]
GFX=bytes((i*31+(i//5)*17+7)&255 for i in range(4096))
FORMATS=(('8x8-left','cps1_decode_tile8',8,64,False),
         ('8x8-right','cps1_decode_tile8',8,64,True),
         ('16x16','cps1_decode_tile16',16,128,False),
         ('32x32','cps1_decode_tile32',32,512,False))


@unittest.skipUnless(shutil.which('gcc'),'Host C compiler required')
class NativeTileLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory()
        cls.libpath=Path(cls.folder.name)/'tile_layouts.so'
        proc=subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                             '-fPIC','-shared','-Isource','source/cps1_tile.c',
                             '-o',str(cls.libpath)],cwd=ROOT,text=True,capture_output=True)
        if proc.returncode:
            raise AssertionError(proc.stderr)
        cls.lib=ctypes.CDLL(str(cls.libpath))
        for _,symbol,side,_,_ in FORMATS:
            fn=getattr(cls.lib,symbol)
            fn.argtypes=([ctypes.c_void_p,ctypes.c_size_t,ctypes.c_size_t,
                          ctypes.c_bool,ctypes.c_void_p] if side==8 else
                         [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_size_t,
                          ctypes.c_void_p])
            fn.restype=ctypes.c_bool
        cls.pen=cls.lib.cps1_read_tile_pen
        cls.pen.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint,
                          ctypes.c_size_t,ctypes.c_bool,ctypes.c_uint,
                          ctypes.c_uint,ctypes.c_void_p]
        cls.pen.restype=ctypes.c_bool

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def decode(self,symbol,side,code,right=False,region=GFX):
        out=ctypes.create_string_buffer(side*side)
        fn=getattr(self.lib,symbol)
        success=(fn(region,len(region),code,right,out) if side==8
                 else fn(region,len(region),code,out))
        return bool(success),out.raw

    def test_all_codes_match_python_reference(self):
        for layout,symbol,side,unit,right in FORMATS:
            for code in range(len(GFX)//unit):
                with self.subTest(layout=layout,code=code):
                    valid,actual=self.decode(symbol,side,code,right)
                    self.assertTrue(valid)
                    self.assertEqual(actual,decode_tile(GFX,layout,code))

    def test_read_single_pixel_all_layouts(self):
        for layout,_,side,unit,right in FORMATS:
            for code in (0,len(GFX)//unit-1):
                reference=decode_tile(GFX,layout,code)
                for y in (0,side//2,side-1):
                    for x in (0,side//2,side-1):
                        out=ctypes.c_uint8(255)
                        self.assertTrue(self.pen(GFX,len(GFX),side,code,right,
                                                 x,y,ctypes.byref(out)))
                        self.assertEqual(out.value,reference[y*side+x])

    def test_right_half_is_independent_of_left_half(self):
        a=self.decode('cps1_decode_tile8',8,0,False)[1]
        b=self.decode('cps1_decode_tile8',8,0,True)[1]
        self.assertNotEqual(a,b)

    def test_missing_buffers_and_invalid_size_rejected(self):
        for layout,symbol,side,unit,right in FORMATS:
            ok,_=self.decode(symbol,side,len(GFX)//unit,right)
            self.assertFalse(ok)
            ok,_=self.decode(symbol,side,0,right,region=GFX[:-1])
            self.assertFalse(ok)
            out=ctypes.create_string_buffer(bytes([77])*(side*side),side*side)
            fn=getattr(self.lib,symbol)
            success=(fn(None,len(GFX),0,right,out) if side==8 else
                     fn(None,len(GFX),0,out))
            self.assertFalse(success)
            self.assertEqual(out.raw,bytes([77])*(side*side))

    def test_invalid_pixel_coordinates_do_not_change_output(self):
        pixel=ctypes.c_uint8(99)
        for side in (8,16,32,7):
            self.assertFalse(self.pen(GFX,len(GFX),side,0,False,side,0,
                                      ctypes.byref(pixel)))
            self.assertEqual(pixel.value,99)
        self.assertFalse(self.pen(GFX,len(GFX),8,0,False,0,0,None))

    def test_all_transparent_plane_yields_pen_15(self):
        region=bytes([255])*512
        for layout,symbol,side,unit,right in FORMATS:
            actual=self.decode(symbol,side,0,right,region)[1]
            self.assertEqual(actual,bytes([15])*(side*side))


if __name__=='__main__':
    unittest.main()
