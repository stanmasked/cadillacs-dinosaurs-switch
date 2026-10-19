#!/usr/bin/env python3
"""Counterfactual ROM-free queue-depth comparison with occupancy-driven ACKs.

Stage 205 applied identical external ACK credits to different queue depths.
That assumption is relaxed here: the guest-free synthetic service has fixed
*opportunities*, but each release depends on the current queue occupancy
and (for one policy) the configured capacity. Therefore actual ACKs are
NOT held constant between depths and stage-205 fixed-credit optima DO NOT
apply. Synthetic residence is not audio playback latency.
"""
import argparse
import hashlib
import json
from collections import deque
from pathlib import Path

if __package__:
    from tools import nexium_audio_queue_depth_tradeoff as depth
else:
    import nexium_audio_queue_depth_tradeoff as depth

SCHEMA = 'dino-host-pcm-occupancy-feedback-v1'
STATUS = 'DETERMINISTIC_OCCUPANCY_COUPLED_HOST_LEDGER'
SCENARIOS = ('always-ready', 'fixed-two-watermark', 'depth-relative-watermark',
             'stall-then-drain', 'clustered-two-window')
TICKS = 900
WINDOW = 150


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True).encode('ascii')


def opportunity(policy, tick, capacity, occupancy):
    """(number of returned pages, service allowed), BEFORE PCM admission.

    All release decisions are grounded in the pending buffer count; service
    slots themselves are deterministic, not measurements from an emulator.
    """
    depth.check_capacity(capacity)
    if type(tick) is not int or tick < 0 or tick >= TICKS:
        raise ValueError('invalid synthetic tick')
    if type(occupancy) is not int or not 0 <= occupancy <= capacity:
        raise ValueError('invalid synthetic occupancy')
    if policy not in SCENARIOS or type(policy) is not str:
        raise ValueError('unknown synthetic service policy')
    if policy == 'always-ready':
        slot, threshold, quota = True, 1, 1
    elif policy == 'fixed-two-watermark':
        slot, threshold, quota = (tick % 3 == 0), 2, 2
    elif policy == 'depth-relative-watermark':
        slot, threshold, quota = (tick % 3 == 0), capacity, 2
    elif policy == 'stall-then-drain':
        slot, threshold, quota = (tick % 60 >= 20), 2, 1
    else:
        slot, threshold, quota = (tick % 7 in (0, 1)), 2, 2
    return min(occupancy, quota) if slot and occupancy >= threshold else 0


def simulate(policy, capacity, horizon=TICKS):
    """FIFO producer and occupancy-coupled synthetic service for 1..900 ticks."""
    depth.check_capacity(capacity)
    if type(horizon) is not int or not 1 <= horizon <= TICKS:
        raise ValueError('invalid synthetic horizon')
    if type(policy) is not str or policy not in SCENARIOS:
        raise ValueError('unknown synthetic service policy')
    queue = deque((-2, -1))  # identical initial two pages at all depths
    submitted = skipped = released = service_events = 0
    first_service_tick = None
    max_residence = residence_sum = 0
    peak = len(queue)
    last_released_id = -3
    witness = hashlib.sha256()
    windows = []
    window_submitted = window_skipped = window_released = 0
    for tick in range(horizon):
        ack = opportunity(policy, tick, capacity, len(queue))
        if ack > len(queue):
            raise ValueError('synthetic service released an unowned page')
        if ack:
            service_events += 1
            if first_service_tick is None:
                first_service_tick = tick
        for _ in range(ack):
            generated = queue.popleft()
            if generated <= last_released_id:
                raise ValueError('FIFO inversion or duplicate PCM return')
            last_released_id = generated
            age = tick - generated
            if age < 0:
                raise ValueError('negative ACK residence')
            max_residence = max(max_residence, age)
            residence_sum += age
            released += 1
            window_released += 1
            witness.update(canonical([tick, generated]) + b'\n')
        if len(queue) < capacity:
            queue.append(tick)
            submitted += 1
            window_submitted += 1
        else:
            skipped += 1  # this tick is discarded; never buffered/replayed
            window_skipped += 1
        peak = max(peak, len(queue))
        if submitted + skipped != tick + 1:
            raise ValueError('synthetic tick accounting mismatch')
        if len(queue) != 2 + submitted - released:
            raise ValueError('synthetic page ownership mismatch')
        if (tick + 1) % WINDOW == 0 or tick + 1 == horizon:
            windows.append({
                'tick_end': tick + 1,
                'submitted': window_submitted,
                'skipped': window_skipped,
                'released': window_released,
                'pending_end': len(queue),
            })
            window_submitted = window_skipped = window_released = 0
    if peak > capacity:
        raise ValueError('synthetic queue overflow')
    return {
        'capacity_pages': capacity,
        'ticks': horizon,
        'submitted': submitted,
        'skipped': skipped,
        'released': released,
        'pending_end': len(queue),
        'peak_pending': peak,
        'service_events': service_events,
        'first_service_tick': first_service_tick,
        'max_synthetic_ack_residence_ticks': (
            max_residence if released else None),
        'sum_synthetic_ack_residence_ticks': residence_sum,
        'oldest_pending_age_at_end_ticks': (
            horizon - 1 - queue[0] if queue else None),
        'fifo_release_witness_sha256': witness.hexdigest(),
        'windows': windows,
        'pcm_replay_performed': False,
    }


