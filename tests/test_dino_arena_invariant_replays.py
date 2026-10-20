"""Stage 268 — portable ROM-free training arena deterministic state QA.

These are *actual host-compiled C arena rules*, not a claimed NeXium guest
run, original Capcom gameplay, CPS-1 behavior or ROM-derived physics.
"""
import ctypes
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from test_dino_arena import Arena

ROOT = Path(__file__).resolve().parents[1]
HELD_MASK = 0x0f
PRESSED_MASK = 0xf0
EVENT_MASK = (1 << 12) - 1
COUNTER = 1 << 11
DUMMY_KO = 1 << 6
DUMMY_HIT = 1 << 4
FINISHER = 1 << 5
PLAYER_KO = 1 << 9
PLAYER_HIT = 1 << 8
DODGE = 1 << 10
DUMMY_SWING = 1 << 7
SPAR = 1 << 6


def snapshot(a):
    # Compare declared simulation fields (never unstable C padding).
    return tuple(getattr(a, name) for name, _ in Arena._fields_)


def timeline(seed, length=900):
    rnd = random.Random(0xD160268 + seed)
    for tick in range(length):
        # Always enable sparring initially, then exercise legitimate
        # and simultaneous edge masks, horizontal/depth movement,
        # occasional toggles, and arbitrary high (unknown) input bits.
        held = rnd.getrandbits(4) & HELD_MASK
        pressed = (rnd.getrandbits(4) << 4) & PRESSED_MASK
        if tick == 0:
            pressed |= SPAR
        if tick % 73 == 29:
            pressed |= COUNTER
        yield held, pressed


