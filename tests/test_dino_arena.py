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
LEFT=1;RIGHT=2;UP=4;DOWN=8;ATTACK=16;JUMP=32;SPAR=64


class Arena(ctypes.Structure):
    _fields_=[
        ('x',ctypes.c_int32),('y',ctypes.c_int32),
        ('z',ctypes.c_int32),('vz',ctypes.c_int32),
        ('dummy_x',ctypes.c_int32),('dummy_y',ctypes.c_int32),
        ('ticks',ctypes.c_uint32),('successful_hits',ctypes.c_uint32),
        ('facing_right',ctypes.c_uint8),('dummy_hp',ctypes.c_uint8),
        ('dummy_hitstun',ctypes.c_uint8),('attack_frames',ctypes.c_uint8),
        ('attack_cooldown',ctypes.c_uint8),
        ('sparring',ctypes.c_uint8),('player_hp',ctypes.c_uint8),
        ('player_hitstun',ctypes.c_uint8),('player_invuln',ctypes.c_uint8),
        ('dummy_windup',ctypes.c_uint8),('dummy_cooldown',ctypes.c_uint8),
        ('dummy_attack_frames',ctypes.c_uint8),
        ('dummy_facing_right',ctypes.c_uint8),
        ('player_hits_taken',ctypes.c_uint8),
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

    def test_optional_sparring_defaults_off_and_toggles_explicitly(self):
        p=self.new()
        self.assertFalse(p.sparring)
        self.assertEqual(p.player_hp,5)
        self.assertEqual(p.dummy_hp,3)
        self.step(p)
        self.assertEqual(p.dummy_x,250)
        self.step(p,pressed=SPAR)
        self.assertTrue(p.sparring)
        self.assertEqual((p.player_hp,p.dummy_hp),(5,3))
        self.step(p,pressed=SPAR)
        self.assertFalse(p.sparring)
        self.assertEqual((p.dummy_windup,p.dummy_attack_frames),(0,0))

    def test_sparring_enemy_chases_without_overlapping_player(self):
        p=self.new()
        self.step(p,pressed=SPAR)
        self.assertEqual(p.dummy_x,249)
        for _ in range(40):self.step(p)
        self.assertEqual(p.dummy_x,209)
        self.assertGreaterEqual(abs(p.dummy_x-p.x),14)
        self.assertEqual((p.dummy_y,p.player_hp),(151,5))

    def test_same_lane_body_collision_prevents_crossing(self):
        p=self.new();p.x=235
        self.step(p,pressed=SPAR)
        for _ in range(20):self.step(p,held=RIGHT)
        self.assertEqual(p.x,236)
        self.assertGreaterEqual(p.dummy_x-p.x,14)
        self.assertEqual(p.y,151)

    def test_different_depth_lane_can_pass_opponent(self):
        p=self.new();p.x=235;p.y=185
        self.step(p,pressed=SPAR)
        for _ in range(15):self.step(p,held=RIGHT)
        self.assertGreater(p.x,250)

    def test_enemy_telegraph_then_single_damage_and_invulnerability(self):
        p=self.new();p.x=220
        self.step(p,pressed=SPAR)
        self.assertEqual(p.dummy_windup,12)
        for _ in range(11):self.step(p)
        self.assertEqual((p.player_hp,p.player_hits_taken),(5,0))
        self.step(p)
        self.assertEqual((p.player_hp,p.player_hits_taken),(4,1))
        self.assertEqual(p.player_invuln,30)
        self.assertEqual(p.dummy_attack_frames,7)
        for _ in range(25):self.step(p)
        self.assertEqual((p.player_hp,p.player_hits_taken),(4,1))

    def test_moving_away_after_telegraph_dodges_attack(self):
        p=self.new();p.x=210
        self.step(p,pressed=SPAR)
        self.assertEqual(p.dummy_windup,12)
        for _ in range(12):self.step(p,held=LEFT)
        self.assertEqual(p.player_hp,5)
        self.assertEqual(p.dummy_windup,0)
        self.assertGreater(abs(p.x-p.dummy_x),44)

    def test_jump_during_telegraph_dodges_attack(self):
        p=self.new();p.x=220
        self.step(p,pressed=SPAR)
        for i in range(12):self.step(p,pressed=JUMP if i==0 else 0)
        self.assertGreater(p.z,20)
        self.assertEqual((p.player_hp,p.player_hits_taken),(5,0))

    def test_player_hit_interrupts_enemy_attack_and_stuns(self):
        p=self.new();p.x=220
        self.step(p,pressed=SPAR)
        self.assertEqual(p.dummy_windup,12)
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.dummy_hp,p.successful_hits),(2,1))
        self.assertEqual((p.dummy_windup,p.dummy_hitstun),(0,9))
        for _ in range(7):self.step(p)
        self.assertEqual(p.player_hp,5)

    def test_player_ko_freezes_controls_until_reset(self):
        p=self.new();p.x=220
        self.step(p,pressed=SPAR)
        for _ in range(400):
            self.step(p)
            if p.player_hp==0:break
        self.assertEqual((p.player_hp,p.player_hits_taken),(0,5))
        x=p.x
        self.step(p,held=LEFT,pressed=ATTACK|JUMP)
        self.assertEqual((p.x,p.z,p.attack_frames),(x,0,0))
        self.lib.dino_arena_reset(ctypes.byref(p))
        self.assertEqual((p.player_hp,p.dummy_hp,p.sparring),(5,3,0))

    def test_dead_enemy_cannot_telegraph_or_damage(self):
        p=self.new();p.x=220
        self.step(p,pressed=SPAR)
        for _ in range(3):
            self.step(p,pressed=ATTACK)
            for __ in range(15):self.step(p)
        self.assertEqual(p.dummy_hp,0)
        self.assertEqual(p.dummy_windup,0)
        hp=p.player_hp
        for _ in range(120):self.step(p)
        self.assertEqual(p.player_hp,hp)

    def test_sparring_700_tick_replay_is_byte_identical(self):
        p=self.new();q=self.new()
        for t in range(700):
            held=(RIGHT if t%71<34 else LEFT)|(UP if t%39<17 else DOWN)
            pressed=(SPAR if t in (0,350) else 0)
            pressed|=(ATTACK if t%19==0 else 0)
            pressed|=(JUMP if t%53==0 else 0)
            self.step(p,held,pressed)
            self.step(q,held,pressed)
        values=[name for name,_ in Arena._fields_]
        self.assertEqual(tuple(getattr(p,k) for k in values),
                         tuple(getattr(q,k) for k in values))
        self.assertEqual(p.ticks,700)

    def test_null_pointer_is_safe_for_both_native_functions(self):
        self.lib.dino_arena_reset(None)
        self.lib.dino_arena_step(None,RIGHT,ATTACK)


if __name__=='__main__':
    unittest.main()
