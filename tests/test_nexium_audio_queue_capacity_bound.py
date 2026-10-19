"""Exact ROM-free host queue-capacity bound vs real baseline C adapter.

The DP explores choices to submit or deliberately withhold newly generated
PCM every synthetic tick; C uses the existing greedy production scheduler.
A result here is model-relative, NOT a claim about actual NeXium service ACKs
or an improvement to hardware audio latency.
"""
from contextlib import redirect_stdout
import ctypes
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import nexium_audio_queue_capacity_bound as bound
from test_dino_switch_audout_mock import Diagnostics, ROOT
from test_nexium_audio_intertick_phase import SOURCES
from test_nexium_audio_ack_burst_boundaries import CREDIT_CASES, credit


def explicit_policy_enumeration(credits):
    """Brute-force ALL valid pending/admission histories, no DP pruning."""
    histories = {(2, 0)}
    for amount in credits:
        next_histories = set()
        for pages, accepted in histories:
            remaining = pages - min(pages, amount)
            next_histories.add((remaining, accepted))
            if remaining < 2:
                next_histories.add((remaining + 1, accepted + 1))
        histories = next_histories
    maximum_by_pending = {}
    for pages, accepted in histories:
        maximum_by_pending[pages] = max(maximum_by_pending.get(pages, -1),
                                        accepted)
    return maximum_by_pending


class TwoPageExactBoundTests(unittest.TestCase):
    def test_short_horizons_match_exhaustive_unpruned_paths(self):
        patterns = [
            [0], [1], [2], [0, 2, 0, 1, 2, 0],
            [2, 2, 2, 1, 0, 0, 2],
            [0, 0, 0, 0, 2, 2, 1, 0, 1, 2, 0, 2],
        ]
        for credits in patterns:
            for ticks in range(1, len(credits) + 1):
                prefix = credits[:ticks]
                self.assertEqual(bound.possible_optimal_states(prefix),
                                 explicit_policy_enumeration(prefix))

    def test_all_five_fixed_900_tick_optima_and_conservation(self):
        expected = {
            'none': (0, 900, 0, 2),
            'steady-one': (900, 0, 900, 2),
            'burst-two': (164, 736, 164, 2),
            'later-only-two': (809, 91, 810, 1),
            'original-mix': (416, 484, 416, 2),
        }
        report = bound.make_report()
        self.assertEqual(report['status'],
                         'FIXED_HOST_CREDIT_GREEDY_ADMISSION_EXACTLY_OPTIMAL')
        self.assertEqual([case['name'] for case in report['cases']],
                         list(bound.PATTERNS))
        self.assertEqual(report['ticks_per_case'], 900)
        self.assertEqual(report['max_pending_pages'], 2)
        self.assertEqual(report['max_admissions_per_tick'], 1)
        for case in report['cases']:
            accepted, skipped, released, final_pending = expected[case['name']]
            self.assertEqual((
                case['exhaustive_optimal_admissions'],
                case['unavoidable_skips_within_model'],
                case['greedy_releases'], case['greedy_pending_end']
            ), (accepted, skipped, released, final_pending))
            self.assertEqual(case['greedy_admissions'], accepted)
            self.assertEqual(len(case['max_admissions_at_150_tick_prefixes']), 6)
            self.assertEqual(case['max_admissions_at_150_tick_prefixes'][-1],
                             accepted)
        for key in ('real_guest_ack_schedule_matched_verified',
                    'physical_switch_audio_verified',
                    'causal_audio_improvement_verified',
                    'original_arcade_audio_verified'):
            self.assertIs(report[key], False)

    def test_fixture_credits_match_previously_tested_C_burst_schedules(self):
        plan_sha, cases = bound.test_cases()
        self.assertEqual(plan_sha, bound.phase.make_plan()['plan_sha256'])
        plan = bound.phase.make_plan()
        tick = 0
        for frame in plan['frames']:
            for position in range(frame):
                for name in CREDIT_CASES:
                    self.assertEqual(cases[name][tick],
                                     credit(name, tick, position))
                self.assertEqual(cases['original-mix'][tick],
                                 plan['external_credits'][tick])
                tick += 1
        self.assertEqual(tick, 900)

    def test_reject_invalid_inputs_including_bool_and_oversized(self):
        for data in ([], None, '1', [True], [-1], [3],
                     [1.0], [0]*901, {'a': 1}):
            with self.subTest(value=repr(data)[:40]):
                with self.assertRaises(ValueError):
                    bound.possible_optimal_states(data)
        with self.assertRaises(ValueError):
            bound.greedy_ledger([False])

    def test_cli_exclusive_json_result_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'capacity-bound.json'
            with redirect_stdout(StringIO()):
                self.assertEqual(bound.main(['--out', str(out)]), 0)
            saved = out.read_bytes()
            self.assertEqual(json.loads(saved), bound.make_report())
            with redirect_stdout(StringIO()) as printed:
                self.assertEqual(bound.main(['--out', str(out)]), 1)
            self.assertIn('INCONCLUSIVE_HOST_QUEUE_BOUND', printed.getvalue())
            self.assertEqual(out.read_bytes(), saved)
            self.assertNotIn('private', saved.decode('ascii').lower())


