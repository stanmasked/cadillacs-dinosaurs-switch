"""Independent ROM-free audit of occupancy-dependent synthetic PCM ACKs.

The per-tick service schedule and FIFO reference below do not call the
production model's opportunity() or simulate(). This is NOT device testing.
"""
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from tools import nexium_audio_occupancy_service as service
from tools import nexium_audio_queue_depth_tradeoff as depth


def independent_service(policy, tick, capacity, occupancy):
    # Separate table-driven time-slot specification from the implementation.
    slots = {
        'always-ready': (True, 1, 1),
        'fixed-two-watermark': (tick % 3 == 0, 2, 2),
        'depth-relative-watermark': (tick % 3 == 0, capacity, 2),
        'stall-then-drain': (tick % 60 in range(20, 60), 2, 1),
        'clustered-two-window': (tick % 7 == 0 or tick % 7 == 1, 2, 2),
    }
    active, watermark, quota = slots[policy]
    return min(quota, occupancy) if active and occupancy >= watermark else 0


def independent_ledger(policy, capacity, ticks):
    queue = [-2, -1]
    submitted = skipped = released = peak = 0
    peak = 2
    events = []
    windows = []
    ages = []
    first_service_tick = None
    service_events = 0
    sub_window = skip_window = release_window = 0
    for tick in range(ticks):
        ack = independent_service(policy, tick, capacity, len(queue))
        if ack:
            service_events += 1
            first_service_tick = tick if first_service_tick is None else first_service_tick
        for _ in range(ack):
            origin = queue.pop(0)
            ages.append(tick - origin)
            events.append((tick, origin))
            released += 1
            release_window += 1
        if len(queue) < capacity:
            submitted += 1
            sub_window += 1
            queue.append(tick)
        else:
            skipped += 1
            skip_window += 1
        peak = max(peak, len(queue))
        if (tick + 1) % 150 == 0 or tick + 1 == ticks:
            windows.append({'tick_end': tick + 1,
                            'submitted': sub_window,
                            'skipped': skip_window,
                            'released': release_window,
                            'pending_end': len(queue)})
            sub_window = skip_window = release_window = 0
    self_hash = sha256()
    for tick, origin in events:
        self_hash.update(('[%d,%d]\n' % (tick, origin)).encode('ascii'))
    return {
        'capacity_pages': capacity,
        'ticks': ticks,
        'submitted': submitted,
        'skipped': skipped,
        'released': released,
        'pending_end': len(queue),
        'peak_pending': peak,
        'service_events': service_events,
        'first_service_tick': first_service_tick,
        'max_synthetic_ack_residence_ticks': max(ages) if ages else None,
        'sum_synthetic_ack_residence_ticks': sum(ages),
        'oldest_pending_age_at_end_ticks': ticks - 1 - queue[0] if queue else None,
        'fifo_release_witness_sha256': self_hash.hexdigest(),
        'windows': windows,
        'pcm_replay_performed': False,
    }


