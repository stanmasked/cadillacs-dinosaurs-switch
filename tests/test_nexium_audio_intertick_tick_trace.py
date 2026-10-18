"""Independent per-tick queue-pressure oracle for the ROM-free ACK phases.

Stage 200 compared the production C baseline/extra adapters with one another
on every tick, and independently validated their six 150-tick ledgers.
This follow-up also checks every intermediate C queue state against a
separately calculated, one-tick-at-a-time mathematical model. In particular,
an early acknowledgement can alter the *diagnostic* pre-poll-full counter
without changing submission throughput. Neither this mock nor its schedule
is hardware, acoustic output, or matched NeXium guest scheduling.
"""
import ctypes
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import nexium_audio_intertick_phase as phase
from test_dino_switch_audout_mock import Diagnostics, ROOT
from test_nexium_audio_intertick_phase import SOURCES


class IndependentTickQueue:
    """Integer-only two-pending-page admission oracle, no C state consulted."""

    def __init__(self):
        # Two independent synthetic prefill steps have already run.
        self.pending = 2
        self.submitted = 2
        self.released = 0
        self.skipped = 0
        self.mid_released = 0
        self.mid_calls = 0
        self.baseline_full = 0
        self.extra_full = 0
        self.baseline_recovered = 0
        self.extra_recovered = 0

    def step(self, credit, position, early):
        before = self.pending
        returned = min(before, credit)
        mid_returned = returned if position and early else 0
        # Only the experimental build has a mid-frame observation point.
        self.mid_calls += int(position > 0)
        self.mid_released += mid_returned

        # The ordinary poll starts with a different observed occupancy if
        # the optional poll has already seen a released page.
        base_full = before >= 2
        extra_before_normal = before - mid_returned
        extra_full = extra_before_normal >= 2
        self.baseline_full += int(base_full)
        self.extra_full += int(extra_full)
        self.baseline_recovered += int(base_full and before - returned < 2)
        self.extra_recovered += int(extra_full and before - returned < 2)

        self.pending = before - returned
        self.released += returned
        if self.pending < 2:
            self.pending += 1
            self.submitted += 1
        else:
            self.skipped += 1
        return mid_returned


class IndependentQueueMathematicsTests(unittest.TestCase):
    def test_diagnostic_pressure_can_shift_without_extra_admissions(self):
        plan = phase.make_plan()
        phase.check_plan(plan)
        reference = phase.oracle(plan)
        snapshots = {}
        for name in phase.PHASES:
            oracle = IndependentTickQueue()
            tick = 0
            for frame in plan['frames']:
                for pos in range(frame):
                    oracle.step(plan['external_credits'][tick],
                                pos, phase.is_early(name, tick, pos))
                    tick += 1
            self.assertEqual(tick, 900)
            expected = next(x for x in reference['cases']
                            if x['phase'] == name)
            self.assertEqual(oracle.mid_calls, 540)
            self.assertEqual(oracle.mid_released,
                             expected['extra_poll_page_releases'])
            self.assertEqual(oracle.submitted - 2,
                             expected['baseline']['submitted'])
            self.assertEqual(oracle.released,
                             expected['baseline']['released'])
            self.assertEqual(oracle.skipped,
                             expected['baseline']['skipped'])
            snapshots[name] = oracle

        before = snapshots['before-extra']
        after = snapshots['after-extra']
        alternating = snapshots['alternating']
        self.assertEqual([x.mid_released
                          for x in (before, after, alternating)],
                         [249, 0, 125])
        self.assertEqual([x.extra_full
                          for x in (before, after, alternating)],
                         [614, 807, 709])
        self.assertEqual([x.extra_recovered
                          for x in (before, after, alternating)],
                         [130, 323, 225])
        self.assertEqual([x.baseline_full
                          for x in (before, after, alternating)],
                         [807] * 3)
        self.assertEqual([x.baseline_recovered
                          for x in (before, after, alternating)],
                         [323] * 3)
        self.assertEqual([x.submitted - 2
                          for x in (before, after, alternating)],
                         [416] * 3)
        self.assertEqual([x.skipped
                          for x in (before, after, alternating)],
                         [484] * 3)


