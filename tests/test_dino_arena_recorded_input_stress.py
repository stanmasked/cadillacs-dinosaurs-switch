"""ROM-free synthetic checks for streamed active-low input into native C arena."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CORE=ROOT/'source'/'dino_arena.c'
PROBE=ROOT/'tools'/'dino_arena_recorded_input_stress.c'

def compile_probe(compiler,optimization,out):
    subprocess.run([compiler,'-std=c99',optimization,'-Wall','-Wextra','-Werror',
                    '-I',str(ROOT/'source'),str(CORE),str(PROBE),'-o',str(out)],
                   check=True,capture_output=True,text=True,timeout=30)

def execute(path,input_bytes,args=()):
    p=subprocess.run([str(path),*args],input=input_bytes,
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
    return p,json.loads(p.stdout) if p.returncode==0 else None

class NativeRecordedInputStressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.binary=Path(cls.temp.name)/'arena'
        compile_probe('gcc','-O2',cls.binary)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_held_button_is_not_another_new_press(self):
        p,r=execute(self.binary,bytes([255,239,239,255,223,223,255]))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(r['nominal_input_records'],7)
        self.assertEqual(r['attack_press_edges'],1)
        self.assertEqual(r['jump_press_edges'],1)
        self.assertFalse(r['wolfmame_playback_verified'])

    def test_both_edges_same_record(self):
        p,r=execute(self.binary,bytes([255,207,207,255]))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual((r['attack_press_edges'],r['jump_press_edges']),(1,1))

    def test_deterministic_long_synthetic_record(self):
        seq=bytes((255,254,253,251,247,239,223,207)[(i*13)//7%8]
                  for i in range(25000))
        a,ra=execute(self.binary,seq)
        b,rb=execute(self.binary,seq)
        self.assertEqual((a.returncode,b.returncode),(0,0))
        self.assertEqual(ra,rb)
        self.assertEqual(ra['nominal_input_records'],25000)
        self.assertTrue(ra['training_only'])
        self.assertFalse(ra['original_gameplay_parity_verified'])

    def test_explicit_sparring_is_invented_optional_mode(self):
        inp=bytes([255,254,254,239,255])*300
        p,ordinary=execute(self.binary,inp)
        q,spar=execute(self.binary,inp,('--spar',))
        self.assertEqual((p.returncode,q.returncode),(0,0))
        self.assertFalse(ordinary['sparring_mode'])
        self.assertTrue(spar['sparring_mode'])
        self.assertEqual(ordinary['nominal_input_records'],
                         spar['nominal_input_records'])

    def test_empty_and_unknown_switch_rejected(self):
        p,_=execute(self.binary,b'')
        self.assertNotEqual(p.returncode,0)
        q,_=execute(self.binary,b'\xff',('--unsupported',))
        self.assertNotEqual(q.returncode,0)

    def test_optimizations_have_same_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            o0=Path(tmp)/'arena_O0'
            compile_probe('gcc','-O0',o0)
            seq=bytes([255,255,254,239,255,223,255,251])*500
            a,ra=execute(self.binary,seq)
            b,rb=execute(o0,seq)
            self.assertEqual((a.returncode,b.returncode),(0,0))
            self.assertEqual(ra['state_digest_fnv64'],rb['state_digest_fnv64'])

    @unittest.skipUnless(shutil.which('clang'),'Clang not installed')
    def test_clang_and_gcc_same_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            clang=Path(tmp)/'arena_clang'
            compile_probe('clang','-O2',clang)
            seq=bytes((255,254,253,251,247,239,223)[i%7]
                      for i in range(10000))
            a,ra=execute(self.binary,seq,('--spar',))
            b,rb=execute(clang,seq,('--spar',))
            self.assertEqual((a.returncode,b.returncode),(0,0))
            self.assertEqual(ra,rb)

if __name__=='__main__':
    unittest.main()
