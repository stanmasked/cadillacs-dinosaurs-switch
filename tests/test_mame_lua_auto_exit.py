"""Run *actual* MAME Lua capture script against a synthetic Lua 5.4 MAME stub.

No MAME game ROM, original game pixels, buffered OBJ, or VBlank claims.
"""
import contextlib
import ctypes
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_mame_lua_stub import LIB, SCRIPT, STUB


# Register stub callbacks for every frame, not only the six capture
# samples. The callback must allow 911 before scheduling an auto-exit.
EXIT_STUB = STUB.replace(
    'emu={}',
    '''exit_calls=0
exit_frame=-1
function manager.machine:exit()
  exit_calls=exit_calls+1
  exit_frame=screen.frame_number
end
emu={}''',
).replace('for frame=900,910,2 do', '''for frame=900,1032 do
    if frame<=910 and frame%2==0 and CPP_EMIT_MODE~='missing' then
      local stem=string.format('cps1-captures/frame-%08d.',frame)
      local function put(suffix,data)
        local f=assert(io.open(stem..suffix,'wb'))
        assert(f:write(data))
        assert(f:close())
      end
      -- Synthetic stand-ins for the instrumented C++ video hook.
      put('render-regs-be.bin',string.rep('R',128))
      put('buffered-obj-be.bin',string.rep('O',2048))
      if CPP_EMIT_MODE=='malformed' and frame==910 then
        put('obj-latch-count.txt','')
      elseif CPP_EMIT_MODE=='late' and frame==910 then
        -- A later callback will supply the last sidecar.
      else
        put('obj-latch-count.txt','SYNTHETIC_LATCH')
      end
    end
    if CPP_EMIT_MODE=='late' and frame==914 then
      local f=assert(io.open('cps1-captures/frame-00000910.obj-latch-count.txt','wb'))
      assert(f:write('SYNTHETIC_LATCH'))
      assert(f:close())
    end''')


@unittest.skipUnless(LIB is not None, 'Lua 5.4 shared library unavailable')
class MameLuaAutoExitTests(unittest.TestCase):
    def run_script(self, *, auto_exit, cpp_mode='complete', expected_exit=912):
        lib = ctypes.CDLL(LIB)
        lib.luaL_newstate.restype = ctypes.c_void_p
        lib.luaL_openlibs.argtypes = [ctypes.c_void_p]
        lib.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.luaL_loadstring.restype = ctypes.c_int
        lib.luaL_loadfilex.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                      ctypes.c_char_p]
        lib.luaL_loadfilex.restype = ctypes.c_int
        lib.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int,
                                  ctypes.c_longlong, ctypes.c_void_p]
        lib.lua_pcallk.restype = ctypes.c_int
        lib.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                     ctypes.c_void_p]
        lib.lua_tolstring.restype = ctypes.c_char_p
        lib.lua_close.argtypes = [ctypes.c_void_p]

        with tempfile.TemporaryDirectory() as temp, contextlib.ExitStack() as stack:
            old = Path.cwd()
            stack.callback(os.chdir, old)
            os.chdir(temp)
            output = Path('cps1-captures')
            output.mkdir()
            # Ensure tests do not rely on a host's inherited flag.
            environment = {'CPS1_DINO_AUTO_EXIT_AFTER_CAPTURE': '1'} if auto_exit else {}
            stack.enter_context(patch.dict(os.environ, environment, clear=True))
            state = lib.luaL_newstate()
            self.assertTrue(state)
            lib.luaL_openlibs(state)
            try:
                mode_prefix = 'CPP_EMIT_MODE='+repr(cpp_mode)+'\\n'
                for source, is_file in ((mode_prefix+EXIT_STUB, False),
                                        (str(SCRIPT), True)):
                    code = (
                        lib.luaL_loadfilex(state, source.encode(), None)
                        if is_file else lib.luaL_loadstring(state, source.encode())
                    )
                    self.assertEqual(code, 0, 'Lua source failed syntax check')
                    code = lib.lua_pcallk(state, 0, 0, 0, 0, None)
                    if code:
                        message = (lib.lua_tolstring(state, -1, None) or b'').decode()
                        self.fail('Lua stub failed: ' + message)
                check = (
                    'assert(exit_calls==1 and exit_frame==%d)' % expected_exit
                    if auto_exit else 'assert(exit_calls==0)'
                )
                self.assertEqual(lib.luaL_loadstring(state, check.encode()), 0)
                code = lib.lua_pcallk(state, 0, 0, 0, 0, None)
                if code:
                    self.fail((lib.lua_tolstring(state, -1, None) or b'').decode())
                files = list(output.iterdir())
                expected_cpp_files = 0 if cpp_mode=='missing' else 18
                if cpp_mode=='malformed' or cpp_mode=='late':
                    expected_cpp_files = 18 if cpp_mode=='malformed' else 18
                self.assertEqual(len(files), 36+expected_cpp_files)
                for frame in (900, 902, 904, 906, 908, 910):
                    prefix = f'frame-{frame:08d}.'
                    self.assertEqual(len([x for x in files if x.name.startswith(prefix)]),
                                     6+(0 if cpp_mode=='missing' else 3))
                self.assertFalse(any('frame-00000911' in x.name for x in files))
                self.assertFalse(any('frame-00000912' in x.name for x in files))
            finally:
                lib.lua_close(state)

    def test_auto_exit_only_after_next_frame_and_six_complete_lua_bundles(self):
        self.run_script(auto_exit=True)

    def test_delayed_cpp_sidecar_exit_after_two_complete_observations(self):
        self.run_script(auto_exit=True, cpp_mode='late', expected_exit=916)

    def test_missing_cpp_sidecars_exit_at_bounded_grace_only(self):
        self.run_script(auto_exit=True, cpp_mode='missing', expected_exit=1030)

    def test_invalid_cpp_sidecar_size_does_not_claim_readiness(self):
        self.run_script(auto_exit=True, cpp_mode='malformed', expected_exit=1030)

    def test_manual_default_does_not_schedule_exit_even_after_frame_1032(self):
        self.run_script(auto_exit=False, cpp_mode='missing')


class MameLuaAutoExitStaticTests(unittest.TestCase):
    def test_exit_is_guarded_by_explicit_flag_and_later_frame(self):
        script = SCRIPT.read_text(encoding='utf-8')
        self.assertIn("os.getenv('CPS1_DINO_AUTO_EXIT_AFTER_CAPTURE')", script)
        self.assertIn('frame>last_capture_frame and not exit_scheduled', script)
        self.assertIn('all_capture_files_size_ready()', script)
        self.assertIn('complete_metadata_streak>=2', script)
        self.assertIn('frame>=last_capture_frame+AUTO_EXIT_GRACE_FRAMES', script)
        self.assertIn("if captured==FRAME_COUNT then last_capture_frame=frame end", script)
        self.assertIn('machine:exit()', script)
        self.assertIn("if captured>=FRAME_COUNT then", script)


if __name__ == '__main__':
    unittest.main()
