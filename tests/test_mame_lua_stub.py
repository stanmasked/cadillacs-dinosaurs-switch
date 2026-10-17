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
import zlib

from tools.mame_obj_sequence_alignment import CAPTURE_SIZES, read_frames
from tools.mame_obj_latch_evidence import obj_fnv1a64

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
local screen={frame_number=900}
function screen:pixel(x,y) return (x+y)%3072 end
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
emu={}
function emu.register_frame_done(callback,name)
  assert(name=='frame')
  for frame=900,910,2 do
    screen.frame_number=frame
    callback()
  end
end
'''

@unittest.skipUnless(LIB is not None,'Optional Lua 5.4 shared library not installed')
class MameLuaCaptureStubTests(unittest.TestCase):
    def test_lua_script_generates_exact_documented_files(self):
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
                    for source,is_file in ((STUB,False),(str(SCRIPT),True)):
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
                # Six frame_done callbacks must yield six complete Lua
                # capture bundles: five binaries plus a checksum manifest.
                self.assertEqual(len(list(root.iterdir())),36)
                names=set(CAPTURE_SIZES)
                for frame in range(900,912,2):
                    prefix=f'frame-{frame:08d}.'
                    manifest=json.loads((root/(prefix+'manifest.json')).read_text())
                    self.assertEqual(manifest['frame'],frame)
                    self.assertFalse(manifest['pixel_parity_eligible'])
                    self.assertEqual(manifest['obj_latch'],'NOT_CAPTURED')
                    self.assertEqual(set(manifest['file_crc32']),names)
                    for suffix,length in CAPTURE_SIZES.items():
                        raw=(root/(prefix+suffix)).read_bytes()
                        self.assertEqual(len(raw),length)
                        self.assertEqual(manifest['file_crc32'][suffix],
                                         f'{zlib.crc32(raw)&0xffffffff:08x}')
                        if suffix=='gfxram-be.bin':
                            self.assertEqual(struct.unpack('>2H',raw[:4]),(33,50))

                # Original Lua output must now be accepted by the strict
                # multi-frame reader once private C++ probes are present.
                # The generated probes here are synthetic only.
                obj=bytes(2048)
                for i,frame in enumerate(range(900,912,2)):
                    prefix=f'frame-{frame:08d}.'
                    a=(root/(prefix+'cps-a-be.bin')).read_bytes()
                    b=(root/(prefix+'cps-b-be.bin')).read_bytes()
                    (root/(prefix+'render-regs-be.bin')).write_bytes(a+b)
                    (root/(prefix+'buffered-obj-be.bin')).write_bytes(obj)
                    (root/(prefix+'obj-latch-count.txt')).write_text(
                        f'CPS1_DINO_LATCH_V2 {200+i*2} {obj_fnv1a64(obj)}\\n')
                render,lua,objects=read_frames(root,900,6,2,include_obj=True)
                self.assertEqual(len(objects),6)
                self.assertEqual(render,lua)

            finally:
                os.chdir(old)

if __name__=='__main__':
    unittest.main()
