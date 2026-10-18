"""Executable C replay checks: identical 180 input ticks for native host + NRO.

All inputs are self-authored integer masks; no commercial game ROM, MAME
data, switch firmware, capture files, or runtime emulator is used.
"""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import dino_host_preview as host

ROOT=Path(__file__).resolve().parents[1]
TICKS=180


@unittest.skipUnless(shutil.which('gcc'), 'GCC required for portable C replay tests')
class NativeReplayContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dino-replay-c-test-')
        binary=Path(cls.tmp.name)/'libreplay.so'
        p=subprocess.run(
            ['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-shared','-fPIC','-Isource',
             'source/dino_replay.c','-o',str(binary)],
            cwd=ROOT,capture_output=True,text=True,check=False)
        if p.returncode:
            raise AssertionError('Portable replay failed to compile: '+p.stderr)
        cls.dll=ctypes.CDLL(str(binary))
        cls.dll.dino_replay_input.argtypes=[
            ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32)]
        cls.dll.dino_replay_input.restype=ctypes.c_bool

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def controls(self,tick):
        held=ctypes.c_uint32(0)
        pressed=ctypes.c_uint32(0)
        ok=self.dll.dino_replay_input(
            tick,ctypes.byref(held),ctypes.byref(pressed))
        return ok,held.value,pressed.value

    def test_all_180_ticks_valid_and_look_only_like_training_buttons(self):
        for tick in range(TICKS):
            ok,held,pressed=self.controls(tick)
            self.assertTrue(ok)
            self.assertEqual(held & ~15,0)
            self.assertEqual(pressed & ~112,0)

    def test_movement_and_all_single_shot_actions_at_exact_ticks(self):
        self.assertEqual([i for i in range(TICKS)
                          if self.controls(i)[1] & host.RIGHT],
                         list(range(70)))
        self.assertEqual([i for i in range(TICKS)
                          if self.controls(i)[2] & host.ATTACK],
                         [75,90,105,148])
        self.assertEqual([i for i in range(TICKS)
                          if self.controls(i)[2] & host.SPAR],[130])
        self.assertEqual([i for i in range(TICKS)
                          if self.controls(i)[2] & host.JUMP],[155])

    def test_trace_bounds_and_null_pointers_do_not_modify_outputs(self):
        for t in (TICKS,TICKS+1,2**32-1):
            held=ctypes.c_uint32(0xfeed)
            pressed=ctypes.c_uint32(0xbeef)
            self.assertFalse(self.dll.dino_replay_input(
                t,ctypes.byref(held),ctypes.byref(pressed)))
            self.assertEqual((held.value,pressed.value),(0xfeed,0xbeef))
        out=ctypes.c_uint32(55)
        self.assertFalse(self.dll.dino_replay_input(2,None,ctypes.byref(out)))
        self.assertFalse(self.dll.dino_replay_input(2,ctypes.byref(out),None))
        self.assertEqual(out.value,55)

    def test_same_c_trace_replayed_as_host_demo_step_has_known_state(self):
        engine=host.HostArena()
        try:
            for t in range(TICKS):
                ok,held,pressed=self.controls(t)
                self.assertTrue(ok)
                engine.step(held,pressed)
            direct=engine.status()
            frame_direct=engine.render_rgb()
            engine.reset()
            for t in range(TICKS):
                engine.demo_step(t)
            via_shared=engine.status()
            self.assertEqual((direct.x,direct.y,direct.ticks),
                             (via_shared.x,via_shared.y,via_shared.ticks))
            self.assertEqual((direct.player_hp,direct.dummy_hp
                              if hasattr(direct,'dummy_hp') else direct.enemy_hp,
                              direct.successful_hits,direct.pcm_digest),
                             (via_shared.player_hp,via_shared.enemy_hp,
                              via_shared.successful_hits,via_shared.pcm_digest))
            self.assertEqual(frame_direct,engine.render_rgb())
            self.assertEqual((direct.ticks,direct.x,direct.player_hp,
                              direct.successful_hits,direct.sparring),
                             (180,230,4,3,1))
        finally:
            engine.close()

    def test_end_of_replay_is_not_a_hidden_gameplay_tick(self):
        engine=host.HostArena()
        try:
            for i in range(TICKS):engine.demo_step(i)
            a=engine.status()
            first=engine.render_rgb()
            engine.demo_step(TICKS)
            engine.demo_step(0xffffffff)
            b=engine.status()
            self.assertEqual(a.ticks,b.ticks)
            self.assertEqual(a.pcm_digest,b.pcm_digest)
            self.assertEqual(a.successful_hits,b.successful_hits)
            self.assertEqual(first,engine.render_rgb())
        finally:
            engine.close()


if __name__=='__main__':
    unittest.main()
