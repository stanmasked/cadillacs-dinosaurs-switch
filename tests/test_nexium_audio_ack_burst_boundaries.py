"""ROM-free adversarial ACK timing at a two-page queue boundary.

Compiles the unchanged production Switch C audio adapter twice, then drives
synthetic credits just before/after guest-only intertick polls. Exercises
complete starvation, steady ACKs, two-at-once ACK bursts, and ACKs confined
to later ticks of a multi-tick frame. This deliberately does NOT control
real NeXium service ACK timing or prove audible hardware latency.
"""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import nexium_audio_intertick_phase as phase
from test_dino_switch_audout_mock import Diagnostics, ROOT
from test_nexium_audio_intertick_phase import SOURCES
from test_nexium_audio_intertick_tick_trace import IndependentTickQueue

CREDIT_CASES = ('none', 'steady-one', 'burst-two', 'later-only-two')


def credit(case, tick, position):
    """Pre-registered synthetic ACKs: exactly 0/1/2 pages, never real audio."""
    if case == 'none':
        return 0
    if case == 'steady-one':
        return 1
    if case == 'burst-two':
        return 2 if tick % 11 == 0 else 0
    if case == 'later-only-two':
        return 2 if position > 0 else 0
    raise ValueError('unknown test release pattern')


def diagnostic(lib):
    snap = Diagnostics()
    lib.dino_switch_sound_diagnostics(ctypes.byref(snap))
    return snap


