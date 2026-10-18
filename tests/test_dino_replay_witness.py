"""Independent endianness-stable witness for the exact host/Switch replay.

Executes real original training C, never original game ROMs or emulation.
A Python little-endian reference detects changes to the C hash contract.
"""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_dino_arena import Arena
from tools import dino_host_preview as host

ROOT=Path(__file__).resolve().parents[1]
START=14695981039346656037
PRIME=1099511628211
MASK=(1<<64)-1


def independent_tick(hash_value,a,player_pose,enemy_pose):
    fields=(a.ticks,a.x,a.y,a.z,a.vz,a.dummy_x,a.dummy_y,
            a.successful_hits,a.events,a.player_hp,a.dummy_hp,
            a.combo_hits,a.sparring,player_pose,enemy_pose)
    for field in fields:
        for b in (int(field)&0xffffffff).to_bytes(4,'little'):
            hash_value=((hash_value^b)*PRIME)&MASK
    return hash_value


@unittest.skipUnless(shutil.which('gcc'),'Host GCC needed for replay checks')
class ReplayWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dino-replay-witness-')
        output=Path(cls.tmp.name)/'libwitness.so'
        proc=subprocess.run(
            ['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-shared','-fPIC','-Isource',
             'source/dino_arena.c','source/dino_replay.c',
             'source/dino_replay_witness.c','-o',str(output)],
            cwd=ROOT,capture_output=True,text=True,check=False)
        if proc.returncode:
            raise AssertionError('Witness C failed to compile: '+proc.stderr)
        cls.dll=ctypes.CDLL(str(output))
        pointer=ctypes.POINTER(Arena)
        cls.dll.dino_arena_reset.argtypes=[pointer]
        cls.dll.dino_arena_step.argtypes=[
            pointer,ctypes.c_uint32,ctypes.c_uint32]
        cls.dll.dino_replay_input.argtypes=[
            ctypes.c_uint32,ctypes.POINTER(ctypes.c_uint32),
            ctypes.POINTER(ctypes.c_uint32)]
        cls.dll.dino_replay_input.restype=ctypes.c_bool
        cls.dll.dino_arena_player_pose.argtypes=[pointer]
        cls.dll.dino_arena_player_pose.restype=ctypes.c_int
        cls.dll.dino_arena_dummy_pose.argtypes=[pointer]
        cls.dll.dino_arena_dummy_pose.restype=ctypes.c_int
        cls.dll.dino_replay_witness_tick.argtypes=[ctypes.c_uint64,pointer]
        cls.dll.dino_replay_witness_tick.restype=ctypes.c_uint64

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def replay(self,override=None):
        arena=Arena()
        self.dll.dino_arena_reset(ctypes.byref(arena))
        h=START
        for t in range(180):
            held=ctypes.c_uint32()
            pressed=ctypes.c_uint32()
            self.assertTrue(self.dll.dino_replay_input(
                t,ctypes.byref(held),ctypes.byref(pressed)))
            if override is not None and t==override:
                held.value=0
                pressed.value=0
            self.dll.dino_arena_step(
                ctypes.byref(arena),held.value,pressed.value)
            h=self.dll.dino_replay_witness_tick(
                h,ctypes.byref(arena))
        return arena,h

    def test_c_witness_matches_independent_python_after_every_tick(self):
        arena=Arena()
        self.dll.dino_arena_reset(ctypes.byref(arena))
        c_hash=py_hash=START
        for tick in range(180):
            held=ctypes.c_uint32()
            pressed=ctypes.c_uint32()
            self.assertTrue(self.dll.dino_replay_input(
                tick,ctypes.byref(held),ctypes.byref(pressed)))
            self.dll.dino_arena_step(
                ctypes.byref(arena),held.value,pressed.value)
            c_hash=self.dll.dino_replay_witness_tick(
                c_hash,ctypes.byref(arena))
            py_hash=independent_tick(
                py_hash,arena,
                self.dll.dino_arena_player_pose(ctypes.byref(arena)),
                self.dll.dino_arena_dummy_pose(ctypes.byref(arena)))
            self.assertEqual(c_hash,py_hash,f'drift at tick {tick}')
        self.assertEqual((arena.ticks,arena.x,arena.player_hp,
                          arena.successful_hits),(180,230,4,3))

    def test_canonical_witness_matches_actual_native_host_bridge(self):
        arena,digest=self.replay()
        result=host.headless(180)
        self.assertEqual(result['gameplay_witness_fnv64'],f'{digest:016x}')
        self.assertEqual(result['ticks'],arena.ticks)
        self.assertFalse(result['switch_emulator_verified'])

    def test_one_changed_control_tick_changes_witness(self):
        baseline=self.replay()[1]
        for tick in (0,75,90,130,155):
            with self.subTest(tick=tick):
                changed=self.replay(override=tick)[1]
                self.assertNotEqual(baseline,changed)

    def test_replay_is_stable_across_independent_reset_runs(self):
        first=self.replay()[1]
        second=self.replay()[1]
        self.assertEqual(first,second)
        self.assertNotEqual(first,START)

    def test_null_pointer_leaves_hash_unmodified(self):
        for digest in (0,1,START,0xffffffffffffffff):
            with self.subTest(digest=digest):
                self.assertEqual(
                    self.dll.dino_replay_witness_tick(digest,None),
                    digest)


if __name__=='__main__':
    unittest.main()