@unittest.skipUnless(shutil.which('gcc'), 'host GCC needed for native C audout')
class BaselineCExactCapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='dino-capacity-C-')
        output = Path(cls.tmp.name) / 'baseline.so'
        cmd = ['gcc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
               '-fPIC', '-shared', '-Itests/mocks', '-Isource',
               '-DDINO_EMULATOR_SELFTEST',
               *SOURCES, '-o', str(output)]
        proc = subprocess.run(cmd, cwd=ROOT,
                              capture_output=True, text=True)
        if proc.returncode:
            raise AssertionError('Actual baseline C build failed: ' +
                                 proc.stderr)
        cls.lib = ctypes.CDLL(str(output))
        cls.lib.dino_switch_sound_open.restype = ctypes.c_bool
        cls.lib.dino_switch_sound_step.argtypes = [ctypes.c_uint32]
        cls.lib.dino_switch_sound_diagnostics.argtypes = [
            ctypes.POINTER(Diagnostics)]
        cls.lib.mock_audout_grant_releases.argtypes = [ctypes.c_uint32]
        cls.lib.mock_audout_integrity_errors.restype = ctypes.c_uint32

    @classmethod
    def tearDownClass(cls):
        cls.lib.dino_switch_sound_close()
        cls.tmp.cleanup()

    def test_native_production_scheduler_hits_exact_dp_bound(self):
        plan_sha, cases = bound.test_cases()
        self.assertEqual(plan_sha, bound.make_report()['intertick_plan_sha256'])
        for case, credits in cases.items():
            with self.subTest(ack_pattern=case):
                self.lib.dino_switch_sound_close()
                self.lib.mock_audout_reset()
                self.assertTrue(self.lib.dino_switch_sound_open())
                self.lib.dino_switch_sound_step(0)
                self.lib.dino_switch_sound_step(0)
                start = Diagnostics()
                self.lib.dino_switch_sound_diagnostics(ctypes.byref(start))
                self.assertEqual(start.pending, 2)
                before_tick = start.simulated_ticks
                for tick, amount in enumerate(credits):
                    self.lib.mock_audout_grant_releases(amount)
                    self.lib.dino_switch_sound_step(1 << ((tick*7) % 10))
                    if (tick+1) % 150 == 0:
                        progress = Diagnostics()
                        self.lib.dino_switch_sound_diagnostics(ctypes.byref(progress))
                        maximum = max(bound.possible_optimal_states(
                            credits[:tick+1]).values())
                        self.assertEqual(progress.submitted-2, maximum,
                                         (case, tick, 'prefix optimum'))
                final = Diagnostics()
                self.lib.dino_switch_sound_diagnostics(ctypes.byref(final))
                maximum = max(bound.possible_optimal_states(credits).values())
                self.assertEqual(final.submitted-2, maximum)
                self.assertEqual(final.skipped, 900-maximum)
                self.assertEqual(final.released,
                                 bound.greedy_ledger(credits)['released'])
                self.assertEqual(final.pending,
                                 2 + (final.submitted-2) - final.released)
                self.assertEqual(final.simulated_ticks-before_tick, 900)
                self.assertEqual((final.active, final.queue_valid,
                                  final.audio_errors), (1, 1, 0))
                self.assertEqual(self.lib.mock_audout_integrity_errors(), 0)


if __name__ == '__main__':
    unittest.main()