def make_report():
    scenarios = []
    for policy in SCENARIOS:
        rows = [simulate(policy, cap) for cap in depth.DEPTHS]
        if any(row['submitted'] + row['skipped'] != TICKS for row in rows):
            raise ValueError('scheduling dropped a simulation tick')
        if policy == 'always-ready':
            if any(row['skipped'] != 0 or row['released'] != TICKS
                   for row in rows):
                raise ValueError('steady synthetic service baseline drift')
        if policy == 'depth-relative-watermark':
            control = simulate('fixed-two-watermark', 2)
            if rows[0] != control:
                raise ValueError('depth-two service gating disagreement')
        scenarios.append({
            'policy': policy,
            'depths': rows,
            'release_events_match_across_depths': (
                len({row['fifo_release_witness_sha256'] for row in rows}) == 1),
        })
    return {
        'schema': SCHEMA,
        'status': STATUS,
        'scope': 'ISOLATED_OCCUPANCY_COUPLED_SYNTHETIC_AUDIO_SERVICE_ONLY',
        'model_assumptions': {
            'initial_pending_pages': 2,
            'new_pcm_blocks_per_tick_at_most': 1,
            'service_check_before_block_admission': True,
            'fifo_ack_return_order': True,
            'discard_skipped_pcm_without_replay': True,
            'max_synthetic_release_quota_per_tick': 2,
            'opportunity_schedule_pre_registered': True,
            'actual_ack_event_schedule_fixed_across_depths': False,
        },
        'ticks_per_scenario': TICKS,
        'capacity_pages_compared': list(depth.DEPTHS),
        'scenarios': scenarios,
        'production_queue_capacity_modified': False,
        'real_guest_service_policy_verified': False,
        'real_nexium_ack_timing_matched_verified': False,
        'physical_switch_audio_verified': False,
        'original_arcade_audio_verified': False,
        'causal_audio_improvement_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = make_report()
        with args.out.open('x', encoding='ascii') as output:
            output.write(json.dumps(report, sort_keys=True) + '\n')
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({
            'status': 'INCONCLUSIVE_OCCUPANCY_SERVICE_MODEL',
            'reason': type(exc).__name__,
            'real_guest_service_policy_verified': False,
            'physical_switch_audio_verified': False,
        }, sort_keys=True))
        return 1
    print(json.dumps({
        'status': report['status'],
        'policies': len(SCENARIOS),
        'capacities': list(depth.DEPTHS),
        'real_guest_service_policy_verified': False,
        'physical_switch_audio_verified': False,
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