@unittest.skipUnless(shutil.which('gcc'), 'Host GCC is required')
class ArenaNativeDeterministicInvariants(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='dino-arena-invariants-')
        cls.libs = {}
        profiles = [('gcc-O0', 'gcc', '-O0'),
                    ('gcc-O2', 'gcc', '-O2')]
        if shutil.which('clang'):
            profiles.append(('clang-O2', 'clang', '-O2'))
        for name, cc, opt in profiles:
            shared = Path(cls.tmp.name) / (name + '.so')
            command = [cc, '-std=c11', opt, '-Wall', '-Wextra',
                       '-Werror', '-fPIC', '-shared', '-Isource',
                       'source/dino_arena.c', '-o', str(shared)]
            done = subprocess.run(command, cwd=ROOT,
                                  capture_output=True, text=True, timeout=45)
            if done.returncode:
                raise AssertionError(
                    name + ' C build failed:\n' + done.stdout + done.stderr)
            lib = ctypes.CDLL(str(shared))
            lib.dino_arena_reset.argtypes = [ctypes.POINTER(Arena)]
            lib.dino_arena_step.argtypes = [
                ctypes.POINTER(Arena), ctypes.c_uint32, ctypes.c_uint32]
            lib.dino_arena_reset.restype = None
            lib.dino_arena_step.restype = None
            cls.libs[name] = lib

    @classmethod
    def tearDownClass(cls):
        cls.libs.clear()
        cls.tmp.cleanup()

    def new(self, lib):
        a = Arena()
        lib.dino_arena_reset(ctypes.byref(a))
        return a

    def step(self, lib, a, held=0, pressed=0):
        lib.dino_arena_step(ctypes.byref(a), held, pressed)

    def assert_invariants(self, a):
        self.assertTrue(16 <= a.x <= 368)
        self.assertTrue(80 <= a.y <= 208)
        self.assertTrue(16 <= a.dummy_x <= 368)
        self.assertTrue(80 <= a.dummy_y <= 208)
        self.assertGreaterEqual(a.z, 0)
        if a.z == 0:
            self.assertEqual(a.vz, 0)
        self.assertLessEqual(a.player_hp, 5)
        self.assertLessEqual(a.dummy_hp, 3)
        self.assertLessEqual(a.combo_hits, 3)
        self.assertLessEqual(a.combo_timer, 24)
        self.assertLessEqual(a.dummy_windup, 12)
        self.assertLessEqual(a.dummy_cooldown, 48)
        self.assertLessEqual(a.attack_cooldown, 15)
        self.assertLessEqual(a.finisher_flash, 10)
        self.assertLessEqual(a.dummy_impact_flash, 6)
        self.assertLessEqual(a.player_impact_flash, 8)
        self.assertEqual(a.events & ~EVENT_MASK, 0)
        if a.events & COUNTER:
            self.assertTrue(a.sparring)
            self.assertGreater(a.player_hp, 0)
            self.assertGreater(a.dummy_hp, 0)
            self.assertEqual(a.dummy_impact_flash, 6)
            self.assertEqual(a.dummy_cooldown, 48)
            self.assertEqual(a.dummy_hitstun, 9)
            self.assertFalse(a.events & PLAYER_HIT)
        if a.events & DUMMY_KO:
            self.assertEqual(a.dummy_hp, 0)
            self.assertTrue(a.events & DUMMY_HIT)
        if a.events & FINISHER:
            self.assertTrue(a.events & DUMMY_HIT)
        if a.events & PLAYER_KO:
            self.assertEqual(a.player_hp, 0)
            self.assertTrue(a.events & PLAYER_HIT)
        if a.events & DODGE:
            self.assertTrue(a.events & DUMMY_SWING)
            self.assertFalse(a.events & PLAYER_HIT)

    def test_24_seeded_900_tick_playthroughs_respect_game_state(self):
        lib = self.libs['gcc-O2']
        for seed in range(24):
            with self.subTest(seed=seed):
                a = self.new(lib)
                for held, pressed in timeline(seed):
                    self.step(lib, a, held, pressed)
                    self.assert_invariants(a)
                self.assertEqual(a.ticks, 900)

    def test_cross_optimization_and_clang_are_bitwise_field_deterministic(self):
        for seed in range(12):
            states = {name: self.new(lib) for name, lib in self.libs.items()}
            for held, pressed in timeline(seed, 600):
                for name, lib in self.libs.items():
                    self.step(lib, states[name], held, pressed)
                reference = snapshot(states['gcc-O2'])
                for name, state in states.items():
                    self.assertEqual(snapshot(state), reference, (seed, name))
            self.assertEqual(states['gcc-O2'].ticks, 600)

    def test_input_unknown_upper_bits_do_not_change_any_field(self):
        lib = self.libs['gcc-O2']
        plain, unknown = self.new(lib), self.new(lib)
        for held, pressed in timeline(100, 1200):
            self.step(lib, plain, held, pressed)
            self.step(lib, unknown, held | 0xffff0000,
                      pressed | 0xffff0000)
            self.assertEqual(snapshot(plain), snapshot(unknown))

    def test_reset_eliminates_prior_sparring_and_combo_history(self):
        lib = self.libs['gcc-O2']
        used, fresh = self.new(lib), self.new(lib)
        for held, pressed in timeline(22, 1500):
            self.step(lib, used, held, pressed)
        lib.dino_arena_reset(ctypes.byref(used))
        self.assertEqual(snapshot(used), snapshot(fresh))
        for held, pressed in timeline(41, 600):
            self.step(lib, used, held, pressed)
            self.step(lib, fresh, held, pressed)
            self.assertEqual(snapshot(used), snapshot(fresh))

    def test_all_256_grounded_edge_and_movement_combinations_are_bounded(self):
        lib = self.libs['gcc-O2']
        for held in range(16):
            for edge in range(16):
                a = self.new(lib)
                self.step(lib, a, held, (edge << 4) | SPAR)
                self.assert_invariants(a)
                self.assertEqual(a.ticks, 1)

    def test_native_pursuit_counter_event_reachable_under_each_compiler(self):
        # Unlike random inputs, this is a reachable game event with no
        # manually seeded enemy x, hitstun or windup. Preserve natural AI.
        for name, lib in self.libs.items():
            with self.subTest(compiler=name):
                a = self.new(lib)
                self.step(lib, a, pressed=SPAR)
                for _ in range(200):
                    if a.dummy_windup:
                        break
                    self.step(lib, a)
                else:
                    self.fail('natural enemy windup was not reached')
                self.assertEqual((a.ticks, a.x, a.dummy_x),
                                 (116, 90, 134))
                self.assertEqual(a.dummy_windup, 12)
                self.step(lib, a, pressed=128)
                self.assertEqual(a.events, COUNTER)
                self.assertEqual((a.dummy_windup, a.dummy_hitstun,
                                  a.dummy_cooldown), (0, 9, 48))
                self.assert_invariants(a)
                self.step(lib, a, pressed=128)
                self.assertFalse(a.events & COUNTER)

    def test_native_three_hit_finisher_and_ko_under_each_compiler(self):
        for name, lib in self.libs.items():
            with self.subTest(compiler=name):
                a = self.new(lib)
                a.x = 230
                for hit_index in range(3):
                    self.step(lib, a, pressed=16)
                    expected = (1 << 3) | DUMMY_HIT
                    if hit_index == 2:
                        expected |= FINISHER | DUMMY_KO
                    self.assertEqual(a.events, expected)
                    self.assert_invariants(a)
                    if hit_index < 2:
                        for _ in range(14):
                            self.step(lib, a)
                self.assertEqual((a.dummy_hp, a.successful_hits), (0, 3))
                self.step(lib, a)
                self.assertFalse(a.events & (DUMMY_KO | FINISHER))

    def test_native_jump_dodge_and_player_ko_events_under_each_compiler(self):
        for name, lib in self.libs.items():
            with self.subTest(compiler=name):
                dodge = self.new(lib)
                dodge.x = 220
                self.step(lib, dodge, pressed=SPAR)
                for i in range(12):
                    self.step(lib, dodge, pressed=32 if i == 0 else 0)
                self.assertEqual(dodge.events, DUMMY_SWING | DODGE)
                self.assertEqual(dodge.player_hp, 5)
                self.assert_invariants(dodge)

                ko = self.new(lib)
                ko.x = 220
                self.step(lib, ko, pressed=SPAR)
                ko.player_hp = 1
                ko.dummy_windup = 1
                ko.player_invuln = 0
                self.step(lib, ko)
                self.assertEqual(ko.events,
                                 DUMMY_SWING | PLAYER_HIT | PLAYER_KO)
                self.assertEqual(ko.player_hp, 0)
                self.assert_invariants(ko)
                self.step(lib, ko)
                self.assertFalse(ko.events & (PLAYER_HIT | PLAYER_KO))

    def test_null_arena_arguments_do_not_dereference(self):
        for lib in self.libs.values():
            lib.dino_arena_reset(None)
            lib.dino_arena_step(None, 0xffffffff, 0xffffffff)


if __name__ == '__main__':
    unittest.main()