@unittest.skipUnless(shutil.which('gcc'), 'host GCC required for C audio')
class NativeCQueueTickTraceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='dino-ack-trace-C-')
        cls.libs = []
        for enabled in (False, True):
            output = Path(cls.tmp.name) / ('extra.so' if enabled else 'base.so')
            defines = ['-DDINO_EMULATOR_SELFTEST']
            if enabled:
                defines.append('-DDINO_AUDIO_EXPERIMENT_MID_BATCH_POLL')
            cmd = ['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-fPIC', '-shared', '-Itests/mocks', '-Isource',
                   *defines, *SOURCES, '-o', str(output)]
            process = subprocess.run(cmd, cwd=ROOT,
                                     capture_output=True, text=True)
            if process.returncode:
                raise AssertionError('Production C adapter compile failed: ' +
                                     process.stderr)
            lib = ctypes.CDLL(str(output))
            lib.dino_switch_sound_open.restype = ctypes.c_bool
            lib.dino_switch_sound_step.argtypes = [ctypes.c_uint32]
            lib.dino_switch_sound_diagnostics.argtypes = [
                ctypes.POINTER(Diagnostics)]
            lib.dino_switch_sound_pcm_witness.restype = ctypes.c_uint64
            lib.dino_switch_sound_guest_mid_batch_calls.restype = ctypes.c_uint32
            lib.dino_switch_sound_guest_mid_batch_releases.restype = ctypes.c_uint32
            lib.mock_audout_grant_releases.argtypes = [ctypes.c_uint32]
            lib.mock_audout_pending.restype = ctypes.c_uint32
            lib.mock_audout_released.restype = ctypes.c_uint32
            lib.mock_audout_integrity_errors.restype = ctypes.c_uint32
            if enabled:
                lib.dino_switch_sound_guest_mid_batch_poll.restype = None
            cls.libs.append(lib)

    @classmethod
    def tearDownClass(cls):
        for lib in cls.libs:
            lib.dino_switch_sound_close()
        cls.tmp.cleanup()

    @staticmethod
    def diagnostics(lib):
        diag = Diagnostics()
        lib.dino_switch_sound_diagnostics(ctypes.byref(diag))
        return diag

    def test_each_native_tick_and_observer_counter_matches_independent_oracle(self):
        base, extra = self.libs
        plan = phase.make_plan()
        phase.check_plan(plan)
        for name in phase.PHASES:
            for lib in (base, extra):
                lib.dino_switch_sound_close()
                lib.mock_audout_reset()
                self.assertTrue(lib.dino_switch_sound_open())
                lib.dino_switch_sound_step(0)
                lib.dino_switch_sound_step(0)
                self.assertEqual(self.diagnostics(lib).pending, 2)
            starts = [self.diagnostics(lib).simulated_ticks
                      for lib in (base, extra)]
            reference = IndependentTickQueue()
            tick = 0
            for frame in plan['frames']:
                for position in range(frame):
                    credit = plan['external_credits'][tick]
                    early = phase.is_early(name, tick, position)
                    prior_pending = reference.pending
                    ack = min(prior_pending, credit)
                    if position and not early:
                        # The only ordering difference: the experimental
                        # poll sees an empty credit slot *before* the same
                        # external acknowledgement is offered to both.
                        for lib in (base, extra):
                            lib.mock_audout_grant_releases(0)
                        extra.dino_switch_sound_guest_mid_batch_poll()
                        for lib in (base, extra):
                            lib.mock_audout_grant_releases(credit)
                    else:
                        for lib in (base, extra):
                            lib.mock_audout_grant_releases(credit)
                        if position:
                            extra.dino_switch_sound_guest_mid_batch_poll()

                    self.assertEqual(self.diagnostics(base).pending,
                                     prior_pending, (name, tick, 'baseline-mid'))
                    self.assertEqual(self.diagnostics(extra).pending,
                                     prior_pending - (ack if early else 0),
                                     (name, tick, 'extra-mid'))
                    reference.step(credit, position, early)
                    event = 1 << ((tick * 7) % 10)
                    for lib in (base, extra):
                        lib.dino_switch_sound_step(event)
                    for index, lib in enumerate((base, extra)):
                        current = self.diagnostics(lib)
                        self.assertEqual(
                            (current.pending, current.submitted,
                             current.released, current.skipped),
                            (reference.pending, reference.submitted,
                             reference.released, reference.skipped),
                            (name, tick, index, 'queue ledger'))
                        self.assertEqual(current.pre_poll_full_steps,
                                         reference.baseline_full if index == 0
                                         else reference.extra_full,
                                         (name, tick, index, 'pre-poll-full'))
                        self.assertEqual(current.pre_poll_recovered_steps,
                                         reference.baseline_recovered if index == 0
                                         else reference.extra_recovered,
                                         (name, tick, index, 'recovered'))
                        self.assertEqual(current.simulated_ticks - starts[index],
                                         tick + 1)
                        self.assertEqual((current.audio_errors,
                                          current.queue_valid, current.active),
                                         (0, 1, 1))
                        self.assertEqual(lib.mock_audout_pending(),
                                         reference.pending)
                        self.assertEqual(lib.mock_audout_released(),
                                         reference.released)
                        self.assertEqual(lib.mock_audout_integrity_errors(), 0)
                    self.assertEqual(base.dino_switch_sound_pcm_witness(),
                                     extra.dino_switch_sound_pcm_witness(),
                                     (name, tick, 'generated PCM'))
                    self.assertEqual(extra.dino_switch_sound_guest_mid_batch_calls(),
                                     reference.mid_calls)
                    self.assertEqual(extra.dino_switch_sound_guest_mid_batch_releases(),
                                     reference.mid_released)
                    self.assertEqual(base.dino_switch_sound_guest_mid_batch_calls(), 0)
                    tick += 1
            self.assertEqual(tick, 900)
            self.assertEqual(reference.submitted - 2, 416)
            self.assertEqual(reference.skipped, 484)
            self.assertEqual(reference.released, 416)


if __name__ == '__main__':
    unittest.main()
