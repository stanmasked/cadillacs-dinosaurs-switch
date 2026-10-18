#!/usr/bin/env python3
"""ROM-free, exact capacity bound for the host-controlled two-page audout queue.

An independent dynamic program tries EVERY legal choice of admitting or
withholding one newly synthesized block at each tick, under a fixed
pre-registered external ACK-credit schedule. The measured production
adapter is tested separately. The exhaustive bound assumes at most two
pending PCM pages, a maximum of ONE new page per game tick, fixed external
credits, no PCM resampling, no backlog playback, and no new service events.
It makes NO assertion about live NeXium timing or physical speaker latency.
"""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from tools import nexium_audio_intertick_phase as phase
    from tools import nexium_audio_control_plan as control
else:
    import nexium_audio_intertick_phase as phase
    import nexium_audio_control_plan as control

SCHEMA = 'dino-host-two-page-capacity-bound-v1'
PATTERNS = ('none', 'steady-one', 'burst-two', 'later-only-two', 'original-mix')
INITIAL_PAGES = 2
MAX_PENDING = 2
MAX_APPEND_PER_TICK = 1


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True).encode('ascii')


def validate_credits(credits):
    if type(credits) is not list or not credits:
        raise ValueError('credits must be a nonempty bounded array')
    if len(credits) > 900:
        raise ValueError('credits longer than declared 900-tick horizon')
    if any(type(value) is not int or value < 0 or value > 2
           for value in credits):
        raise ValueError('credits must be integral 0, 1 or 2')


def possible_optimal_states(credits):
    """Return max admissions for each final pending-page count after any prefix.

    States are (pending pages -> maximum admitted blocks), not a greedy
    simulation. Explicitly branch on admission/no-admission whenever a
    free page exists. Keep the best score per pending-page state.
    """
    validate_credits(credits)
    states = {INITIAL_PAGES: 0}
    for credit in credits:
        next_states = {}
        for pending, admitted in states.items():
            after_release = pending - min(pending, credit)
            for append in ((0, 1) if after_release < MAX_PENDING else (0,)):
                end_pending = after_release + append
                old = next_states.get(end_pending, -1)
                if admitted + append > old:
                    next_states[end_pending] = admitted + append
        states = next_states
    return states


def greedy_ledger(credits):
    validate_credits(credits)
    pending = INITIAL_PAGES
    accepted = skipped = released = 0
    for credit in credits:
        returned = min(pending, credit)
        pending -= returned
        released += returned
        if pending < MAX_PENDING:
            accepted += 1
            pending += 1
        else:
            skipped += 1
    if accepted + skipped != len(credits):
        raise ValueError('invalid host admission ledger')
    if pending != INITIAL_PAGES + accepted - released:
        raise ValueError('invalid synthetic page ownership conservation')
    return {'submitted': accepted, 'skipped': skipped,
            'released': released, 'pending_end': pending}


def test_cases():
    plan = phase.make_plan()
    phase.check_plan(plan)
    positions = [position for frame in plan['frames']
                 for position in range(frame)]
    if len(positions) != 900:
        raise ValueError('unexpected synthetic frame plan')
    values = {}
    for name in PATTERNS:
        credits = []
        for tick, position in enumerate(positions):
            if name == 'none':
                credit = 0
            elif name == 'steady-one':
                credit = 1
            elif name == 'burst-two':
                credit = 2 if tick % 11 == 0 else 0
            elif name == 'later-only-two':
                credit = 2 if position > 0 else 0
            else:
                credit = control.release_credit(tick)
            credits.append(credit)
        values[name] = credits
    return plan['plan_sha256'], values


def make_report():
    plan_sha, cases = test_cases()
    results = []
    for name, credits in cases.items():
        maxima = possible_optimal_states(credits)
        optimum = max(maxima.values())
        production_policy = greedy_ledger(credits)
        if optimum != production_policy['submitted']:
            raise ValueError('greedy admission did not meet exact legal optimum')
        prefixes = []
        for tick in range(150, len(credits) + 1, 150):
            prefixes.append(max(possible_optimal_states(credits[:tick]).values()))
        results.append({
            'name': name,
            'credits_sha256': hashlib.sha256(canonical(credits)).hexdigest(),
            'exhaustive_optimal_admissions': optimum,
            'greedy_admissions': production_policy['submitted'],
            'unavoidable_skips_within_model': len(credits) - optimum,
            'greedy_releases': production_policy['released'],
            'greedy_pending_end': production_policy['pending_end'],
            'max_admissions_at_150_tick_prefixes': prefixes,
        })
    return {
        'schema': SCHEMA,
        'status': 'FIXED_HOST_CREDIT_GREEDY_ADMISSION_EXACTLY_OPTIMAL',
        'scope': 'SYNTHETIC_HOST_TWO_PAGE_QUEUE_ONLY',
        'intertick_plan_sha256': plan_sha,
        'patterns': list(PATTERNS),
        'ticks_per_case': 900,
        'initial_pending_pages': INITIAL_PAGES,
        'max_pending_pages': MAX_PENDING,
        'max_admissions_per_tick': MAX_APPEND_PER_TICK,
        'cases': results,
        'real_guest_ack_schedule_matched_verified': False,
        'physical_switch_audio_verified': False,
        'causal_audio_improvement_verified': False,
        'original_arcade_audio_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = make_report()
        # Fail closed: never overwrite evidence from another run.
        with args.out.open('x', encoding='ascii') as dest:
            dest.write(json.dumps(report, sort_keys=True) + '\n')
    except (OSError, TypeError, ValueError) as exc:
        print(json.dumps({'status': 'INCONCLUSIVE_HOST_QUEUE_BOUND',
                          'reason': type(exc).__name__,
                          'physical_switch_audio_verified': False},
                         sort_keys=True))
        return 1
    print(json.dumps({'status': report['status'],
                      'cases': len(report['cases']),
                      'real_guest_ack_schedule_matched_verified': False,
                      'physical_switch_audio_verified': False},
                     sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
