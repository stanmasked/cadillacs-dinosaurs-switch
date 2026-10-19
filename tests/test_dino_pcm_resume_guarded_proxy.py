"""Synthetic ROM-free regression suite for a PROXY-only PCM gate.

This uses actual GCC-compiled C. "Previous" is a supplied previously
submitted PCM sample, not actual physical audout playback. No production
output is changed, no sampling of speaker data, no commercial audio.
"""
import ctypes
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
FRAMES=800
ATTACK=96


def reference(previous, samples, attack=ATTACK):
    if previous is None:
        return False
    if len(previous)!=2 or len(samples)!=2*FRAMES or attack<1 or attack>FRAMES:
        raise ValueError("invalid reference")
    before_overall=0
    after_overall=0
    for channel in (0,1):
        prior_a=prior_b=previous[channel]
        before=after=0
        for i in range(attack):
            value=samples[2*i+channel]
            shaped=(1 if value>=0 else -1)*(abs(value)*(i+1)//attack)
            before=max(before,abs(value-prior_a))
            after=max(after,abs(shaped-prior_b))
            prior_a=value
            prior_b=shaped
        if after>before:
            return False
        before_overall=max(before_overall,before)
        after_overall=max(after_overall,after)
    return after_overall<before_overall


@unittest.skipUnless(shutil.which("gcc"),"Native GCC required")
class PurePCMResumeGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory=tempfile.TemporaryDirectory(prefix="dino-guarded-proxy-")
        path=Path(cls.directory.name)/"gate.so"
        command=["gcc","-std=c11","-O2","-Wall","-Wextra","-Werror",
                 "-shared","-fPIC","-Isource",
                 "source/dino_pcm_resume_guarded_proxy.c",
                 "-o",str(path)]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
        if result.returncode:
            raise AssertionError(result.stderr)
        lib=ctypes.CDLL(str(path))
        cls.gate=lib.dino_pcm_resume_guarded_proxy_would_help
        cls.gate.argtypes=[
            ctypes.POINTER(ctypes.c_int16),ctypes.POINTER(ctypes.c_int16),
            ctypes.c_size_t,ctypes.c_size_t,
        ]
        cls.gate.restype=ctypes.c_bool

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def actual_gate(self,previous,samples,frames=FRAMES,attack=ATTACK):
        prev=None if previous is None else (ctypes.c_int16*2)(*previous)
        values=(ctypes.c_int16*(2*FRAMES))(*samples)
        original=bytes(values)
        result=self.gate(prev,values,frames,attack)
        self.assertEqual(bytes(values),original)
        return result

    def test_silence_to_loud_is_accepted_by_proxy(self):
        samples=[30000,-24000]*FRAMES
        self.assertTrue(self.actual_gate((0,0),samples))
        self.assertTrue(reference((0,0),samples))

    def test_already_continuous_boundary_is_rejected(self):
        samples=[30000,-24000]*FRAMES
        self.assertFalse(self.actual_gate((30000,-24000),samples))
        self.assertFalse(reference((30000,-24000),samples))

    def test_opposite_polarity_transition_is_accepted(self):
        samples=[30000,-24000]*FRAMES
        self.assertTrue(self.actual_gate((-30000,24000),samples))

    def test_zero_signal_and_identical_previous_are_not_pointlessly_shaped(self):
        self.assertFalse(self.actual_gate((0,0),[0,0]*FRAMES))
        self.assertFalse(self.actual_gate((100,100),[100,100]*FRAMES))

    def test_unknown_previous_frame_fails_closed(self):
        self.assertFalse(self.actual_gate(None,[30000,-24000]*FRAMES))
        self.assertFalse(self.gate(None,None,FRAMES,ATTACK))

    def test_bad_attack_arguments_fail_without_pcm_mutation(self):
        samples=[-32768,32767]*FRAMES
        for frames,attack in ((FRAMES,0),(FRAMES,FRAMES+1),
                              (FRAMES,2**31),(0,1),
                              (2**64-1,1)):
            with self.subTest(frames=frames,attack=attack):
                self.assertFalse(self.actual_gate(
                    (-32768,32767),samples,frames,attack))

    def test_both_channels_must_not_get_worse(self):
        # Left has a beneficial silence->loud boundary; right was
        # already perfectly continuous and would be made worse.
        samples=[30000,10000]*FRAMES
        self.assertFalse(self.actual_gate((0,10000),samples))
        self.assertFalse(reference((0,10000),samples))

    def test_real_c_matches_independent_oracle_on_seeded_stereo_cases(self):
        rng=random.Random(223)
        choices=(-32768,-30000,-24000,-10000,-1,0,1,10000,24000,30000,32767)
        for n in range(120):
            previous=(rng.choice(choices),rng.choice(choices))
            samples=[]
            style=n%4
            if style==0:
                samples=list((rng.choice(choices),rng.choice(choices)))*FRAMES
            elif style==1:
                samples=[rng.choice(choices) for _ in range(FRAMES*2)]
            elif style==2:
                val=(rng.choice(choices),rng.choice(choices))
                samples=list(val)*FRAMES
                samples[100:200]=[rng.choice(choices) for _ in range(100)]
            else:
                samples=[(i*121%65536)-32768 for i in range(FRAMES*2)]
            with self.subTest(n=n):
                self.assertEqual(self.actual_gate(previous,samples),
                                 reference(previous,samples))

    def test_proxy_source_is_independent_from_production_sound_adapter(self):
        adapter=(ROOT/"source/dino_switch_sound.c").read_text()
        source=(ROOT/"source/dino_pcm_resume_guarded_proxy.c").read_text()
        header=(ROOT/"source/dino_pcm_resume_guarded_proxy.h").read_text()
        makefile=(ROOT/"Makefile").read_text()
        self.assertNotIn("dino_pcm_resume_guarded_proxy",adapter)
        self.assertNotIn("DINO_AUDIO_EXPERIMENT_GUARDED",makefile)
        self.assertIn("NOT known to be the most recently PLAYED",header)
        for forbidden in ("audout","armGetSystemTick","sdmc:",
                          "dino_switch_sound_step("):
            self.assertNotIn(forbidden,source)
        self.assertIn("return ramp_max_all<original_max_all;",source)


if __name__=="__main__":
    unittest.main()
