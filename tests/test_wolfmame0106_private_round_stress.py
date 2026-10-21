"""Stage275 private input training-rounds: completely synthetic ROM-free tests."""
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from tools import wolfmame0106_private_round_stress as check

ROOT=Path(__file__).resolve().parents[1]
SAMPLE=bytes((255,254,239,223,255,255,251,247)[i%8] for i in range(2405))

class NativeSegmentedRoundTests(unittest.TestCase):
    def test_exact_full_and_short_final_rounds(self):
        r=check.run_rounds(SAMPLE,"gcc",1200)
        self.assertEqual(r["normal"]["rounds"],3)
        self.assertEqual(r["normal"]["records"],len(SAMPLE))
        self.assertEqual(r["invented_sparring"]["records"],len(SAMPLE))
        self.assertEqual(len(r["normal"]["round_state_digest_sha256"]),64)
        self.assertGreater(r["normal"]["swings"],0)
        self.assertGreater(r["normal"]["jumps"],0)

    def test_repeated_run_is_deterministic(self):
        a=check.run_rounds(SAMPLE[:1600],"gcc",1200)
        b=check.run_rounds(SAMPLE[:1600],"gcc",1200)
        self.assertEqual(a,b)

    def test_invalid_round_lengths_and_inputs_rejected(self):
        for n in (0,-1,12001,True,None,"1200"):
            with self.subTest(rounds=n),self.assertRaises(ValueError):
                check.run_rounds(SAMPLE,"gcc",n)
        for raw in (b"",bytearray(SAMPLE),"bytes",None):
            with self.subTest(type=type(raw).__name__),self.assertRaises(ValueError):
                check.run_rounds(raw,"gcc",1200)

    @unittest.skipUnless(shutil.which("clang"),"Clang unavailable")
    def test_clang_gcc_native_training_agree(self):
        r=check.run_rounds(SAMPLE[:1300],"gcc",1200)
        s=check.run_rounds(SAMPLE[:1300],"clang",1200)
        self.assertEqual(r,s)

    def test_private_synthetic_inp_wlf_only(self):
        frames=240
        with tempfile.TemporaryDirectory() as folder:
            tmp=Path(folder)
            inp=tmp/"synthetic.inp"
            wlf=tmp/"synthetic.wlf"
            head=bytearray(32)
            head[:4]=b"dino"
            head[16:20]=b"ABCD"
            blocks=[]
            for i in range(frames):
                x=bytearray([255]*124)
                x[19]=SAMPLE[i]
                blocks.append(x)
            inp.write_bytes(head+b"".join(blocks))
            companion=bytearray(598)
            companion[:4]=b"WLF\x00"
            struct.pack_into("<I",companion,4,9)
            companion[148:153]=b"dino\x00"
            label=b"0.106 (May 16 2006)"
            companion[157:157+len(label)]=label
            companion[248:252]=b"ABCD"
            struct.pack_into("<III",companion,256,1000000,1000004,frames)
            wlf.write_bytes(companion)
            report=check.compare_private_input(inp,wlf,120,("gcc",))
            self.assertEqual(report["input_records"],frames)
            self.assertEqual(report["aggregates"]["normal"]["rounds"],2)
            self.assertFalse(report["original_emulator_executed"])
            self.assertFalse(report["full_original_input_stream_in_report"])
            self.assertFalse(report["original_game_physics_or_sprites_verified"])
            json.dumps(report)

    def test_cli_loads_without_environment_injection(self):
        driver=ROOT/"tools"/"wolfmame0106_private_round_stress.py"
        r=subprocess.run([sys.executable,str(driver),"--help"],
                         cwd=str(ROOT),capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn("--round-frames",r.stdout)

if __name__=="__main__":
    unittest.main()
