"""Stage 225: live original-training-room counter, NOT Capcom game AI.

These compile the exact Switch-facing arena C module and drive its new
action from a standalone host test. Existing 180-tick ROM-free replay
does not use the new action and must remain byte-stable.
"""
import ctypes
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from test_dino_arena import Arena

ROOT=Path(__file__).resolve().parents[1]
RIGHT=2
ATTACK=16
JUMP=32
SPAR=64
COUNTER=128
COUNTER_EVENT=1<<11
PLAYER_HIT=1<<8
ENEMY_SWING=1<<7


@unittest.skipUnless(shutil.which('gcc'),'Native GCC required')
class ArenaCounterGameplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dino-counter-225-')
        path=Path(cls.tmp.name)/'libdino_counter.so'
        proc=subprocess.run([
            'gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
            '-fPIC','-shared','-Isource','source/dino_arena.c',
            '-o',str(path)
        ],cwd=ROOT,capture_output=True,text=True)
        if proc.returncode:
            raise AssertionError(proc.stderr)
        cls.lib=ctypes.CDLL(str(path))
        cls.lib.dino_arena_reset.argtypes=[ctypes.POINTER(Arena)]
        cls.lib.dino_arena_step.argtypes=[
            ctypes.POINTER(Arena),ctypes.c_uint32,ctypes.c_uint32]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def new(self):
        a=Arena()
        self.lib.dino_arena_reset(ctypes.byref(a))
        return a

    def step(self,a,held=0,pressed=0):
        self.lib.dino_arena_step(ctypes.byref(a),held,pressed)

    def ready(self):
        a=self.new()
        a.x=219
        a.y=151
        a.sparring=1
        a.dummy_x=250
        a.dummy_y=151
        a.dummy_hp=3
        a.dummy_windup=6
        a.dummy_cooldown=0
        return a

    def test_counter_interrupts_a_telegraphed_strike(self):
        a=self.ready()
        self.step(a,pressed=COUNTER)
        self.assertEqual(a.events,COUNTER_EVENT)
        self.assertEqual(a.dummy_windup,0)
        self.assertEqual(a.dummy_hitstun,9)
        self.assertEqual(a.dummy_cooldown,48)
        self.assertEqual(a.dummy_impact_flash,6)
        self.assertEqual((a.player_hp,a.dummy_hp),(5,3))
        self.assertEqual(a.successful_hits,0)
        self.assertEqual(a.ticks,1)

    def test_last_windup_tick_counter_prevents_imminent_damage(self):
        a=self.ready()
        a.dummy_windup=1
        self.step(a,pressed=COUNTER)
        self.assertEqual(a.events,COUNTER_EVENT)
        self.assertFalse(a.events&ENEMY_SWING)
        self.assertFalse(a.events&PLAYER_HIT)
        self.assertEqual(a.player_hp,5)
        self.assertEqual(a.dummy_windup,0)

    def test_hitstun_last_tick_is_not_counter_actionable(self):
        a=self.ready()
        a.player_hitstun=1
        # A last-tick press is illegal even though the countdown hits zero
        # before combat resolution. A *new* edge next tick is valid.
        self.step(a,pressed=COUNTER)
        self.assertFalse(a.events&COUNTER_EVENT)
        self.assertEqual((a.player_hitstun,a.dummy_windup),(0,5))
        self.assertEqual(a.dummy_hitstun,0)
        self.step(a,pressed=COUNTER)
        self.assertEqual(a.events,COUNTER_EVENT)
        self.assertEqual(a.dummy_windup,0)

    def test_attack_animation_last_tick_is_not_counter_actionable(self):
        a=self.ready()
        a.attack_frames=1
        self.step(a,pressed=COUNTER)
        self.assertFalse(a.events&COUNTER_EVENT)
        self.assertEqual((a.attack_frames,a.dummy_windup),(0,5))
        self.assertEqual(a.dummy_hitstun,0)
        self.step(a,pressed=COUNTER)
        self.assertEqual(a.events,COUNTER_EVENT)
        self.assertEqual((a.player_hp,a.dummy_hp),(5,3))

    def test_landing_tick_cannot_convert_airborne_press_to_counter(self):
        a=self.ready()
        a.z=1
        a.vz=-2
        self.step(a,pressed=COUNTER)
        self.assertFalse(a.events&COUNTER_EVENT)
        self.assertEqual((a.z,a.vz,a.dummy_windup),(0,0,5))
        self.assertEqual(a.dummy_hitstun,0)
        self.step(a,pressed=COUNTER)
        self.assertEqual(a.events,COUNTER_EVENT)
        self.assertEqual((a.player_hp,a.dummy_hp),(5,3))

    def test_counter_is_single_tick_not_passive_invulnerability(self):
        a=self.ready()
        self.step(a,pressed=COUNTER)
        self.step(a)
        self.assertFalse(a.events&COUNTER_EVENT)
        self.assertEqual(a.dummy_hitstun,8)
        self.assertEqual(a.dummy_cooldown,47)
        self.assertEqual(a.player_invuln,0)
        for _ in range(10):self.step(a,pressed=COUNTER)
        self.assertEqual(a.dummy_windup,0)
        self.assertEqual(a.player_hp,5)
        self.assertEqual(a.successful_hits,0)

    def test_wrong_facing_does_not_counter_and_enemy_still_hits(self):
        a=self.ready()
        a.facing_right=0
        a.dummy_windup=1
        self.step(a,pressed=COUNTER)
        self.assertFalse(a.events&COUNTER_EVENT)
        self.assertTrue(a.events&ENEMY_SWING)
        self.assertTrue(a.events&PLAYER_HIT)
        self.assertEqual(a.player_hp,4)

    def test_counter_requires_same_depth_lane(self):
        a=self.ready()
        a.y=170
        a.dummy_windup=1
        self.step(a,pressed=COUNTER)
        self.assertFalse(a.events&COUNTER_EVENT)
        self.assertEqual(a.player_hp,5)
        self.assertTrue(a.events&ENEMY_SWING)

    def test_counter_requires_close_range(self):
        a=self.ready()
        a.x=170
        a.dummy_windup=1
        self.step(a,pressed=COUNTER)
        self.assertFalse(a.events&COUNTER_EVENT)
        self.assertEqual(a.dummy_hitstun,0)

    def test_counter_rejected_during_attack_jump_or_hitstun(self):
        for mode in ('hitstun','airborne','attack_animation',
                     'same_tick_attack','same_tick_jump'):
            a=self.ready()
            a.dummy_windup=7
            pressed=COUNTER
            if mode=='hitstun':a.player_hitstun=3
            if mode=='airborne':
                a.z=14
                a.vz=4
            if mode=='attack_animation':a.attack_frames=4
            if mode=='same_tick_attack':
                pressed|=ATTACK
                a.attack_cooldown=10
            if mode=='same_tick_jump':pressed|=JUMP
            with self.subTest(mode=mode):
                self.step(a,pressed=pressed)
                self.assertFalse(a.events&COUNTER_EVENT)

    def test_counter_ignored_with_sparring_disabled_or_player_defeated(self):
        for mode in ('spar_off','enemy_ko','player_ko','no_windup'):
            a=self.ready()
            if mode=='spar_off':a.sparring=0
            if mode=='enemy_ko':a.dummy_hp=0
            if mode=='player_ko':a.player_hp=0
            if mode=='no_windup':a.dummy_windup=0
            self.step(a,pressed=COUNTER)
            with self.subTest(mode=mode):
                self.assertFalse(a.events&COUNTER_EVENT)
                self.assertEqual(a.successful_hits,0)

    def test_real_input_toggle_opens_fair_counter_window(self):
        a=self.new()
        a.x=219
        self.step(a,pressed=SPAR)
        self.assertEqual(a.sparring,1)
        self.assertGreater(a.dummy_windup,0)
        self.step(a,pressed=COUNTER)
        self.assertTrue(a.events&COUNTER_EVENT)
        self.assertEqual((a.player_hp,a.dummy_hp),(5,3))

    def test_without_new_button_legacy_demo_is_deterministic(self):
        from ctypes import string_at, sizeof, addressof
        from test_dino_arena import RIGHT as WALK_RIGHT
        from test_dino_arena import SPAR as TOGGLE_SPAR
        a=self.new()
        b=self.new()
        for tick in range(700):
            held=WALK_RIGHT if tick<70 else 0
            pressed=ATTACK if tick in (75,90,105,148) else 0
            if tick==130:pressed|=TOGGLE_SPAR
            if tick==155:pressed|=JUMP
            self.step(a,held,pressed)
            self.step(b,held,pressed)
            self.assertEqual(string_at(addressof(a),sizeof(a)),
                             string_at(addressof(b),sizeof(b)))
            self.assertFalse(a.events&COUNTER_EVENT)
        self.assertEqual(a.ticks,700)

    def test_desktop_h_action_is_true_key_edge(self):
        from tools import dino_host_preview as host
        controls=host.KeyboardInput()
        controls.key_down('h')
        self.assertEqual(controls.tick_input(),(0,COUNTER))
        controls.key_down('h')  # key-repeat must not trigger again
        self.assertEqual(controls.tick_input(),(0,0))
        controls.key_up('h')
        controls.key_down('H')
        self.assertEqual(controls.tick_input(),(0,COUNTER))

    def test_native_desktop_bridge_dispatches_real_c_counter(self):
        from tools import dino_host_preview as host
        game=host.HostArena()
        try:
            for _ in range(65):game.step(host.RIGHT)
            game.step(0,host.SPAR)
            self.assertEqual(game.status().sparring,1)
            game.step(0,host.COUNTER)
            self.assertEqual(game.status().events,COUNTER_EVENT)
            self.assertEqual(game.status().player_hp,5)
        finally:
            game.close()

    def test_real_host_bridge_counter_event_reaches_pcm_synth(self):
        # Exercise real arena -> event -> SFX -> 48 kHz PCM hash.
        # Compare the very same deterministic setup with/without ZR/H.
        from tools import dino_host_preview as host
        game=host.HostArena()
        try:
            def prepare():
                game.reset()
                for _ in range(65):
                    game.step(host.RIGHT)
                game.step(0,host.SPAR)
                self.assertEqual(game.status().x,220)
            prepare()
            game.step(0,host.COUNTER)
            triggered=game.status()
            self.assertEqual(triggered.events,COUNTER_EVENT)
            self.assertEqual((triggered.player_hp,triggered.enemy_hp),(5,3))
            counter_pcm=triggered.pcm_digest
            prepare()
            game.step()
            baseline=game.status()
            self.assertEqual(baseline.events,0)
            self.assertEqual((baseline.player_hp,baseline.enemy_hp),(5,3))
            self.assertNotEqual(counter_pcm,baseline.pcm_digest)
        finally:
            game.close()

    def test_switch_button_and_event_feedback_are_wired_only_on_counter(self):
        source=(ROOT/'source/main.c').read_text(encoding='utf-8')
        self.assertIn(
            'if (down & HidNpadButton_ZR) pending_actions|=DINO_ARENA_COUNTER;',
            source)
        self.assertIn('if (arena->events&DINO_EVT_COUNTER)',source)
        self.assertIn('"COUNTER!"',source)
        self.assertIn(
            '"DPAD MOVE  A HIT  B JUMP  X SPAR  Y RESET  - DEMO  + EXIT"',
            source)

    def test_adversarial_random_inputs_never_overflow_bounds(self):
        r=random.Random(225)
        a=self.new()
        for t in range(2800):
            held=r.getrandbits(4)
            pressed=r.getrandbits(4)<<4
            self.step(a,held,pressed)
            self.assertTrue(16<=a.x<=368)
            self.assertTrue(80<=a.y<=208)
            self.assertTrue(0<=a.player_hp<=5)
            self.assertTrue(0<=a.dummy_hp<=3)
            self.assertTrue(0<=a.dummy_windup<=12)
            self.assertTrue(0<=a.dummy_cooldown<=48)
        self.assertEqual(a.ticks,2800)


if __name__=='__main__':
    unittest.main()
