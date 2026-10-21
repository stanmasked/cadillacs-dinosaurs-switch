"""Stage277: canonical complete C arena-state witness (synthetic ROM-free)."""
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from tools import wolfmame0106_private_round_stress as rounds

ROOT=Path(__file__).resolve().parents[1]
HEADER=ROOT/"source"/"dino_arena.h"
SOURCE=ROOT/"source"/"dino_arena.c"
ADAPTER=ROOT/"tools"/"dino_arena_recorded_input_stress.c"
SAMPLE=bytes([255,239,239,223,207,255,254,253,255])*73

def compile_native(out,core=SOURCE,compiler="gcc"):
    subprocess.run([compiler,"-std=c99","-O2","-Wall","-Wextra","-Werror",
                    "-I",str(ROOT/"source"),str(core),str(ADAPTER),"-o",str(out)],
                   capture_output=True,text=True,check=True,timeout=30)

def execute(binary,input_bytes=SAMPLE,*options):
    return json.loads(subprocess.run([str(binary),*options],input=input_bytes,
                                     capture_output=True,check=True,timeout=20).stdout)

class FullArenaStateWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder=tempfile.TemporaryDirectory(prefix="dino277-")
        cls.binary=Path(cls.folder.name)/"native"
        compile_native(cls.binary)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_all_declared_arena_fields_in_canonical_witness_exactly_once(self):
        header=HEADER.read_text()
        body=header.split("typedef struct {",1)[1].split("} DinoArena;",1)[0]
        body=re.sub(r"/\*.*?\*/","",body,flags=re.S)
        declared=[]
        for typ,variables in re.findall(r"\b(int32_t|uint32_t|uint8_t)\s+([^;]+);",body):
            declared.extend(v.strip() for v in variables.split(","))
        adapter=ADAPTER.read_text()
        function=adapter.split("static uint64_t mix_full_state(",1)[1].split("\nint main(",1)[0]
        witnessed=re.findall(r"\(uint32_t\)a->([A-Za-z_][A-Za-z_0-9]*)",function)
        self.assertEqual(len(declared),30)
        self.assertEqual(len(witnessed),30)
        self.assertCountEqual(witnessed,declared)
        self.assertEqual(len(set(witnessed)),30)

    def test_legacy_stable_while_full_covers_all_30_fields(self):
        r=execute(self.binary)
        self.assertEqual(r["full_state_fields"],30)
        self.assertRegex(r["full_state_digest_fnv64"],r"^[0-9a-f]{16}$")
        self.assertRegex(r["state_digest_fnv64"],r"^[0-9a-f]{16}$")
        self.assertFalse(r["original_gameplay_parity_verified"])

    def test_deliberate_health_mutation_fools_legacy_but_not_full_state(self):
        with tempfile.TemporaryDirectory() as folder:
            original=SOURCE.read_text()
            self.assertIn(".player_hp=5",original)
            mutated=Path(folder)/"dino_arena_health_mutant.c"
            mutated.write_text(original.replace(".player_hp=5",".player_hp=4",1))
            binary=Path(folder)/"arena_mutant"
            compile_native(binary,mutated)
            baseline=execute(self.binary)
            changed=execute(binary)
        self.assertEqual(baseline["player_hp"],5)
        self.assertEqual(changed["player_hp"],4)
        self.assertEqual(baseline["state_digest_fnv64"],
                         changed["state_digest_fnv64"])
        self.assertNotEqual(baseline["full_state_digest_fnv64"],
                            changed["full_state_digest_fnv64"])

    @unittest.skipUnless(shutil.which("clang"),"Clang not installed")
    def test_cross_compiler_complete_state_parity(self):
        with tempfile.TemporaryDirectory() as folder:
            other=Path(folder)/"arena_clang"
            compile_native(other,compiler="clang")
            for options in ((),("--spar",),("--prior-active-low=ef",)):
                with self.subTest(options=options):
                    self.assertEqual(execute(self.binary,SAMPLE,*options),
                                     execute(other,SAMPLE,*options))

    def test_segmented_driver_keeps_separate_full_and_legacy_witnesses(self):
        output=rounds.run_rounds(SAMPLE,"gcc",100)
        for mode in ("normal","invented_sparring"):
            receipt=output[mode]
            self.assertEqual(receipt["full_state_fields_witnessed"],30)
            self.assertRegex(receipt["round_full_state_digest_sha256"],
                             r"^[0-9a-f]{64}$")
            self.assertRegex(receipt["round_state_digest_sha256"],
                             r"^[0-9a-f]{64}$")
            self.assertNotEqual(receipt["round_full_state_digest_sha256"],
                                receipt["round_state_digest_sha256"])
            self.assertEqual(receipt["records"],len(SAMPLE))

    def test_full_state_witness_is_reproducible(self):
        a=execute(self.binary,SAMPLE,"--spar")
        b=execute(self.binary,SAMPLE,"--spar")
        self.assertEqual(a["full_state_digest_fnv64"],b["full_state_digest_fnv64"])
        self.assertTrue(a["training_only"])

if __name__=="__main__":
    unittest.main()
