"""Stage 269 — native ROM-free C scenario trace/CI determinism tests.

Run original portable C training rules. No ROM files, no NeXium guest
claim, no Python-derived gameplay physics or physical input latency.
"""
import csv
from io import StringIO
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools' / 'dino_arena_scenario_trace.c'
FIELDS = ('scene','step','tick','x','y','z','player_hp','dummy_hp',
          'dummy_x','dummy_windup','combo_hits','events',
          'counter_feedback_ttl')
SIZES = {'target':120,'counter':140,'dodge':22,'player_ko':5}
DUMMY_HIT = 1 << 4
FINISHER = 1 << 5
DUMMY_KO = 1 << 6
DODGE = 1 << 10
COUNTER = 1 << 11
PLAYER_HIT = 1 << 8
PLAYER_KO = 1 << 9


@unittest.skipUnless(shutil.which('gcc'), 'Native GCC required')
class NativeGameScenarioTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='dino-scenario-')
        cls.outputs = {}
        compiler_profiles = [('gcc-O0','gcc','-O0'),
                             ('gcc-O2','gcc','-O2')]
        if shutil.which('clang'):
            compiler_profiles.append(('clang-O2','clang','-O2'))
        for label, compiler, optimize in compiler_profiles:
            binary = Path(cls.temp.name) / label
            compile_result = subprocess.run(
                [compiler, '-std=c11', optimize, '-Wall', '-Wextra',
                 '-Werror', '-Isource', str(SOURCE),
                 'source/dino_arena.c', '-o', str(binary)],
                cwd=ROOT, capture_output=True, text=True, timeout=45)
            if compile_result.returncode:
                raise AssertionError(label + ': ' + compile_result.stderr)
            executed = subprocess.run([str(binary)], cwd=ROOT,
                                      capture_output=True, timeout=15)
            if executed.returncode:
                raise AssertionError(
                    '%s scenario exited %d: %s' %
                    (label, executed.returncode,
                     executed.stderr.decode('utf-8', errors='replace')))
            cls.outputs[label] = executed.stdout
        cls.text = cls.outputs['gcc-O2'].decode('ascii')
        reader = csv.DictReader(StringIO(cls.text))
        if tuple(reader.fieldnames or ()) != FIELDS:
            raise AssertionError('unexpected C scenario trace CSV schema')
        cls.rows = []
        for raw in reader:
            if None in raw or set(raw) != set(FIELDS):
                raise AssertionError('noncanonical C CSV row')
            row = {'scene':raw['scene']}
            for k in FIELDS[1:]:
                if not raw[k] or not raw[k].isascii() or (
                        k not in ('x','y','z','dummy_x') and
                        not raw[k].isdecimal()):
                    raise AssertionError('invalid C integer CSV evidence')
                row[k] = int(raw[k])
            cls.rows.append(row)

    @classmethod
    def tearDownClass(cls):
        cls.outputs.clear()
        cls.temp.cleanup()

    def rows_for(self, scene):
        return [r for r in self.rows if r['scene'] == scene]

    def test_exact_byte_identity_across_compilers_and_optimization(self):
        reference=self.outputs['gcc-O2']
        self.assertGreater(len(reference),5000)
        self.assertEqual(reference.count(b'\n'),288)
        for label, output in self.outputs.items():
            with self.subTest(compiler=label):
                self.assertEqual(output,reference)

    def test_every_60hz_tick_is_accounted_for_and_no_other_scenes(self):
        self.assertEqual(len(self.rows),287)
        self.assertEqual({r['scene'] for r in self.rows},set(SIZES))
        for scene, n in SIZES.items():
            with self.subTest(scene=scene):
                rows=self.rows_for(scene)
                self.assertEqual(len(rows),n)
                self.assertEqual([r['step'] for r in rows],list(range(n)))
                self.assertEqual([r['tick'] for r in rows],
                                 list(range(1,n+1)))

    def test_original_c_training_arena_bounds_on_every_frame(self):
        for row in self.rows:
            self.assertTrue(16<=row['x']<=368)
            self.assertTrue(80<=row['y']<=208)
            self.assertTrue(16<=row['dummy_x']<=368)
            self.assertGreaterEqual(row['z'],0)
            self.assertTrue(0<=row['player_hp']<=5)
            self.assertTrue(0<=row['dummy_hp']<=3)
            self.assertTrue(0<=row['combo_hits']<=3)
            self.assertTrue(0<=row['counter_feedback_ttl']<=6)

    def test_three_authentic_practice_hits_and_one_finisher(self):
        rows=self.rows_for('target')
        hits=[r['step'] for r in rows if r['events'] & DUMMY_HIT]
        finals=[r['step'] for r in rows if r['events'] & FINISHER]
        ko=[r['step'] for r in rows if r['events'] & DUMMY_KO]
        self.assertEqual(hits,[75,90,105])
        self.assertEqual(finals,[105])
        self.assertEqual(ko,[105])
        self.assertEqual((rows[-1]['dummy_hp'],rows[-1]['x']),(0,230))

    def test_natural_116_tick_pursuit_and_single_successful_counter(self):
        rows=self.rows_for('counter')
        self.assertEqual(rows[115]['dummy_x'],134)
        self.assertEqual(rows[115]['dummy_windup'],12)
        counter=[r for r in rows if r['events'] & COUNTER]
        self.assertEqual([r['step'] for r in counter],[116])
        self.assertEqual(counter[0]['counter_feedback_ttl'],6)
        self.assertEqual(counter[0]['dummy_windup'],0)
        self.assertEqual(counter[0]['dummy_hp'],3)
        self.assertFalse(rows[117]['events'] & COUNTER)
        self.assertEqual(rows[117]['counter_feedback_ttl'],5)

    def test_jump_dodge_has_no_damage(self):
        rows=self.rows_for('dodge')
        dodges=[r['step'] for r in rows if r['events'] & DODGE]
        self.assertEqual(dodges,[12])
        self.assertTrue(all(r['player_hp']==5 for r in rows))
        self.assertTrue(all(not (r['events'] & PLAYER_HIT) for r in rows))

    def test_staged_single_hit_player_ko_is_one_time_only(self):
        rows=self.rows_for('player_ko')
        ko=[r['step'] for r in rows if r['events'] & PLAYER_KO]
        self.assertEqual(ko,[1])
        self.assertTrue(rows[1]['events'] & PLAYER_HIT)
        self.assertEqual(rows[1]['player_hp'],0)
        self.assertTrue(all(not (r['events'] & PLAYER_KO)
                            for r in rows[2:]))

    def test_fixture_is_standalone_without_nintendo_or_rom_assets(self):
        src=SOURCE.read_text(encoding='ascii')
        self.assertIn('#include "dino_arena.h"',src)
        self.assertIn('dino_arena_step(',src)
        self.assertNotIn('sdmc:/',src)
        self.assertNotIn('nexium',src.lower())
        self.assertNotIn('mame',src.lower())
        self.assertNotIn('gfx.bin',src)


if __name__=='__main__':
    unittest.main()
