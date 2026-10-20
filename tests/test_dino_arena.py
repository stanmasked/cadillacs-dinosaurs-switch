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
LEFT=1;RIGHT=2;UP=4;DOWN=8;ATTACK=16;JUMP=32;SPAR=64;COUNTER=128
SPAR_TOGGLE=1;JUMP_START=2;LAND=4;SWING=8;DUMMY_HIT=16
FINISHER=32;DUMMY_KO=64;DUMMY_SWING=128;PLAYER_HIT=256
PLAYER_KO=512;DODGE=1024


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
        ('player_moving',ctypes.c_uint8),
        ('dummy_moving',ctypes.c_uint8),
        ('combo_hits',ctypes.c_uint8),
        ('combo_timer',ctypes.c_uint8),
        ('finisher_flash',ctypes.c_uint8),
        ('dummy_impact_flash',ctypes.c_uint8),
        ('player_impact_flash',ctypes.c_uint8),
        ('events',ctypes.c_uint32),
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
        cls.lib.dino_arena_player_pose.argtypes=[ctypes.POINTER(Arena)]
        cls.lib.dino_arena_player_pose.restype=ctypes.c_int
        cls.lib.dino_arena_dummy_pose.argtypes=[ctypes.POINTER(Arena)]
        cls.lib.dino_arena_dummy_pose.restype=ctypes.c_int
        cls.lib.dino_arena_pose_phase.argtypes=[ctypes.POINTER(Arena)]
        cls.lib.dino_arena_pose_phase.restype=ctypes.c_uint8

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

    def natural_counter_windup(self,p):
        """Start from reset: AI walks ~116 ticks; never seed x/windup."""
        self.assertEqual((p.x,p.dummy_x,p.ticks),(90,250,0))
        self.step(p,pressed=SPAR)
        self.assertTrue(p.sparring)
        self.assertEqual(p.events,SPAR_TOGGLE)
        for _ in range(200):
            if p.dummy_windup:
                break
            self.step(p)
        else:
            self.fail('natural sparring AI never reached its windup')
        # Genuine pursuit from 250 to 134, not the staged x=220 probe.
        self.assertEqual((p.ticks,p.x,p.dummy_x),(116,90,134))
        self.assertEqual((p.dummy_windup,p.dummy_cooldown),(12,0))
        self.assertEqual((p.player_hp,p.dummy_hp,p.successful_hits),(5,3,0))
        self.assertEqual(p.facing_right,1)

    def test_natural_pursuit_windup_then_pressed_counter_prevents_damage(self):
        p=self.new()
        self.natural_counter_windup(p)
        self.step(p,pressed=COUNTER)
        self.assertEqual(p.ticks,117)
        self.assertEqual(p.events,1<<11)
        self.assertEqual((p.dummy_windup,p.dummy_hitstun,
                          p.dummy_cooldown),(0,9,48))
        self.assertEqual((p.player_hp,p.dummy_hp,p.player_hits_taken),(5,3,0))
        self.assertEqual((p.successful_hits,p.dummy_impact_flash),(0,6))
        # Repeated ZR during stun/cooldown does not grant extra counters.
        self.step(p,pressed=COUNTER)
        self.assertFalse(p.events & (1<<11))
        self.assertEqual((p.dummy_cooldown,p.dummy_hp),(47,3))

    def test_natural_premature_counter_does_not_buffer_until_enemy_windup(self):
        p=self.new()
        self.step(p,pressed=SPAR)
        self.step(p,pressed=COUNTER)  # enemy is still far away
        self.assertEqual(p.ticks,2)
        self.assertFalse(p.events & (1<<11))
        self.assertEqual((p.player_hp,p.dummy_hp),(5,3))
        for _ in range(200):
            if p.dummy_windup:
                break
            self.step(p)
        else:
            self.fail('AI never initiated its original windup')
        self.assertEqual((p.ticks,p.dummy_windup),(116,12))
        for _ in range(12):
            self.step(p)  # do NOT inject another ZR edge
        self.assertEqual(p.ticks,128)
        self.assertEqual(p.events,DUMMY_SWING|PLAYER_HIT)
        self.assertEqual((p.player_hp,p.player_hits_taken),(4,1))
        self.assertFalse(p.events & (1<<11))

    def test_natural_last_windup_tick_vs_late_post_impact_edge(self):
        saved=self.new()
        missed=self.new()
        self.natural_counter_windup(saved)
        self.natural_counter_windup(missed)
        for _ in range(11):
            self.step(saved)
            self.step(missed)
        self.assertEqual((saved.ticks,saved.dummy_windup),(127,1))
        self.assertEqual((missed.ticks,missed.dummy_windup),(127,1))
        self.step(saved,pressed=COUNTER)  # last valid tick
        self.step(missed)                 # enemy lands its strike
        self.assertEqual(saved.events,1<<11)
        self.assertEqual(saved.player_hp,5)
        self.assertEqual(missed.events,DUMMY_SWING|PLAYER_HIT)
        self.assertEqual(missed.player_hp,4)
        self.step(missed,pressed=COUNTER) # already stunned, too late
        self.assertFalse(missed.events & (1<<11))
        self.assertEqual(missed.player_hp,4)

    def test_natural_counter_replay_is_identical_from_fresh_reset(self):
        p=self.new()
        q=self.new()
        self.natural_counter_windup(p)
        self.natural_counter_windup(q)
        for tick in range(110):
            pressed=COUNTER if tick in (0,1,48,49,60) else 0
            self.step(p,pressed=pressed)
            self.step(q,pressed=pressed)
            self.assertEqual(p.events,q.events)
            self.assertEqual(
                tuple(getattr(p,name) for name,_ in Arena._fields_),
                tuple(getattr(q,name) for name,_ in Arena._fields_))
        self.assertEqual((p.ticks,q.ticks),(226,226))

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

    def test_pose_api_is_idle_by_default_and_handles_null(self):
        p=self.new()
        self.assertEqual(self.lib.dino_arena_player_pose(ctypes.byref(p)),0)
        self.assertEqual(self.lib.dino_arena_dummy_pose(ctypes.byref(p)),0)
        self.assertEqual(self.lib.dino_arena_pose_phase(ctypes.byref(p)),0)
        self.assertEqual(self.lib.dino_arena_player_pose(None),5)
        self.assertEqual(self.lib.dino_arena_dummy_pose(None),5)
        self.assertEqual(self.lib.dino_arena_pose_phase(None),0)

    def test_actual_player_displacement_drives_walk_pose_not_held_button(self):
        p=self.new()
        self.step(p,held=RIGHT)
        self.assertEqual((p.player_moving,
                          self.lib.dino_arena_player_pose(ctypes.byref(p))),(1,1))
        self.step(p)
        self.assertEqual((p.player_moving,
                          self.lib.dino_arena_player_pose(ctypes.byref(p))),(0,0))
        p.x=368
        self.step(p,held=RIGHT)
        self.assertEqual(p.player_moving,0)
        self.assertEqual(self.lib.dino_arena_player_pose(ctypes.byref(p)),0)

    def test_jump_and_attack_poses_have_explicit_priority(self):
        p=self.new()
        self.step(p,held=RIGHT,pressed=JUMP)
        self.assertEqual(self.lib.dino_arena_player_pose(ctypes.byref(p)),2)
        self.step(p,held=RIGHT,pressed=ATTACK)
        self.assertEqual(self.lib.dino_arena_player_pose(ctypes.byref(p)),3)
        for _ in range(8):self.step(p)
        self.assertEqual(self.lib.dino_arena_player_pose(ctypes.byref(p)),2)
        for _ in range(20):self.step(p)
        self.assertEqual(self.lib.dino_arena_player_pose(ctypes.byref(p)),0)

    def test_enemy_pursuit_and_windup_pose_transitions(self):
        p=self.new()
        self.step(p,pressed=SPAR)
        self.assertEqual((p.dummy_moving,
                          self.lib.dino_arena_dummy_pose(ctypes.byref(p))),(1,1))
        p.x=220
        self.step(p)
        self.assertEqual(self.lib.dino_arena_dummy_pose(ctypes.byref(p)),6)
        for _ in range(12):self.step(p)
        self.assertEqual(self.lib.dino_arena_dummy_pose(ctypes.byref(p)),3)
        self.assertEqual(self.lib.dino_arena_player_pose(ctypes.byref(p)),4)

    def test_damage_reaction_wins_over_previous_attack_frames(self):
        p=self.new();p.x=220
        self.step(p,pressed=SPAR)
        self.step(p,pressed=ATTACK)
        self.assertEqual(self.lib.dino_arena_dummy_pose(ctypes.byref(p)),4)
        self.assertEqual(self.lib.dino_arena_player_pose(ctypes.byref(p)),3)
        self.assertEqual(p.dummy_windup,0)

    def test_ko_wins_over_every_other_animation_flag(self):
        p=self.new()
        p.player_hp=0
        p.player_hitstun=5
        p.attack_frames=4
        p.z=17
        p.player_moving=1
        p.dummy_hp=0
        p.dummy_hitstun=5
        p.dummy_windup=8
        p.dummy_attack_frames=2
        p.dummy_moving=1
        self.assertEqual(self.lib.dino_arena_player_pose(ctypes.byref(p)),5)
        self.assertEqual(self.lib.dino_arena_dummy_pose(ctypes.byref(p)),5)

    def test_pose_phase_changes_only_on_six_tick_boundaries(self):
        p=self.new()
        for tick in range(25):
            self.assertEqual(self.lib.dino_arena_pose_phase(ctypes.byref(p)),
                             (tick//6)&1)
            self.step(p)
        self.assertEqual(p.ticks,25)

    def test_pose_queries_never_modify_simulation_state(self):
        p=self.new()
        self.step(p,held=RIGHT|DOWN,pressed=SPAR|JUMP)
        before=tuple(getattr(p,key) for key,_ in Arena._fields_)
        for _ in range(20):
            self.lib.dino_arena_player_pose(ctypes.byref(p))
            self.lib.dino_arena_dummy_pose(ctypes.byref(p))
            self.lib.dino_arena_pose_phase(ctypes.byref(p))
        after=tuple(getattr(p,key) for key,_ in Arena._fields_)
        self.assertEqual(before,after)

    def test_movement_flags_clear_after_ko_and_hitstun(self):
        p=self.new();p.x=220
        self.step(p,pressed=SPAR)
        for _ in range(12):self.step(p)
        self.assertEqual(self.lib.dino_arena_player_pose(ctypes.byref(p)),4)
        self.step(p,held=LEFT)
        self.assertEqual(p.player_moving,0)
        p.player_hp=0
        self.step(p,held=LEFT)
        self.assertEqual(p.player_moving,0)
        self.assertEqual(self.lib.dino_arena_player_pose(ctypes.byref(p)),5)

    def test_combo_starts_only_after_confirmed_hit(self):
        p=self.new()
        self.assertEqual((p.combo_hits,p.combo_timer,p.finisher_flash),(0,0,0))
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.combo_hits,p.combo_timer),(0,0))
        for _ in range(14):self.step(p)
        p.x=230
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.combo_hits,p.combo_timer),(1,24))
        self.assertEqual(p.dummy_hp,2)

    def test_combo_cooldown_inputs_and_misses_do_not_refresh_window(self):
        p=self.new();p.x=230
        self.step(p,pressed=ATTACK)
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.combo_hits,p.combo_timer),(1,23))
        p.x=100
        for _ in range(13):self.step(p)
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.combo_hits,p.combo_timer),(1,9))
        self.assertEqual(p.dummy_hp,2)

    def test_exact_twenty_four_tick_combo_expiry(self):
        p=self.new();p.x=230
        self.step(p,pressed=ATTACK)
        for i in range(23):
            self.step(p)
            self.assertEqual(p.combo_hits,1)
        self.assertEqual(p.combo_timer,1)
        self.step(p)
        self.assertEqual((p.combo_hits,p.combo_timer),(0,0))
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.combo_hits,p.combo_timer),(1,24))

    def test_three_landed_hits_trigger_single_sparring_knockback(self):
        p=self.new();p.x=230
        self.step(p,pressed=SPAR)
        p.dummy_hp=6
        start=p.dummy_x
        for index in range(3):
            self.step(p,pressed=ATTACK)
            self.assertEqual((p.combo_hits,p.dummy_hp),(index+1,5-index))
            if index<2:
                self.assertEqual(p.dummy_x,start)
                for _ in range(14):self.step(p)
        self.assertEqual(p.dummy_x,start+18)
        self.assertEqual(p.dummy_moving,1)
        self.assertEqual((p.combo_hits,p.finisher_flash,p.dummy_hitstun),
                         (3,10,14))
        self.assertEqual(p.successful_hits,3)

    def test_left_facing_finisher_knocks_back_in_opposite_direction(self):
        p=self.new();p.x=270;p.facing_right=0
        self.step(p,pressed=SPAR)
        p.dummy_hp=6
        start=p.dummy_x
        for index in range(3):
            self.step(p,pressed=ATTACK)
            if index<2:
                for _ in range(14):self.step(p)
        self.assertEqual(p.dummy_x,start-18)
        self.assertEqual(p.combo_hits,3)
        self.assertEqual(p.dummy_hp,3)

    def test_finisher_knockback_clamps_to_arena_edge(self):
        p=self.new();p.x=337
        self.step(p,pressed=SPAR)
        p.dummy_x=360
        p.dummy_hp=6
        p.combo_hits=2
        p.combo_timer=10
        self.step(p,pressed=ATTACK)
        self.assertEqual((p.dummy_x,p.combo_hits),(368,3))
        self.assertLessEqual(p.dummy_x,368)

    def test_fourth_hit_does_not_repeat_combo_finisher(self):
        p=self.new();p.x=230
        self.step(p,pressed=SPAR)
        p.dummy_hp=7
        for index in range(4):
            self.step(p,pressed=ATTACK)
            if index==2:
                # Keep the opponent fixed between the finisher and the
                # fourth hit to distinguish AI pursuit from knockback.
                p.dummy_hitstun=40
            if index<3:
                for _ in range(14):self.step(p)
        self.assertEqual(p.combo_hits,3)
        self.assertEqual(p.dummy_hp,3)
        self.assertEqual(p.dummy_x,268)
        self.assertEqual(p.successful_hits,4)

    def test_no_spar_mode_keeps_static_dummy_in_place(self):
        p=self.new();p.x=230
        for index in range(3):
            self.step(p,pressed=ATTACK)
            if index<2:
                for _ in range(14):self.step(p)
        self.assertEqual((p.combo_hits,p.dummy_hp,p.dummy_x),(3,0,250))
        self.assertEqual(p.finisher_flash,10)

    def test_sparring_toggle_discards_prior_combo(self):
        p=self.new();p.x=230
        self.step(p,pressed=ATTACK)
        self.assertEqual(p.combo_hits,1)
        self.step(p,pressed=SPAR)
        self.assertEqual((p.combo_hits,p.combo_timer,p.finisher_flash),(0,0,0))
        self.step(p,pressed=SPAR)
        self.assertEqual((p.combo_hits,p.combo_timer,p.finisher_flash),(0,0,0))

    def test_enemy_damage_breaks_player_combo(self):
        p=self.new();p.x=220
        self.step(p,pressed=SPAR)
        self.step(p,pressed=ATTACK)
        self.assertEqual(p.combo_hits,1)
        # A synthetic short enemy cooldown independent of player attack.
        p.dummy_hitstun=0
        p.dummy_windup=1
        self.step(p)
        self.assertEqual((p.player_hp,p.player_hits_taken),(4,1))
        self.assertEqual((p.combo_hits,p.combo_timer,p.finisher_flash),(0,0,0))

    def test_finisher_flash_expires_without_mutating_combo_state(self):
        p=self.new();p.x=230
        for index in range(3):
            self.step(p,pressed=ATTACK)
            if index<2:
                for _ in range(14):self.step(p)
        self.assertEqual((p.finisher_flash,p.combo_hits),(10,3))
        for _ in range(10):self.step(p)
        self.assertEqual((p.finisher_flash,p.combo_hits),(0,3))
        for _ in range(14):self.step(p)
        self.assertEqual((p.finisher_flash,p.combo_hits,p.combo_timer),(0,0,0))

    def test_combo_replay_1000_ticks_is_byte_identical(self):
        a=self.new();b=self.new()
        for tick in range(1000):
            held=(RIGHT if tick%91<43 else LEFT) | (UP if tick%51<19 else DOWN)
            pressed=(ATTACK if tick%16==0 else 0) | (
                JUMP if tick%57==0 else 0) | (
                SPAR if tick in (0,370,620,850) else 0)
            self.step(a,held,pressed)
            self.step(b,held,pressed)
        fields=[name for name,_ in Arena._fields_]
        self.assertEqual(tuple(getattr(a,k) for k in fields),
                         tuple(getattr(b,k) for k in fields))
        self.assertEqual(a.ticks,1000)

    def test_event_mask_is_empty_on_reset_idle_and_one_tick_later(self):
        p=self.new()
        self.assertEqual(p.events,0)
        self.step(p)
        self.assertEqual(p.events,0)
        self.step(p,pressed=SPAR)
        self.assertEqual(p.events,SPAR_TOGGLE)
        self.step(p)
        self.assertFalse(p.events & SPAR_TOGGLE)

    def test_jump_start_and_landing_are_distinct_single_tick_events(self):
        p=self.new()
        self.step(p,pressed=JUMP)
        self.assertEqual(p.events,JUMP_START)
        self.step(p,pressed=JUMP)
        self.assertFalse(p.events & JUMP_START)
        landings=0
        for _ in range(40):
            self.step(p)
            if p.events & LAND:
                landings+=1
                self.assertEqual((p.z,p.vz),(0,0))
        self.assertEqual(landings,1)
        self.assertEqual(p.events,0)

    def test_whiff_generates_swing_but_never_hit_or_impact(self):
        p=self.new()
        self.step(p,pressed=ATTACK)
        self.assertEqual(p.events,SWING)
        self.assertEqual(p.dummy_impact_flash,0)
        self.step(p,pressed=ATTACK)
        self.assertEqual(p.events,0)
        self.assertEqual(p.successful_hits,0)

    def test_landed_hit_generates_swing_and_damage_event_exactly_once(self):
        p=self.new();p.x=230
        self.step(p,pressed=ATTACK)
        self.assertEqual(p.events,SWING|DUMMY_HIT)
        self.assertEqual(p.dummy_impact_flash,6)
        self.step(p)
        self.assertEqual((p.events,p.dummy_impact_flash),(0,5))
        for _ in range(5):self.step(p)
        self.assertEqual((p.events,p.dummy_impact_flash),(0,0))

    def test_finisher_event_coincides_with_third_hit_and_ko(self):
        p=self.new();p.x=230
        for i in range(3):
            self.step(p,pressed=ATTACK)
            expected=SWING|DUMMY_HIT
            if i==2:expected|=FINISHER|DUMMY_KO
            self.assertEqual(p.events,expected)
            if i<2:
                for _ in range(14):self.step(p)
        self.assertEqual(p.dummy_hp,0)
        for _ in range(15):self.step(p)
        self.step(p,pressed=ATTACK)
        self.assertEqual(p.events,SWING)
        self.assertFalse(p.events&(DUMMY_HIT|FINISHER|DUMMY_KO))

    def test_spar_toggle_clears_prior_impact_effects(self):
        p=self.new();p.x=230
        self.step(p,pressed=ATTACK)
        self.assertGreater(p.dummy_impact_flash,0)
        self.step(p,pressed=SPAR)
        self.assertEqual(p.events,SPAR_TOGGLE)
        self.assertEqual((p.dummy_impact_flash,p.player_impact_flash),(0,0))

    def test_enemy_swing_and_player_hit_share_single_impact_tick(self):
        p=self.new();p.x=220
        self.step(p,pressed=SPAR)
        self.assertEqual(p.events,SPAR_TOGGLE)
        for _ in range(11):
            self.step(p)
            self.assertFalse(p.events&(DUMMY_SWING|PLAYER_HIT|PLAYER_KO))
        self.step(p)
        self.assertEqual(p.events,DUMMY_SWING|PLAYER_HIT)
        self.assertEqual((p.player_hp,p.player_impact_flash),(4,8))
        self.step(p)
        self.assertEqual(p.events,0)
        self.assertEqual(p.player_impact_flash,7)

    def test_dodged_telegraph_emits_swing_and_dodge_but_no_hit(self):
        p=self.new();p.x=220
        self.step(p,pressed=SPAR)
        for i in range(12):
            self.step(p,pressed=JUMP if i==0 else 0)
        self.assertEqual(p.events,DUMMY_SWING|DODGE)
        self.assertEqual((p.player_hp,p.player_impact_flash),(5,0))

    def test_player_ko_is_single_transition_event_and_no_extra_damage(self):
        p=self.new();p.x=220
        self.step(p,pressed=SPAR)
        p.player_hp=1
        p.dummy_windup=1
        p.player_invuln=0
        self.step(p)
        self.assertEqual(p.events,DUMMY_SWING|PLAYER_HIT|PLAYER_KO)
        self.assertEqual(p.player_hp,0)
        self.step(p)
        self.assertFalse(p.events&(PLAYER_HIT|PLAYER_KO|DUMMY_SWING))
        self.assertEqual(p.player_hp,0)

    def test_dying_dummy_emits_ko_without_automatically_finishing(self):
        p=self.new();p.x=230;p.dummy_hp=1
        self.step(p,pressed=ATTACK)
        self.assertEqual(p.events,SWING|DUMMY_HIT|DUMMY_KO)
        self.assertFalse(p.events&FINISHER)
        self.step(p)
        self.assertEqual(p.events,0)

    def test_five_hundred_tick_event_replay_is_deterministic(self):
        a=self.new();b=self.new()
        for i in range(500):
            held=(RIGHT if i%49<24 else LEFT)|(UP if i%31<10 else DOWN)
            pressed=(SPAR if i in (0,250) else 0)
            pressed|=ATTACK if i%17==0 else 0
            pressed|=JUMP if i%41==0 else 0
            self.step(a,held,pressed)
            self.step(b,held,pressed)
            self.assertEqual(a.events,b.events)
        self.assertEqual(
            tuple(getattr(a,name) for name,_ in Arena._fields_),
            tuple(getattr(b,name) for name,_ in Arena._fields_)
        )
        self.assertEqual(a.ticks,500)

    def test_null_pointer_is_safe_for_both_native_functions(self):
        self.lib.dino_arena_reset(None)
        self.lib.dino_arena_step(None,RIGHT,ATTACK)


if __name__=='__main__':
    unittest.main()