class OccupancyDrivenACKTests(unittest.TestCase):
    EXPECTED = {
        'always-ready': ((900, 900, 0), (900, 900, 0), (900, 900, 0)),
        'fixed-two-watermark': ((600, 600, 0), (601, 600, 0), (602, 600, 0)),
        'depth-relative-watermark': ((600, 600, 0), (599, 598, 3), (600, 598, 3)),
        'stall-then-drain': ((600, 600, 20), (601, 600, 20), (602, 600, 20)),
        'clustered-two-window': ((258, 258, 0), (515, 514, 0), (516, 514, 0)),
    }

    def test_all_900_tick_ledgers_and_release_hashes_match_independent_reference(self):
        for name in service.SCENARIOS:
            for cap in depth.DEPTHS:
                with self.subTest(policy=name, depth=cap):
                    measured = service.simulate(name, cap)
                    expected = independent_ledger(name, cap, 900)
                    self.assertEqual(measured, expected)
                    self.assertEqual(len(measured['windows']), 6)
                    self.assertEqual(sum(w['submitted'] for w in measured['windows']),
                                     measured['submitted'])
                    self.assertEqual(sum(w['released'] for w in measured['windows']),
                                     measured['released'])
                    self.assertEqual(measured['submitted']+measured['skipped'], 900)
                    self.assertLessEqual(measured['peak_pending'], cap)
                    self.assertEqual(measured['pending_end'],
                                     2 + measured['submitted'] - measured['released'])
                    self.assertFalse(measured['pcm_replay_performed'])

    def test_fixed_900_tick_expected_counts_are_pinned(self):
        for name, triples in self.EXPECTED.items():
            for cap, (admitted, released, first) in zip(depth.DEPTHS, triples):
                with self.subTest(name=name, capacity=cap):
                    observed = service.simulate(name, cap)
                    self.assertEqual(
                        (observed['submitted'], observed['skipped'],
                         observed['released'], observed['first_service_tick']),
                        (admitted, 900-admitted, released, first))

    def test_feedback_invalidates_equal_external_ack_assumption(self):
        measured = service.make_report()
        self.assertEqual(measured['status'], service.STATUS)
        self.assertEqual(measured['capacity_pages_compared'], [2, 3, 4])
        self.assertEqual(len(measured['scenarios']), 5)
        flags = measured['model_assumptions']
        self.assertIs(flags['actual_ack_event_schedule_fixed_across_depths'], False)
        self.assertIs(flags['service_check_before_block_admission'], True)
        for name in ('real_guest_service_policy_verified',
                     'real_nexium_ack_timing_matched_verified',
                     'physical_switch_audio_verified',
                     'original_arcade_audio_verified',
                     'causal_audio_improvement_verified',
                     'production_queue_capacity_modified'):
            self.assertIs(measured[name], False)
        for row in measured['scenarios']:
            for cap, output in zip(depth.DEPTHS, row['depths']):
                self.assertEqual(output['capacity_pages'], cap)
                self.assertEqual(output, independent_ledger(row['policy'], cap, 900))
        # Strong counterexamples: a deeper queue can trigger *fewer*
        # service events when the hypothetical device uses relative gating.
        r = {v['policy']: v for v in measured['scenarios']}
        gated = r['depth-relative-watermark']['depths']
        self.assertEqual([v['service_events'] for v in gated], [300, 299, 299])
        self.assertLess(gated[1]['submitted'], gated[0]['submitted'])
        burst = r['clustered-two-window']['depths']
        self.assertEqual([v['service_events'] for v in burst], [129, 257, 257])
        self.assertFalse(r['clustered-two-window']['release_events_match_across_depths'])
        self.assertTrue(r['always-ready']['release_events_match_across_depths'])

    def test_depth_two_fixed_gate_equals_relative_gate(self):
        a = service.simulate('fixed-two-watermark', 2)
        b = service.simulate('depth-relative-watermark', 2)
        self.assertEqual(a, b)

    def test_small_horizons_and_partial_windows_match_independent_reference(self):
        for horizon in (1, 2, 3, 7, 19, 20, 21, 149, 150, 151):
            for cap in depth.DEPTHS:
                for name in service.SCENARIOS:
                    with self.subTest(h=horizon, cap=cap, policy=name):
                        self.assertEqual(service.simulate(name, cap, horizon),
                                         independent_ledger(name, cap, horizon))

    def test_reject_boolean_negative_bad_policy_occupancy_and_horizon(self):
        for bad in (None, True, 1, 3.0, 'unknown', [], {}):
            with self.subTest(policy=repr(bad)), self.assertRaises(ValueError):
                service.simulate(bad, 2)
        for invalid in (None, True, 0, -1, 3.0, 901):
            with self.subTest(horizon=repr(invalid)), self.assertRaises(ValueError):
                service.simulate('always-ready', 2, invalid)
        for invalid in (-1, None, True, 2.0, 4, 5):
            with self.subTest(occupancy=repr(invalid)), self.assertRaises(ValueError):
                service.opportunity('always-ready', 0, 2, invalid)
        for invalid in (-1, True, None, 1.0, 900):
            with self.subTest(tick=repr(invalid)), self.assertRaises(ValueError):
                service.opportunity('always-ready', invalid, 2, 2)
        with self.assertRaises(ValueError):
            service.opportunity('unknown', 0, 2, 2)

    def test_cli_is_exclusive_and_retains_rom_free_disclaimers(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'host-service-feedback.json'
            with redirect_stdout(StringIO()) as console:
                self.assertEqual(service.main(['--out', str(path)]), 0)
            self.assertIn(service.STATUS, console.getvalue())
            data = path.read_bytes()
            self.assertEqual(json.loads(data), service.make_report())
            with redirect_stdout(StringIO()) as console:
                self.assertEqual(service.main(['--out', str(path)]), 1)
            self.assertIn('INCONCLUSIVE_OCCUPANCY_SERVICE_MODEL',
                          console.getvalue())
            self.assertEqual(path.read_bytes(), data)

    def test_production_two_page_ceiling_is_unchanged(self):
        original = Path(__file__).resolve().parents[1] / 'source/dino_audio_queue.h'
        self.assertIn('#define DINO_AUDIO_QUEUE_MAX_PENDING 2u',
                      original.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
