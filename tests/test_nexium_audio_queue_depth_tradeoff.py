"""ROM-free exact FIFO queue-depth tradeoff: exhaustive and provenance tests.

Capacities 3/4 are hypothetical and do NOT modify Switch sound code.
"""
from collections import deque
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from tools import nexium_audio_queue_depth_tradeoff as depth
from tools import nexium_audio_queue_capacity_bound as bound


def exhaustive_unpruned(credits, capacity):
    histories = {(2, 0)}
    for count in credits:
        following = set()
        for pending, total in histories:
            after = pending - min(pending, count)
            following.add((after, total))
            if after < capacity:
                following.add((after + 1, total + 1))
        histories = following
    return max(score for _, score in histories)


class QueueDepthTradeoffTests(unittest.TestCase):
    def test_depth_dp_matches_unpruned_short_horizon_policies(self):
        probes = ([0], [1], [2], [0, 2, 0, 1, 2, 2, 0, 1],
                  [2, 2, 0, 0, 1, 2, 0, 2, 1, 0, 1, 2])
        for cap in depth.DEPTHS:
            for credits in probes:
                for size in range(1, len(credits) + 1):
                    with self.subTest(capacity=cap, size=size):
                        part = credits[:size]
                        self.assertEqual(depth.exact_max_admissions(part, cap),
                                         exhaustive_unpruned(part, cap))

    def test_exact_900_tick_depth_tradeoff_and_device_disclaimers(self):
        report = depth.make_report()
        expectations = {
            'none': ((0, 900, None), (1, 899, None), (2, 898, None)),
            'steady-one': ((900, 0, 2), (900, 0, 2), (900, 0, 2)),
            'burst-two': ((164, 736, 11), (165, 735, 21), (166, 734, 22)),
            'later-only-two': ((809, 91, 4), (899, 1, 4), (900, 0, 4)),
            'original-mix': ((416, 484, 6), (417, 483, 9), (418, 482, 11)),
        }
        self.assertEqual(report['status'],
                         'ISOLATED_FIFO_DEPTH_MODEL_MATCHES_EXACT_CAPACITY_BOUNDS')
        self.assertEqual(report['capacity_pages_compared'], [2, 3, 4])
        self.assertEqual(report['fixed_initial_pending_pages'], 2)
        self.assertEqual([x['scenario'] for x in report['scenarios']],
                         list(bound.PATTERNS))
        for case in report['scenarios']:
            for idx, result in enumerate(case['depths']):
                with self.subTest(case=case['scenario'], depth=result['capacity_pages']):
                    submitted, skipped, max_age = expectations[case['scenario']][idx]
                    self.assertEqual(result['capacity_pages'], depth.DEPTHS[idx])
                    self.assertEqual(
                        (result['submitted'], result['skipped'],
                         result['max_synthetic_ack_residence_ticks']),
                        (submitted, skipped, max_age))
                    self.assertEqual(result['exact_max_admissions'], submitted)
                    self.assertEqual(result['minimum_model_skips'], skipped)
                    self.assertEqual(result['submitted'] + result['skipped'], 900)
                    self.assertEqual(result['pending_end'],
                                     2 + submitted - result['released'])
                    self.assertLessEqual(result['peak_pending'],
                                         result['capacity_pages'])
                    self.assertIs(result['fifo_release_order_valid'], True)
                    self.assertIs(result['skipped_pcm_replayed'], False)
        for key in ('production_queue_capacity_modified',
                    'real_nexium_ack_schedule_verified',
                    'physical_switch_audio_verified',
                    'causal_audio_improvement_verified',
                    'original_arcade_audio_verified'):
            self.assertIs(report[key], False)

    def test_depth_two_agrees_with_prior_model(self):
        old = {x['name']: x for x in bound.make_report()['cases']}
        for case in depth.make_report()['scenarios']:
            current = case['depths'][0]
            previous = old[case['scenario']]
            self.assertEqual(current['submitted'], previous['greedy_admissions'])
            self.assertEqual(current['released'], previous['greedy_releases'])
            self.assertEqual(current['pending_end'], previous['greedy_pending_end'])
            self.assertEqual(current['skipped'],
                             previous['unavoidable_skips_within_model'])

    def test_fifo_release_order_and_age_against_separate_queue_model(self):
        for credits, capacity in (([0, 2, 0, 1, 2, 2], 2),
                                  ([2, 0, 1, 2, 0, 0, 2], 3),
                                  ([0, 0, 2, 0, 2, 0, 1, 2], 4)):
            q = deque((-2, -1))
            releases = []
            admitted = dropped = 0
            peak = 2
            for tick, count in enumerate(credits):
                for _ in range(min(count, len(q))):
                    releases.append((q.popleft(), tick))
                if len(q) < capacity:
                    q.append(tick)
                    admitted += 1
                else:
                    dropped += 1
                peak = max(peak, len(q))
            data = depth.fifo_ledger(credits, capacity)
            self.assertEqual((data['submitted'], data['skipped'],
                              data['released'], data['peak_pending']),
                             (admitted, dropped, len(releases), peak))
            self.assertEqual(data['sum_synthetic_ack_residence_ticks'],
                             sum(t - generation for generation, t in releases))
            self.assertEqual(data['max_synthetic_ack_residence_ticks'],
                             max((t - generation for generation, t in releases),
                                 default=None))
            self.assertEqual(data['oldest_pending_age_at_end_ticks'],
                             len(credits) - 1 - q[0] if q else None)

    def test_invalid_credit_and_capacity_values_fail_closed(self):
        for cap in (None, True, 1.0, 1, 5, '2'):
            with self.subTest(capacity=cap), self.assertRaises(ValueError):
                depth.exact_max_admissions([0, 1], cap)
        for credits in (None, (), [False], [-1], [3], [1.5], [0] * 901):
            with self.subTest(credits=str(credits)[:30]), self.assertRaises(ValueError):
                depth.fifo_ledger(credits, 2)

    def test_cli_creates_exclusive_json_without_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'depth-evidence.json'
            with redirect_stdout(StringIO()):
                self.assertEqual(depth.main(['--out', str(path)]), 0)
            saved = path.read_bytes()
            self.assertEqual(json.loads(saved), depth.make_report())
            with redirect_stdout(StringIO()) as stream:
                self.assertEqual(depth.main(['--out', str(path)]), 1)
            self.assertIn('INCONCLUSIVE_FIFO_DEPTH_MODEL', stream.getvalue())
            self.assertEqual(path.read_bytes(), saved)

    def test_two_pending_production_guard_still_present(self):
        header = Path(__file__).resolve().parents[1] / 'source/dino_audio_queue.h'
        self.assertIn('#define DINO_AUDIO_QUEUE_MAX_PENDING 2u',
                      header.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
