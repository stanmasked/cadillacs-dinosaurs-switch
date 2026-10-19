#!/usr/bin/env python3
"""ROM-free study of two/three/four pending PCM pages under fixed ACK credits.

Only a hypothetical model: production C remains max-two-pending. One
generation per 60Hz tick; FIFO ACKs; skipped PCM is discarded, never replayed.
Synthetic ACK residence is NOT audible latency or real NeXium timing.
"""
import argparse
import hashlib
import json
from collections import deque
from pathlib import Path

if __package__:
    from tools import nexium_audio_queue_capacity_bound as baseline
else:
    import nexium_audio_queue_capacity_bound as baseline

SCHEMA = 'dino-host-pcm-queue-depth-tradeoff-v1'
DEPTHS = (2, 3, 4)
START_PENDING = 2
TICKS = 900


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True).encode('ascii')


def check_capacity(capacity):
    if type(capacity) is not int or capacity not in DEPTHS:
        raise ValueError('unsupported hypothetical pending capacity')


def exact_max_admissions(credits, capacity):
    """Exact finite-state DP; explores admit and withhold at every tick."""
    baseline.validate_credits(credits)
    check_capacity(capacity)
    states = {START_PENDING: 0}
    for credit in credits:
        next_states = {}
        for pending, total in states.items():
            after_ack = pending - min(pending, credit)
            for append in ((0, 1) if after_ack < capacity else (0,)):
                occupancy = after_ack + append
                next_states[occupancy] = max(
                    next_states.get(occupancy, -1), total + append)
        states = next_states
    return max(states.values())


def fifo_ledger(credits, capacity):
    """Greedy FIFO with unique generation IDs; return only safe counters."""
    baseline.validate_credits(credits)
    check_capacity(capacity)
    queue = deque((-2, -1))  # two equally initialized prefill pages
    admitted = skipped = released = 0
    peak = len(queue)
    max_residence = 0
    residence_sum = 0
    last_returned = -3
    admitted_ticks = []
    for tick, credit in enumerate(credits):
        for _ in range(min(credit, len(queue))):
            generation = queue.popleft()
            if generation <= last_returned:
                raise ValueError('nonmonotone FIFO release')
            last_returned = generation
            age = tick - generation
            if age < 0:
                raise ValueError('negative synthetic queue residence')
            residence_sum += age
            max_residence = max(max_residence, age)
            released += 1
        if len(queue) < capacity:
            queue.append(tick)
            admitted_ticks.append(tick)
            admitted += 1
            peak = max(peak, len(queue))
        else:
            skipped += 1  # discard synthetic PCM, never store for replay
        if admitted + skipped != tick + 1:
            raise ValueError('lost/replayed synthetic tick')
        if len(queue) != START_PENDING + admitted - released:
            raise ValueError('invalid page conservation')
    if any(y <= x for x, y in zip(admitted_ticks, admitted_ticks[1:])):
        raise ValueError('duplicate/out-of-order PCM generation')
    if len(queue) > capacity:
        raise ValueError('queue overflow')
    return {
        'capacity_pages': capacity,
        'initial_pending_pages': START_PENDING,
        'ticks': len(credits),
        'submitted': admitted,
        'skipped': skipped,
        'released': released,
        'pending_end': len(queue),
        'peak_pending': peak,
        'fifo_release_order_valid': True,
        'skipped_pcm_replayed': False,
        'max_synthetic_ack_residence_ticks': max_residence if released else None,
        'sum_synthetic_ack_residence_ticks': residence_sum,
        'oldest_pending_age_at_end_ticks': (
            len(credits) - 1 - queue[0] if queue else None),
    }


def make_report():
    plan_sha, scenarios = baseline.test_cases()
    old = baseline.make_report()
    if old['intertick_plan_sha256'] != plan_sha:
        raise ValueError('original two-page plan drift')
    previous = {x['name']: x for x in old['cases']}
    results = []
    for name, credits in scenarios.items():
        if len(credits) != TICKS:
            raise ValueError('noncanonical synthetic horizon')
        outcomes = []
        for capacity in DEPTHS:
            row = fifo_ledger(credits, capacity)
            optimum = exact_max_admissions(credits, capacity)
            if row['submitted'] != optimum:
                raise ValueError('greedy did not reach exact capacity optimum')
            row['exact_max_admissions'] = optimum
            row['minimum_model_skips'] = TICKS - optimum
            if capacity == 2:
                for a, b in (
                    ('submitted', 'greedy_admissions'),
                    ('skipped', 'unavoidable_skips_within_model'),
                    ('released', 'greedy_releases'),
                    ('pending_end', 'greedy_pending_end'),
                ):
                    if row[a] != previous[name][b]:
                        raise ValueError('stage-204 baseline drift')
            outcomes.append(row)
        results.append({
            'scenario': name,
            'external_credits_sha256': hashlib.sha256(canonical(credits)).hexdigest(),
            'depths': outcomes,
        })
    return {
        'schema': SCHEMA,
        'status': 'ISOLATED_FIFO_DEPTH_MODEL_MATCHES_EXACT_CAPACITY_BOUNDS',
        'scope': 'SYNTHETIC_HOST_MODEL_ONLY_NO_PRODUCTION_CHANGE',
        'source_intertick_plan_sha256': plan_sha,
        'fixed_initial_pending_pages': START_PENDING,
        'ticks_per_scenario': TICKS,
        'capacity_pages_compared': list(DEPTHS),
        'fifo_pcm_generation_order_only': True,
        'credit_arrivals_matched_across_depths': True,
        'ack_residence_is_not_audible_latency': True,
        'production_queue_capacity_modified': False,
        'real_nexium_ack_schedule_verified': False,
        'physical_switch_audio_verified': False,
        'causal_audio_improvement_verified': False,
        'original_arcade_audio_verified': False,
        'scenarios': results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = make_report()
        with args.out.open('x', encoding='ascii') as stream:
            stream.write(json.dumps(report, sort_keys=True) + '\n')
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'status': 'INCONCLUSIVE_FIFO_DEPTH_MODEL',
                          'reason': type(exc).__name__,
                          'physical_switch_audio_verified': False},
                         sort_keys=True))
        return 1
    print(json.dumps({'status': report['status'],
                      'capacity_pages_compared': list(DEPTHS),
                      'real_nexium_ack_schedule_verified': False,
                      'physical_switch_audio_verified': False},
                     sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
