"""Stage278 ROM-free periodic complete-state checkpoints for native C arena."""
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CORE=ROOT/"source"/"dino_arena.c"
PROBE=ROOT/"tools"/"dino_arena_recorded_input_stress.c"
FIXTURE=bytes(([255,239,239,255,223,223,255,254])*31)

def compile_probe(out,core=CORE,compiler="gcc"):
    subprocess.run([compiler,"-std=c99","-O2","-Wall","-Wextra","-Werror",
                    "-I",str(ROOT/"source"),str(core),str(PROBE),"-o",str(out)],
                   check=True,capture_output=True,text=True,timeout=30)

def run_probe(binary,buf=FIXTURE,*args):
    p=subprocess.run([str(binary),*args],input=buf,
                     capture_output=True,timeout=20)
    if p.returncode:
        return p,None,[]
    lines=p.stderr.decode("ascii").splitlines()
    checks=[]
    for line in lines:
        m=re.fullmatch(r"DINO278_CHECKPOINT frame=(\d+) full_state=([0-9a-f]{16})",line)
        if m is None:raise AssertionError("unexpected checkpoint evidence: "+line)
        checks.append((int(m.group(1)),m.group(2)))
    return p,json.loads(p.stdout),checks

class FullStateCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix="dino278-")
        cls.binary=Path(cls.temp.name)/"arena_gcc"
        compile_probe(cls.binary)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_no_optin_legacy_receipt_is_unchanged(self):
        p,old,checks=run_probe(self.binary)
        q,enabled,with_checks=run_probe(self.binary,FIXTURE,
                                        "--checkpoint-every=60")
        self.assertEqual((p.returncode,q.returncode),(0,0))
        self.assertEqual(old,enabled)
        self.assertEqual(checks,[])
        self.assertTrue(with_checks)

    def test_exact_periodic_steps_and_final_partial_checkpoint(self):
        _,result,checks=run_probe(self.binary,FIXTURE,"--checkpoint-every=60")
        self.assertEqual([a for a,b in checks],[60,120,180,240,248])
        self.assertEqual(checks[-1][1],result["full_state_digest_fnv64"])

    def test_aligned_end_not_emitted_twice(self):
        _,result,checks=run_probe(self.binary,FIXTURE[:240],"--checkpoint-every=60")
        self.assertEqual([a for a,b in checks],[60,120,180,240])
        self.assertEqual(checks[-1][1],result["full_state_digest_fnv64"])

    def test_bounded_argument_rejects_malformed(self):
        for flag in ("--checkpoint-every=","--checkpoint-every=0",
                     "--checkpoint-every=-1","--checkpoint-every=1.5",
                     "--checkpoint-every=10000001","--checkpoint-every=999999999999",
                     "--checkpoint-every=abc"):
            with self.subTest(flag=flag):
                p,_,_=run_probe(self.binary,FIXTURE,flag)
                self.assertNotEqual(p.returncode,0)

    def test_duplicate_interval_and_other_bad_options_rejected(self):
        p,_,_=run_probe(self.binary,FIXTURE,
                        "--checkpoint-every=60","--checkpoint-every=60")
        self.assertNotEqual(p.returncode,0)
        q,_,_=run_probe(self.binary,FIXTURE,"--not-a-real-flag")
        self.assertNotEqual(q.returncode,0)

    @unittest.skipUnless(shutil.which("clang"),"Clang not installed")
    def test_exact_gcc_clang_checkpoint_series_and_final_receipts(self):
        with tempfile.TemporaryDirectory() as folder:
            clang=Path(folder)/"native-clang"
            compile_probe(clang,compiler="clang")
            for flags in (("--checkpoint-every=7",),
                          ("--checkpoint-every=59","--spar"),
                          ("--prior-active-low=ef","--checkpoint-every=23")):
                with self.subTest(flags=flags):
                    a,ra,ca=run_probe(self.binary,FIXTURE,*flags)
                    b,rb,cb=run_probe(clang,FIXTURE,*flags)
                    self.assertEqual((a.returncode,b.returncode),(0,0))
                    self.assertEqual(ra,rb)
                    self.assertEqual(ca,cb)

    def test_temporary_hp_mutant_first_checkpoint_catches_blind_spot(self):
        with tempfile.TemporaryDirectory() as folder:
            source=CORE.read_text()
            self.assertIn(".player_hp=5",source)
            mutant=Path(folder)/"dino_arena_mutant.c"
            mutant.write_text(source.replace(".player_hp=5",".player_hp=4",1))
            binary=Path(folder)/"mutant"
            compile_probe(binary,core=mutant)
            a,ra,ca=run_probe(self.binary,FIXTURE,"--checkpoint-every=20")
            b,rb,cb=run_probe(binary,FIXTURE,"--checkpoint-every=20")
        self.assertEqual((a.returncode,b.returncode),(0,0))
        self.assertEqual(ra["state_digest_fnv64"],rb["state_digest_fnv64"])
        self.assertNotEqual(ra["full_state_digest_fnv64"],rb["full_state_digest_fnv64"])
        self.assertEqual(ca[0][0],20)
        self.assertEqual(cb[0][0],20)
        self.assertNotEqual(ca[0][1],cb[0][1])

if __name__=="__main__":
    unittest.main()
