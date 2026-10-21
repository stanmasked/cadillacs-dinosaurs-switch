"""Stage276: ensure independent practice resets do not invent input press edges.

All fixtures are synthetic and ROM-free; the original user recording is private.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from tools import wolfmame0106_private_round_stress as rounds

ROOT=Path(__file__).resolve().parents[1]

class NativeHeldEdgeContinuityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="dino276-fixtures-")
        cls.bin=Path(cls.temp.name)/"arena"
        subprocess.run([
            "gcc","-std=c99","-O2","-Wall","-Wextra","-Werror",
            "-I",str(ROOT/"source"),str(ROOT/"source"/"dino_arena.c"),
            str(ROOT/"tools"/"dino_arena_recorded_input_stress.c"),
            "-o",str(cls.bin)],check=True,capture_output=True,timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def native(self,data,*flags):
        p=subprocess.run([str(self.bin),*flags],input=data,capture_output=True,timeout=10)
        return p,(json.loads(p.stdout) if p.returncode==0 else None)

    def test_held_attack_across_boundary_not_counted_twice(self):
        data=bytes([255,239,239,239,239,255])
        r=rounds.run_rounds(data,"gcc",3)
        for mode in ("normal","invented_sparring"):
            self.assertEqual(r[mode]["nominal_attack_press_edges"],1)
            self.assertEqual(r[mode]["continued_held_attack_edges_suppressed"],1)
            self.assertEqual(r[mode]["nominal_jump_press_edges"],0)
        naive,_=self.native(data[3:])
        self.assertEqual(naive.returncode,0)
        _,fixed=self.native(data[3:],"--prior-active-low=ef")
        self.assertEqual(fixed["attack_press_edges"],0)

    def test_two_held_buttons_suppressed_across_boundary(self):
        data=bytes([255,207,207,207,207,255])
        r=rounds.run_rounds(data,"gcc",3)
        for mode in r.values():
            self.assertEqual(mode["nominal_attack_press_edges"],1)
            self.assertEqual(mode["nominal_jump_press_edges"],1)
            self.assertEqual(mode["continued_held_attack_edges_suppressed"],1)
            self.assertEqual(mode["continued_held_jump_edges_suppressed"],1)

    def test_new_press_exactly_on_boundary_must_survive(self):
        data=bytes([255,255,255,239,239,255])
        r=rounds.run_rounds(data,"gcc",3)
        for mode in r.values():
            self.assertEqual(mode["nominal_attack_press_edges"],1)
            self.assertEqual(mode["continued_held_attack_edges_suppressed"],0)

    def test_press_edge_totals_invariant_across_round_lengths(self):
        data=bytes([255,239,239,207,207,223,255,255,239,223,223])*3
        cases=[rounds.run_rounds(data,"gcc",stride)
               for stride in (1,2,5,7,11,33)]
        for result in cases:
            for mode in result.values():
                self.assertEqual(mode["nominal_attack_press_edges"],6)
                self.assertEqual(mode["nominal_jump_press_edges"],3)
                self.assertEqual(mode["records"],len(data))

    def test_prior_hex_option_accepts_lowercase_uppercase(self):
        data=bytes([239,255])
        a,lower=self.native(data,"--prior-active-low=ef")
        b,upper=self.native(data,"--prior-active-low=EF")
        self.assertEqual((a.returncode,b.returncode),(0,0))
        self.assertEqual(lower,upper)
        self.assertEqual(lower["attack_press_edges"],0)

    def test_prior_hex_malformed_or_duplicate_rejected(self):
        bad=[
            ("--prior-active-low=",),
            ("--prior-active-low=1",),
            ("--prior-active-low=zz",),
            ("--prior-active-low=gg",),
            ("--prior-active-low=0fff",),
            ("--prior-active-low=ff","--prior-active-low=ff"),
            ("--spar","--spar"),
        ]
        for args in bad:
            with self.subTest(args=args):
                p,_=self.native(bytes([255]),*args)
                self.assertNotEqual(p.returncode,0)

    def test_default_and_explicit_released_prior_equal(self):
        data=bytes([239,223,255])
        a,default=self.native(data)
        b,explicit=self.native(data,"--prior-active-low=ff")
        self.assertEqual((a.returncode,b.returncode),(0,0))
        self.assertEqual(default,explicit)

    @unittest.skipUnless(shutil.which("clang"),"Clang not installed")
    def test_gcc_clang_same_edge_continuity_and_state_digests(self):
        data=bytes([255,207,207,207,255,239,239,255])*17
        a=rounds.run_rounds(data,"gcc",7)
        b=rounds.run_rounds(data,"clang",7)
        self.assertEqual(a,b)

if __name__=="__main__":
    unittest.main()