@unittest.skipUnless(shutil.which('gcc'), 'host GCC required for C audout')
class BurstBoundaryCAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='dino-audout-ack-edge-')
        cls.libs = []
        for extra in (False, True):
            output = Path(cls.tmp.name) / ('extra.so' if extra else 'base.so')
            flags = ['-DDINO_EMULATOR_SELFTEST']
            if extra:
                flags.append('-DDINO_AUDIO_EXPERIMENT_MID_BATCH_POLL')
            cmd = ['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-fPIC', '-shared', '-Itests/mocks', '-Isource',
                   *flags, *SOURCES, '-o', str(output)]
            proc = subprocess.run(cmd, cwd=ROOT, capture_output=True,
                                  text=True)
            if proc.returncode:
                raise AssertionError('C adapter compile failed: ' + proc.stderr)
            lib = ctypes.CDLL(str(output))
            lib.dino_switch_sound_open.restype = ctypes.c_bool
            lib.dino_switch_sound_step.argtypes = [ctypes.c_uint32]
            lib.dino_switch_sound_diagnostics.argtypes = [
                ctypes.POINTER(Diagnostics)]
            lib.dino_switch_sound_pcm_witness.restype = ctypes.c_uint64
            lib.dino_switch_sound_guest_mid_batch_calls.restype = ctypes.c_uint32
            lib.dino_switch_sound_guest_mid_batch_releases.restype = ctypes.c_uint32
            lib.mock_audout_grant_releases.argtypes = [ctypes.c_uint32]
            for attr in ('mock_audout_pending', 'mock_audout_released',
                         'mock_audout_integrity_errors'):
                getattr(lib, attr).restype = ctypes.c_uint32
            if extra:
                lib.dino_switch_sound_guest_mid_batch_poll.restype = None
            cls.libs.append(lib)

    @classmethod
    def tearDownClass(cls):
        for lib in cls.libs:
            lib.dino_switch_sound_close()
        cls.tmp.cleanup()

    def test_credit_bursts_do_not_increase_per_tick_admissions(self):
        baseline, experimental = self.libs
        plan = phase.make_plan()
        phase.check_plan(plan)
        for schedule in CREDIT_CASES:
            for arrival in phase.PHASES:
                with self.subTest(credits=schedule, arrival=arrival):
                    for lib in (baseline, experimental):
                        lib.dino_switch_sound_close()
                        lib.mock_audout_reset()
                        self.assertTrue(lib.dino_switch_sound_open())
                        lib.dino_switch_sound_step(0)
                        lib.dino_switch_sound_step(0)
                        self.assertEqual(diagnostic(lib).pending, 2)
                    start = [diagnostic(lib).simulated_ticks
                             for lib in (baseline, experimental)]
                    oracle = IndependentTickQueue()
                    tick = 0
                    saw_double_mid_ack = False
                    for frame in plan['frames']:
                        for position in range(frame):
                            credits = credit(schedule, tick, position)
                            early = phase.is_early(arrival, tick, position)
                            pending_before = oracle.pending
                            released = min(pending_before, credits)
                            mid_credit = released if position and early else 0

                            if position and not early:
                                # Both builds receive the SAME external ACK
                                # after the experimental poll already ran.
                                for lib in (baseline, experimental):
                                    lib.mock_audout_grant_releases(0)
                                experimental.dino_switch_sound_guest_mid_batch_poll()
                                for lib in (baseline, experimental):
                                    lib.mock_audout_grant_releases(credits)
                            else:
                                for lib in (baseline, experimental):
                                    lib.mock_audout_grant_releases(credits)
                                if position:
                                    experimental.dino_switch_sound_guest_mid_batch_poll()

                            self.assertEqual(diagnostic(baseline).pending,
                                             pending_before)
                            self.assertEqual(diagnostic(experimental).pending,
                                             pending_before - mid_credit)
                            if mid_credit == 2:
                                saw_double_mid_ack = True
                            oracle.step(credits, position, early)
                            event = 1 << ((tick * 7) % 10)
                            for lib in (baseline, experimental):
                                lib.dino_switch_sound_step(event)
                            for i, lib in enumerate((baseline, experimental)):
                                state = diagnostic(lib)
                                self.assertEqual(
                                    (state.pending, state.submitted,
                                     state.released, state.skipped),
                                    (oracle.pending, oracle.submitted,
                                     oracle.released, oracle.skipped),
                                    (schedule, arrival, tick, i))
                                self.assertEqual(
                                    state.pre_poll_full_steps,
                                    oracle.baseline_full if i == 0
                                    else oracle.extra_full)
                                self.assertEqual(
                                    state.pre_poll_recovered_steps,
                                    oracle.baseline_recovered if i == 0
                                    else oracle.extra_recovered)
                                self.assertEqual(state.simulated_ticks - start[i],
                                                 tick + 1)
                                self.assertEqual((state.active, state.queue_valid,
                                                  state.audio_errors),
                                                 (1, 1, 0))
                                self.assertEqual(lib.mock_audout_pending(),
                                                 oracle.pending)
                                self.assertEqual(lib.mock_audout_released(),
                                                 oracle.released)
                                self.assertEqual(lib.mock_audout_integrity_errors(), 0)
                                # A single 60Hz simulation tick may append
                                # only one PCM block, even if two ACKs arrive.
                                self.assertLessEqual(
                                    state.submitted -
                                    (2 if tick == 0 else previous_submitted[i]),
                                    1)
                            previous_submitted = (
                                diagnostic(baseline).submitted,
                                diagnostic(experimental).submitted)
                            self.assertEqual(
                                baseline.dino_switch_sound_pcm_witness(),
                                experimental.dino_switch_sound_pcm_witness())
                            self.assertEqual(
                                experimental.dino_switch_sound_guest_mid_batch_calls(),
                                oracle.mid_calls)
                            self.assertEqual(
                                experimental.dino_switch_sound_guest_mid_batch_releases(),
                                oracle.mid_released)
                            self.assertEqual(
                                baseline.dino_switch_sound_guest_mid_batch_calls(), 0)
                            tick += 1
                    self.assertEqual(tick, 900)
                    self.assertEqual(oracle.submitted - 2 + oracle.skipped, 900)
                    self.assertEqual(oracle.pending,
                                     2 + oracle.submitted - 2 - oracle.released)
                    if schedule == 'none':
                        self.assertEqual(oracle.mid_released, 0)
                        self.assertEqual(oracle.submitted - 2, 0)
                        self.assertEqual(oracle.skipped, 900)
                    if arrival == 'after-extra':
                        self.assertEqual(oracle.mid_released, 0)
                        self.assertEqual(oracle.extra_full,
                                         oracle.baseline_full)
                    if arrival == 'before-extra' and schedule == 'steady-one':
                        self.assertGreater(oracle.mid_released, 0)
                        self.assertLess(oracle.extra_full,
                                        oracle.baseline_full)
                    if arrival == 'before-extra' and schedule == 'later-only-two':
                        self.assertTrue(saw_double_mid_ack)


if __name__ == '__main__':
    unittest.main()
