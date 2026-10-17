"""ROM-free host-native PCM tests for the original training SFX engine.

No original MAME PCM, commercial sound ROM, synthesized arcade tune or
Switch hardware is required. C sample generation is deterministic.
"""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
EVENTS=[1<<i for i in range(11)]
SAMPLES=800
VOICES=6

class Voice(ctypes.Structure):
    _fields_=[
        ('phase',ctypes.c_uint32),('phase_step',ctypes.c_uint32),
        ('rng',ctypes.c_uint32),('remaining',ctypes.c_uint32),
        ('total',ctypes.c_uint32),('gain',ctypes.c_int32),
        ('pan',ctypes.c_int16),('wave',ctypes.c_uint8),
        ('priority',ctypes.c_uint8)]

class Synth(ctypes.Structure):
    _fields_=[
        ('voices',Voice*VOICES),
        ('ticks',ctypes.c_uint32),('launched',ctypes.c_uint32),
        ('dropped',ctypes.c_uint32)]

@unittest.skipUnless(shutil.which('gcc'), 'GCC is required for native PCM tests')
class OriginalSfxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dino-rom-free-sfx-')
        lib=Path(cls.tmp.name)/'libsfx.so'
        proc=subprocess.run(
            ['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-fPIC','-shared','-Isource','source/dino_sfx.c',
             '-o',str(lib)],
            cwd=ROOT,capture_output=True,text=True)
        if proc.returncode:
            raise AssertionError(proc.stderr)
        cls.dll=ctypes.CDLL(str(lib))
        cls.dll.dino_sfx_reset.argtypes=[ctypes.POINTER(Synth)]
        cls.dll.dino_sfx_events.argtypes=[
            ctypes.POINTER(Synth),ctypes.c_uint32]
        cls.dll.dino_sfx_render_tick.argtypes=[
            ctypes.POINTER(Synth),ctypes.POINTER(ctypes.c_int16),
            ctypes.c_size_t]
        cls.dll.dino_sfx_active_voices.argtypes=[ctypes.POINTER(Synth)]
        cls.dll.dino_sfx_active_voices.restype=ctypes.c_uint

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def fresh(self):
        engine=Synth()
        self.dll.dino_sfx_reset(ctypes.byref(engine))
        return engine

    def trigger(self,engine,bits):
        self.dll.dino_sfx_events(ctypes.byref(engine),bits)

    def pcm(self,engine,count=SAMPLES):
        buffer=(ctypes.c_int16*(2*SAMPLES))()
        self.dll.dino_sfx_render_tick(
            ctypes.byref(engine),buffer,count)
        return tuple(buffer)

    def active(self,engine):
        return self.dll.dino_sfx_active_voices(ctypes.byref(engine))

    def test_silent_reset_produces_stereo_800_sample_frame(self):
        e=self.fresh()
        values=self.pcm(e)
        self.assertEqual(len(values),1600)
        self.assertTrue(all(value==0 for value in values))
        self.assertEqual((e.ticks,e.launched,e.dropped,self.active(e)),
                         (1,0,0,0))

    def test_every_combat_event_emits_sound_without_any_rom_file(self):
        for event in EVENTS:
            with self.subTest(event=event):
                e=self.fresh()
                self.trigger(e,event)
                self.assertEqual((self.active(e),e.launched),(1,1))
                samples=self.pcm(e)
                self.assertTrue(any(value for value in samples))
                self.assertEqual(e.ticks,1)

    def test_all_events_have_deterministic_pcm_including_noise(self):
        for event in EVENTS:
            with self.subTest(event=event):
                a,b=self.fresh(),self.fresh()
                self.trigger(a,event)
                self.trigger(b,event)
                for _ in range(5):
                    self.assertEqual(self.pcm(a),self.pcm(b))
                self.assertEqual(bytes(a),bytes(b))

    def test_event_pan_is_asymmetric_and_audio_is_stereo(self):
        e=self.fresh()
        self.trigger(e,EVENTS[3]) # player swing, negative pan
        pcm=self.pcm(e)
        left=sum(abs(x) for x in pcm[0::2])
        right=sum(abs(x) for x in pcm[1::2])
        self.assertGreater(left,right)

    def test_no_unbounded_voice_growth_with_simultaneous_events(self):
        e=self.fresh()
        self.trigger(e,sum(EVENTS))
        self.assertEqual(self.active(e),VOICES)
        self.assertGreaterEqual(e.launched,VOICES)
        self.assertTrue(any(v.priority==8 for v in e.voices))
        for _ in range(40):
            self.trigger(e,sum(EVENTS))
            self.pcm(e)
            self.assertLessEqual(self.active(e),VOICES)
        self.assertGreater(e.dropped,0)

    def test_audio_envelopes_expire_into_silence(self):
        e=self.fresh()
        self.trigger(e,EVENTS[9]) # player KO, longest 20 ticks
        for _ in range(20):
            self.pcm(e)
        self.assertEqual(self.active(e),0)
        self.assertTrue(all(x==0 for x in self.pcm(e)))

    def test_audio_output_stays_within_signed_16_bit(self):
        e=self.fresh()
        self.trigger(e,sum(EVENTS))
        for _ in range(25):
            pcm=self.pcm(e)
            self.assertGreaterEqual(min(pcm),-32768)
            self.assertLessEqual(max(pcm),32767)

    def test_unknown_event_bits_produce_no_voice(self):
        e=self.fresh()
        self.trigger(e,(1<<20)|(1<<31))
        self.assertEqual((self.active(e),e.launched,e.dropped),(0,0,0))
        self.assertTrue(all(v==0 for v in self.pcm(e)))

    def test_reset_cancels_active_voices_without_heap(self):
        e=self.fresh()
        self.trigger(e,EVENTS[4]|EVENTS[8])
        self.assertGreater(self.active(e),0)
        self.pcm(e)
        self.dll.dino_sfx_reset(ctypes.byref(e))
        self.assertEqual((e.ticks,e.launched,e.dropped,self.active(e)),(0,0,0,0))
        self.assertTrue(all(v==0 for v in self.pcm(e)))

    def test_bad_frame_length_does_not_touch_output_or_clock(self):
        e=self.fresh()
        self.trigger(e,EVENTS[4])
        output=(ctypes.c_int16*(2*SAMPLES))(*([123]*1600))
        self.dll.dino_sfx_render_tick(
            ctypes.byref(e),output,SAMPLES+1)
        self.assertEqual((e.ticks,self.active(e)),(0,1))
        self.assertTrue(all(v==123 for v in output))

    def test_partial_frames_do_not_count_as_60hz_tick(self):
        e=self.fresh()
        self.trigger(e,EVENTS[4])
        frame=self.pcm(e,200)
        self.assertTrue(any(v for v in frame[:400]))
        self.assertTrue(all(v==0 for v in frame[400:]))
        self.assertEqual(e.ticks,0)
        self.pcm(e)
        self.assertEqual(e.ticks,1)

    def test_null_pointers_do_not_crash(self):
        self.dll.dino_sfx_reset(None)
        self.dll.dino_sfx_events(None,EVENTS[0])
        self.dll.dino_sfx_render_tick(None,None,SAMPLES)
        self.assertEqual(self.dll.dino_sfx_active_voices(None),0)
        e=self.fresh()
        self.dll.dino_sfx_render_tick(ctypes.byref(e),None,SAMPLES)
        self.assertEqual(e.ticks,0)

if __name__=='__main__':
    unittest.main()
