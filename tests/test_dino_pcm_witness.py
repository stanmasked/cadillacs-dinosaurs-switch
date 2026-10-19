"""Independent ROM-free stereo PCM witness tests across native host and Switch.

C and Python explicitly hash signed 16-bit samples as little-endian
PCM. This confirms synthesized samples, NOT audout buffer playback.
"""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from tools import dino_host_preview as host

ROOT=Path(__file__).resolve().parents[1]
OFFSET=14695981039346656037
PRIME=1099511628211
MASK=(1<<64)-1


def python_pcm_hash(samples,initial=OFFSET):
    out=initial
    for value in samples:
        for byte in int(value).to_bytes(2,'little',signed=True):
            out=((out^byte)*PRIME)&MASK
    return out


@unittest.skipUnless(shutil.which('gcc'),'GCC needed for PCM witness tests')
class SynthesizedPcmWitnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='dino-pcm-witness-')
        target=Path(cls.temp.name)/'libdino_pcm_witness.so'
        run=subprocess.run(
            ['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-shared','-fPIC','-Isource',
             'source/dino_pcm_witness.c','-o',str(target)],
            cwd=ROOT,check=False,capture_output=True,text=True)
        if run.returncode:
            raise AssertionError(run.stderr)
        cls.dll=ctypes.CDLL(str(target))
        cls.dll.dino_pcm_witness_feed.argtypes=[
            ctypes.c_uint64,ctypes.POINTER(ctypes.c_int16),
            ctypes.c_size_t]
        cls.dll.dino_pcm_witness_feed.restype=ctypes.c_uint64

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def feed(self,values,seed=OFFSET):
        self.assertEqual(len(values)%2,0)
        cbuf=(ctypes.c_int16*len(values))(*values)
        return self.dll.dino_pcm_witness_feed(seed,cbuf,len(values)//2)

    def test_explicit_little_endian_including_signed_extremes(self):
        samples=[0,1,-1,-32768,32767,-17,255,-256]
        self.assertEqual(self.feed(samples),python_pcm_hash(samples))

    def test_chunking_one_pcm_tick_or_many_is_identical(self):
        samples=[((i*3109)%65536)-32768 for i in range(1600)]
        expected=python_pcm_hash(samples)
        self.assertEqual(self.feed(samples),expected)
        current=OFFSET
        for i in range(0,len(samples),200):
            current=self.feed(samples[i:i+200],current)
        self.assertEqual(current,expected)

    def test_bad_pointer_or_excessive_samples_leave_hash_unchanged(self):
        seed=0x123456789abcdef0
        self.assertEqual(self.dll.dino_pcm_witness_feed(
            seed,None,800),seed)
        enormous=(ctypes.c_int16*1602)()
        self.assertEqual(self.dll.dino_pcm_witness_feed(
            seed,enormous,801),seed)
        self.assertEqual(self.feed([],seed),seed)

    def test_single_sample_edit_changes_witness(self):
        samples=[0]*1600
        baseline=self.feed(samples)
        samples[1337]=1
        self.assertNotEqual(self.feed(samples),baseline)
        samples[1337]=-1
        self.assertNotEqual(self.feed(samples),baseline)

    def test_real_180_tick_c_gameplay_matches_recorded_pcm_golden(self):
        # The reference was extracted from an earlier green GitHub Actions
        # artifact before sharing this helper, making it independent.
        actual=host.headless(180)
        self.assertEqual(actual['ticks'],180)
        self.assertEqual(actual['pcm_fnv64'],'d82c3b7960857b22')
        self.assertEqual(actual['gameplay_witness_fnv64'],
                         '5bca2ff01fb244f6')
        self.assertFalse(actual['switch_audio_verified'])
        self.assertFalse(actual['switch_emulator_verified'])


if __name__=='__main__':
    unittest.main()
