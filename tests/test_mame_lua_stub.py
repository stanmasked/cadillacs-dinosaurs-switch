"""Execute the actual Lua MAME capture script with a synthetic MAME API stub.

Optional on CI runners with liblua5.4. Never loads ROMs or actual game data.
"""
import ctypes
import ctypes.util
import json
from pathlib import Path
import os
import struct
import tempfile
import unittest

LIB=ctypes.util.find_library('lua5.4')
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'tools'/'mame_cps1_capture.lua'

STUB=r'''
local function share(bytes)
  local s={size=bytes}
  function s:read_u16(offset)
    return ((offset//2)*17+33)%65536
  end
  return s
end
local gfx=share(0x30000)
local a,b=share(0x40),share(0x40)
local palette={entries=3072}
function palette:pen(i) return i end
function palette:pen_color(i)
  return 0xff000000|((i%256)<<16)|(((i+1)%256)<<8)|((i+2)%256)
end
local screen={frame_number=900,palette=palette}
function screen:pixels()
  local result={}
  for y=0,223 do
    for x=0,383 do
      result[#result+1]=string.pack('=I4',palette:pen_color((x+y)%3072))
    end
  end
  return table.concat(result),384,224
end
local cpu={spaces={program={}}}
function cpu.spaces.program:read_u16(addr)
  return (((addr-0x900000)//2)*17+33)%65536
end
manager={machine={
  devices={[':maincpu']=cpu},screens={[':screen']=screen},
  palettes={[':palette']=palette},memory={shares={
  [':gfxram']=gfx,[':cps_a_regs']=a,[':cps_b_regs']=b
  }}
}}
_G.__cps1_mock_screen=screen
emu={}
function emu.register_frame_done(callback,name)
  assert(name=='frame')
  callback()
end
'''

@unittest.skipUnless(LIB is not None,'Optional Lua 5.4 shared library not installed')
class MameLuaCaptureStubTests(unittest.TestCase):
    def run_capture(self, extra_stub=''):
        lib=ctypes.CDLL(LIB)
        lib.luaL_newstate.restype=ctypes.c_void_p
        lib.luaL_openlibs.argtypes=[ctypes.c_void_p]
        lib.luaL_loadstring.argtypes=[ctypes.c_void_p,ctypes.c_char_p]
        lib.luaL_loadstring.restype=ctypes.c_int
        lib.luaL_loadfilex.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_char_p]
        lib.luaL_loadfilex.restype=ctypes.c_int
        lib.lua_pcallk.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_int,ctypes.c_int,
                                  ctypes.c_longlong,ctypes.c_void_p]
        lib.lua_pcallk.restype=ctypes.c_int
        lib.lua_tolstring.argtypes=[ctypes.c_void_p,ctypes.c_int,ctypes.c_void_p]
        lib.lua_tolstring.restype=ctypes.c_char_p
        lib.lua_close.argtypes=[ctypes.c_void_p]
        old=os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                Path('cps1-captures').mkdir()
                L=lib.luaL_newstate()
                self.assertTrue(L)
                lib.luaL_openlibs(L)
                try:
                    for source,is_file in ((STUB,False),(extra_stub,False),
                                           (str(SCRIPT),True)):
                        if not source:
                            continue
                        if is_file:
                            code=lib.luaL_loadfilex(L,source.encode(),None)
                        else:
                            code=lib.luaL_loadstring(L,source.encode())
                        self.assertEqual(code,0,'Lua source syntax failure')
                        result=lib.lua_pcallk(L,0,0,0,0,None)
                        if result!=0:
                            raise AssertionError(
                                (lib.lua_tolstring(L,-1,None) or b'Lua runtime failure').decode())
                finally:
                    lib.lua_close(L)
                root=Path('cps1-captures')
                self.assertEqual(len(list(root.iterdir())),6)
                prefix='frame-00000900.'
                for suffix,length in (('gfxram-be.bin',196608),('cps-a-be.bin',64),
                        ('cps-b-be.bin',64),('palette-rgb24.bin',9216),
                        ('reference-rgb24.bin',258048)):
                    self.assertEqual((root/(prefix+suffix)).stat().st_size,length)
                raw=(root/(prefix+'gfxram-be.bin')).read_bytes()
                self.assertEqual(struct.unpack('>2H',raw[:4]),(33,50))
                manifest=json.loads((root/(prefix+'manifest.json')).read_text())
                self.assertFalse(manifest['pixel_parity_eligible'])
                self.assertEqual(manifest['obj_latch'],'NOT_CAPTURED')
                return (root/(prefix+'reference-rgb24.bin')).read_bytes(),manifest
            finally:
                os.chdir(old)

    def test_indexed_screen_pixels_use_effective_palette(self):
        rgb,manifest=self.run_capture()
        self.assertEqual(manifest['reference_pixel_encoding'],'rgb32_resolved')
        self.assertEqual(rgb[:9],bytes((0,1,2,1,2,3,2,3,4)))
        self.assertEqual(manifest['reference_source_format'],'indexed_bitmap')

    def test_direct_rgb_screen_pixels_bypass_palette(self):
        extra=r'''
__cps1_mock_screen.palette=nil
function __cps1_mock_screen:pixels()
  return string.rep(string.pack('=I4',0xff408020),384*224),384,224
end
'''
        rgb,manifest=self.run_capture(extra)
        self.assertEqual(manifest['reference_pixel_encoding'],'rgb32_resolved')
        self.assertEqual(rgb[:9],bytes((64,128,32))*3)
        self.assertEqual(manifest['reference_source_format'],'rgb_bitmap')

    def test_malformed_screen_visible_size_is_rejected(self):
        extra=r'''
function __cps1_mock_screen:pixels()
  return string.rep(string.pack('=I4',0xff408020),320*224),320,224
end
'''
        with self.assertRaisesRegex(AssertionError,'Unexpected MAME visible area'):
            self.run_capture(extra)

if __name__=='__main__':
    unittest.main()
