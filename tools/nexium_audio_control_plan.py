#!/usr/bin/env python3
"""Pre-registered ROM-free 900-tick host mock audout A/B stimulus.

This deterministic stimulus does NOT control NeXium frame pacing, physical
ack timing, Nintendo Switch audio hardware, or original arcade content.
"""
import argparse
import hashlib
import json
from pathlib import Path

SCHEMA='dino-romfree-controlled-audout-host-plan-v1'
FRAME_PATTERN=(1,2,3,4)
WINDOW_TICKS=150
WINDOW_COUNT=6
PREFILL_TICKS=2


def release_credit(tick):
    if type(tick) is not int or not 0<=tick<900:
        raise ValueError('invalid synthetic audio tick')
    return 2 if tick%13==0 else (1 if tick%3==0 else 0)


def canonical_bytes(plan):
    return json.dumps(plan,sort_keys=True,separators=(',',':'),
                      ensure_ascii=True).encode('ascii')


def make_plan():
    frames=list(FRAME_PATTERN)*(WINDOW_TICKS//sum(FRAME_PATTERN))
    frames=frames*WINDOW_COUNT
    credits=[release_credit(tick) for tick in range(900)]
    base={
        'schema':SCHEMA,
        'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
        'initial_pending_pages':2,
        'prefill_no_release_ticks':PREFILL_TICKS,
        'total_simulation_ticks':900,
        'window_ticks':WINDOW_TICKS,
        'windows':WINDOW_COUNT,
        'frame_sizes':frames,
        'pre_tick_external_release_credits':credits,
        'causal_emulator_audio_improvement_verified':False,
        'physical_switch_audio_verified':False,
        'emulator_frame_pacing_controlled':False,
    }
    base['stimulus_sha256']=hashlib.sha256(canonical_bytes(base)).hexdigest()
    return base


def verify_plan(plan):
    """Reject shape drift, changed seeds, omitted windows and fake hashes."""
    if type(plan) is not dict or plan!=make_plan():
        raise ValueError('unrecognized deterministic ROM-free host stimulus')
    return True


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(argv)
    plan=make_plan()
    try:
        verify_plan(plan)
        with a.out.open('x',encoding='ascii') as f:
            f.write(json.dumps(plan,sort_keys=True)+'\n')
    except (OSError,ValueError) as e:
        print(json.dumps({'schema':SCHEMA,
                          'status':'INCONCLUSIVE_HOST_PLAN_NOT_CREATED',
                          'reason':type(e).__name__}))
        return 1
    print(json.dumps({'schema':SCHEMA,
                      'status':'DETERMINISTIC_HOST_ONLY_AUDIO_STIMULUS',
                      'stimulus_sha256':plan['stimulus_sha256'],
                      'frame_count':len(plan['frame_sizes']),
                      'total_simulation_ticks':900,
                      'start_pending_pages':2,
                      'real_emulator_audio_verified':False},sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
