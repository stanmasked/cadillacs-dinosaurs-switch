"""Portable ROM-free tests for an explicit opt-in output-edge PCM ramp.

Only local synthetic 48kHz stereo sample arrays; no copied game audio,
no audio device, no assertion of actual speaker quality or latency.
"""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ATTACK = 96
FRAMES = 800


class RampState(ctypes.Structure):
    _fields_ = [('pending', ctypes.c_bool),
                ('applied', ctypes.c_uint32)]


def integer_ramp(sample, i, total):
    magnitude = abs(sample) * (i + 1) // total
    return -magnitude if sample < 0 else magnitude


@unittest.skipUnless(shutil.which('gcc'), 'Host GCC compiler required')
class OptionalPCMResumeRampTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='dino-resume-ramp-')
        binary = Path(cls.temp.name) / 'resume_ramp.so'
        build = subprocess.run([
            'gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
            '-fPIC', '-shared', '-Isource', 'source/dino_pcm_resume_ramp.c',
            '-o', str(binary),
        ], cwd=ROOT, capture_output=True, text=True)
        if build.returncode:
            raise AssertionError('Resume ramp C compilation failed: ' + build.stderr)
        cls.lib = ctypes.CDLL(str(binary))
        cls.apply = cls.lib.dino_pcm_resume_ramp_apply
        cls.apply.argtypes = [ctypes.POINTER(ctypes.c_int16),
                             ctypes.c_size_t, ctypes.c_size_t]
        cls.apply.restype = ctypes.c_bool
        cls.reset = cls.lib.dino_pcm_resume_ramp_reset
        cls.reset.argtypes = [ctypes.POINTER(RampState)]
        cls.reset.restype = None
        cls.note = cls.lib.dino_pcm_resume_ramp_note_full_skip
        cls.note.argtypes = [ctypes.POINTER(RampState)]
        cls.note.restype = None
        cls.admit = cls.lib.dino_pcm_resume_ramp_before_submit
        cls.admit.argtypes = [ctypes.POINTER(RampState),
                             ctypes.POINTER(ctypes.c_int16),
                             ctypes.c_size_t, ctypes.c_size_t]
        cls.admit.restype = ctypes.c_bool

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_exact_96_frame_ramp_and_untouched_remainder(self):
        original = [
            -32768 if i % 4 == 0 else
            32767 if i % 4 == 1 else
            -23091 if i % 4 == 2 else 12345
            for i in range(FRAMES * 2)
        ]
        pcm = (ctypes.c_int16 * (FRAMES * 2))(*original)
        self.assertTrue(self.apply(pcm, FRAMES, ATTACK))
        for frame in range(FRAMES):
            for channel in (0, 1):
                i = 2 * frame + channel
                expected = (integer_ramp(original[i], frame, ATTACK)
                            if frame < ATTACK else original[i])
                self.assertEqual(pcm[i], expected)
                self.assertLessEqual(abs(pcm[i]), abs(original[i]))
        self.assertEqual(list(pcm[ATTACK*2:]), original[ATTACK*2:])
        self.assertEqual(pcm[2*(ATTACK-1)],
                         original[2*(ATTACK-1)])

    def test_all_zero_and_full_scale_pcm_stay_in_i16_bounds(self):
        for amplitude in (-32768, -1, 0, 1, 32767):
            pcm = (ctypes.c_int16 * (FRAMES*2))(
                *([amplitude]*(FRAMES*2)))
            self.assertTrue(self.apply(pcm, FRAMES, ATTACK))
            for s in pcm:
                self.assertGreaterEqual(s,-32768)
                self.assertLessEqual(s,32767)
                self.assertLessEqual(abs(s),abs(amplitude))
            self.assertEqual(pcm[2*(ATTACK-1)], amplitude)
            self.assertEqual(pcm[-1], amplitude)

    def test_zero_or_oversized_attack_rejected_without_writing(self):
        values = [(-20000 if i % 2 else 20000)
                  for i in range(FRAMES*2)]
        for frames,attack in (
            (FRAMES, 0), (FRAMES, FRAMES+1),
            (FRAMES, 2**31), (0, 1), (FRAMES, 2**64-1),
            (2**64-1, 1),
        ):
            pcm = (ctypes.c_int16 * (FRAMES*2))(*values)
            self.assertFalse(self.apply(pcm,frames,attack))
            self.assertEqual(list(pcm),values)
        self.assertFalse(self.apply(None,FRAMES,ATTACK))

    def test_stereo_channels_have_the_same_gain_curve(self):
        data = [0]*(FRAMES*2)
        for frame in range(FRAMES):
            data[2*frame] = 17000
            data[2*frame+1] = -17000
        pcm = (ctypes.c_int16 * (FRAMES*2))(*data)
        self.assertTrue(self.apply(pcm,FRAMES,ATTACK))
        for i in range(FRAMES):
            self.assertEqual(pcm[2*i],-pcm[2*i+1])
            self.assertEqual(pcm[2*i],integer_ramp(17000,i,ATTACK)
                             if i<ATTACK else 17000)

    def test_identical_pcm_is_deterministic_across_runs(self):
        samples = [((i*199) % 65536)-32768
                   for i in range(FRAMES*2)]
        a=(ctypes.c_int16*(FRAMES*2))(*samples)
        b=(ctypes.c_int16*(FRAMES*2))(*samples)
        self.assertTrue(self.apply(a,FRAMES,ATTACK))
        self.assertTrue(self.apply(b,FRAMES,ATTACK))
        self.assertEqual(bytes(a),bytes(b))

    def test_experimental_integration_is_disabled_in_production_by_default(self):
        sound=(ROOT/'source/dino_switch_sound.c').read_text(encoding='utf-8')
        make=(ROOT/'Makefile').read_text(encoding='utf-8')
        module=(ROOT/'source/dino_pcm_resume_ramp.c').read_text(
            encoding='utf-8')
        header=(ROOT/'source/dino_pcm_resume_ramp.h').read_text(
            encoding='utf-8')
        guard='#if defined(DINO_EMULATOR_SELFTEST) && defined(DINO_AUDIO_EXPERIMENT_RESUME_RAMP)'
        self.assertGreaterEqual(sound.count(guard),4)
        self.assertIn('#define DINO_PCM_RESUME_RAMP_FRAMES 96u',header)
        self.assertIn('dino_pcm_resume_ramp_note_full_skip(&s_resume_ramp);',sound)
        self.assertIn('dino_pcm_resume_ramp_reset(&s_resume_ramp);',sound)
        self.assertIn('dino_pcm_resume_ramp_before_submit(',sound)
        self.assertNotIn('DINO_AUDIO_EXPERIMENT_RESUME_RAMP',make)
        self.assertNotIn('audout',module)
        self.assertNotIn('sdmc:',module)
        self.assertNotIn('armGetSystemTick',module)
        # The PCM synthesis checksum is always computed on the original,
        # unmodified samples; optional output-only shaping happens after.
        self.assertLess(sound.index('s_pcm_witness=dino_pcm_witness_feed('),
                        sound.index('dino_pcm_resume_ramp_before_submit('))

    def test_one_shot_ramp_only_after_full_queue_drop(self):
        state = RampState()
        self.reset(ctypes.byref(state))
        samples = [32000] * (FRAMES * 2)
        without = (ctypes.c_int16 * (FRAMES * 2))(*samples)
        self.assertFalse(self.admit(ctypes.byref(state), without,
                                    FRAMES, ATTACK))
        self.assertEqual(list(without), samples)
        self.note(ctypes.byref(state))
        self.assertTrue(state.pending)
        self.assertEqual(state.applied, 0)
        admitted = (ctypes.c_int16 * (FRAMES * 2))(*samples)
        self.assertTrue(self.admit(ctypes.byref(state), admitted, FRAMES, ATTACK))
        self.assertEqual(admitted[0], 32000 // ATTACK)
        self.assertEqual(admitted[2 * (ATTACK - 1)], 32000)
        self.assertEqual(admitted[2 * ATTACK], 32000)
        self.assertFalse(state.pending)
        self.assertEqual(state.applied, 1)
        next_pcm = (ctypes.c_int16 * (FRAMES * 2))(*samples)
        self.assertFalse(self.admit(ctypes.byref(state), next_pcm,
                                    FRAMES, ATTACK))
        self.assertEqual(list(next_pcm), samples)
        self.assertEqual(state.applied, 1)

    def test_repeated_skips_merge_and_bad_admission_retains_pending_ramp(self):
        state = RampState()
        self.reset(ctypes.byref(state))
        for _ in range(50):
            self.note(ctypes.byref(state))
        self.assertTrue(state.pending)
        untouched = (ctypes.c_int16 * (FRAMES * 2))(
            *([19000] * (FRAMES * 2)))
        before = bytes(untouched)
        self.assertFalse(self.admit(ctypes.byref(state), untouched,
                                    FRAMES, FRAMES + 1))
        self.assertEqual(bytes(untouched), before)
        self.assertTrue(state.pending)
        self.assertTrue(self.admit(ctypes.byref(state), untouched, FRAMES, ATTACK))
        self.assertFalse(state.pending)
        self.assertEqual(state.applied, 1)
        self.note(ctypes.byref(state))
        self.assertTrue(state.pending)
        self.reset(ctypes.byref(state))
        self.assertFalse(state.pending)
        self.assertEqual(state.applied, 0)

    def test_diagnostic_counter_saturates_instead_of_wrapping(self):
        state = RampState()
        self.reset(ctypes.byref(state))
        state.applied = (2**32) - 1
        self.note(ctypes.byref(state))
        pcm = (ctypes.c_int16 * (FRAMES * 2))(
            *([-30000] * (FRAMES * 2)))
        self.assertTrue(self.admit(ctypes.byref(state), pcm, FRAMES, ATTACK))
        self.assertEqual(state.applied, (2**32) - 1)
        self.assertFalse(state.pending)
