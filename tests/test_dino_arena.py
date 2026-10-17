"""Host-native, ROM-free tests of the deterministic training-room scaffold.

This is an original independent placeholder sandbox, NOT dino's physics,
enemy AI, timing, sprites, combo system or a real gameplay capture.
"""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
LEFT=1;RIGHT=2;UP=4;DOWN=8;ATTACK=16;JUMP=32


class Arena(ctypes.Structure):
    _fields_=[
        ('x',ctypes.c_int32),('y',ctypes.c_int32),
        ('z',ctypes.c_int32),('vz',ctypes.c_int32),
        ('dummy_x',ctypes.c_int32),('dummy_y',ctypes.c_int32),
        ('ticks',ctypes.c_uint32),('successful_hits',ctypes.c_uint32),
        ('facing_right',ctypes.c_uint8),('dummy_hp',ctypes.c_uint8),
        ('dummy_hitstun',ctypes.c_uint8),('attack_frames',ctypes.c_uint8),
        ('attack_cooldown',ctypes.c_uint8),
    ]


@unittest.skipUnless(shutil.which('gcc'), 'Host GCC required for portable C training-room tests')
class ArenaPrototypeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='dino-arena-rom-free-')
        cls.libpath=Path(cls.temp.name)/'libdinoarena.so'
        proc=subprocess.run(
            ['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-fPIC','-shared','-Isource','source/dino_arena.c',
             '-o',str(cls.libpath)],
            cwd=ROOT,check=False,capture_output=True,text=True)
        if proc.returncode:
            raise AssertionError('portable native C compiler failure: '+proc.stderr)
        cls.lib=ctypes.CDLL(str(cls.libpath))
        cls.lib.dino_arena_reset.argtypes=[ctypes.POINTER(Arena)]
        cls.lib.dino_arena_step.argtypes=[
            ctypes.POINTER(Arena),ctypes.c_uint32,ctypes.c_uint32]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def new(self):
        p=Arena()
        self.lib.dino_arena_reset(ctypes.byref(p))
        return p

    def step(self,p,held=0,pressed=0):
        self.lib.dino_arena_step(ctypes.byref(p),held,pressed)

    def test_reset_initial_state_is_reproducible_and_has_no_rom_requirements(self):
        p=self.new()
        self.assertEqual((p.x,p.y,p.z,p.vz),(90,151,0,0))
        self.assertEqual((p.dummy_x,p.dummy_y,p.dummy_hp),(250,151,3))
        self.assertEqual((p.ticks,p.successful_hits,p.facing_right),(0,0,1))
        self.step(p,RIGHT|DOWN,ATTACK)
        self.lib.dino_arena_reset(ctypes.byref(p))
        self.assertEqual((p.x,p.y,p.z,p.dummy_hp,p.ticks),(90,151,0,3,0))

    def test_integer_movement_bounds_and_facing(self):
        p=self.new()
        for _ in range(200):self.step(p,LEFT|UP)
        self.assertEqual((p.x,p.y,p.facing_right),(16,80,0))
        for _ in range(400):self.step(p,RIGHT|DOWN)
        self.assertEqual((p.x,p.y,p.facing_right),(368,208,1))

    def test_opposite_inputs_cancel_and_unknown_mask_ignored(self):
        p=self.new()
        self.step(p,LEFT|RIGHT|UP|DOWN)
        self.assertEqual((p.x,p.y,p.facing_right),(90,151,1))
        self.step(p,0xffff0000,0xffff0000)
        self.assertEqual((p.x,p.y,p.z,p.dummy_hp),(90,151,0,3))
        self.assertEqual(p.ticks,2)

    def test_diagonal_movement_and_facing_are_deterministic(self):
        p=self.new()
        self.step(p,RIGHT|DOWN)
        self.assertEqual((p.x,p.y,p.facing_right),(92,152,1))
        self.step(p,LEFT|UP)
        self.assertEqual((p.x,p.y,p.facing_right),(90,151,0))

    def test_jump_lands_and_airborne_jump_cannot_restart(self):
        p=self.new()
        self.step(p,pressed=JUMP)
        self.assertEqual((p.z,p.vz),(8,7))
        self.step(p,pressed=JUMP)
        self.assertEqual((p.z,p.vz),(15,6))
        heights=[p.z]
        for _ in range(30):
            self.step(p,pressed=JUMP if p.z else 0)
            heights.append(p.z)
            if p.z==0:break
        self.assertGreater(max(heights),20)
        self.assertEqual((p.z,p.vz),(0,0))
        self.step(p,pressed=JUMP)
        self.assertGreater(p.z,0)

    def test_frontal_range_and_depth_lane_hit(self):
        p=self.new()
        p.x=219
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.dummy_hp,p.successful_hits),(2,1))
        self.assertEqual(p.dummy_hitstun,9)
        self.assertEqual((p.attack_frames,p.attack_cooldown),(8,15))

    def test_facing_away_and_wrong_lane_do_not_hit(self):
        p=self.new()
        p.x=230;p.facing_right=0
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.dummy_hp,p.successful_hits),(3,0))
        p=self.new()
        p.x=230;p.y=180
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.dummy_hp,p.successful_hits),(3,0))
        p=self.new()
        p.x=100
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.dummy_hp,p.successful_hits),(3,0))

    def test_repeated_button_edges_obey_cooldown(self):
        p=self.new();p.x=230
        self.step(p,pressed=ATTACK)
        for _ in range(14):
            self.step(p,pressed=ATTACK)
        self.assertEqual((p.dummy_hp,p.successful_hits),(2,1))
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.dummy_hp,p.successful_hits),(1,2))

    def test_dummy_stops_at_zero_health_and_can_be_reset(self):
        p=self.new();p.x=230
        for _ in range(5):
            self.step(p,pressed=ATTACK)
            for __ in range(15):
                self.step(p)
        self.assertEqual((p.dummy_hp,p.successful_hits),(0,3))
        self.lib.dino_arena_reset(ctypes.byref(p))
        self.assertEqual((p.dummy_hp,p.successful_hits),(3,0))

    def test_high_jump_attacks_cannot_hit_grounded_dummy(self):
        p=self.new();p.x=230
        for i in range(4):self.step(p,pressed=JUMP if i==0 else 0)
        self.assertGreater(p.z,20)
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.dummy_hp,p.successful_hits),(3,0))

    def test_same_inputs_produce_identical_300_tick_replays(self):
        p=self.new();q=self.new()
        for frame in range(300):
            held=(RIGHT if frame%40<20 else LEFT) | (DOWN if frame%9<5 else UP)
            pressed=(ATTACK if frame%31==0 else 0)|(JUMP if frame%47==0 else 0)
            self.step(p,held,pressed);self.step(q,held,pressed)
        fields=[name for name,_ in Arena._fields_]
        self.assertEqual(tuple(getattr(p,k) for k in fields),
                         tuple(getattr(q,k) for k in fields))
        self.assertEqual(p.ticks,300)

    def test_null_pointer_is_safe_for_both_native_functions(self):
        self.lib.dino_arena_reset(None)
        self.lib.dino_arena_step(None,RIGHT,ATTACK)


if __name__=='__main__':
    unittest.main()
