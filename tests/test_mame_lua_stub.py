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
  callback()
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
            finally:
                os.chdir(old)


    def test_existing_capture_is_not_overwritten_on_restart(self):
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
                root=Path('cps1-captures')
                root.mkdir()
                prior=root/'frame-00000900.reference-rgb24.bin'
                sentinel=b'existing-reference-do-not-overwrite'
                prior.write_bytes(sentinel)
                L=lib.luaL_newstate()
                self.assertTrue(L)
                lib.luaL_openlibs(L)
                try:
                    self.assertEqual(lib.luaL_loadstring(L,STUB.encode()),0)
                    self.assertEqual(lib.lua_pcallk(L,0,0,0,0,None),0)
                    self.assertEqual(lib.luaL_loadfilex(L,str(SCRIPT).encode(),None),0)
                    status=lib.lua_pcallk(L,0,0,0,0,None)
                    self.assertNotEqual(status,0)
                    msg=(lib.lua_tolstring(L,-1,None) or b'').decode()
                    self.assertIn('already exists',msg)
                finally:
                    lib.lua_close(L)
                self.assertEqual(prior.read_bytes(),sentinel)
                self.assertEqual({p.name for p in root.iterdir()},{prior.name})
            finally:
                os.chdir(old)

if __name__=='__main__':
    unittest.main()
