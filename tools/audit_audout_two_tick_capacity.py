#!/usr/bin/env python3
"""ROM-free fixed-release two-tick queue counterfactual.

This is NOT an audout emulator. Device releases are externally specified,
not inferred from queue submissions or console timing. Never claim that
reserve-later scheduling fixes live audio, preserves sound, or is audible.
"""
import argparse
import json


def bounded(value, label):
    if type(value) is not int or not 0 <= value <= 2:
        raise ValueError(label + ' must be an integer from zero to two')
    return value


def simulate(initial_pending, first_releases, later_releases, policy='eager'):
    """Simulate exactly two game ticks, no delay, cap=2, fixed releases."""
    p=bounded(initial_pending,'initial_pending')
    first=bounded(first_releases,'first_releases')
    later=bounded(later_releases,'later_releases')
    if policy not in ('eager','reserve_later'):
        raise ValueError('unknown admission policy')
    if first>p:
        raise ValueError('cannot release more pages than initially pending')
    p-=first
    free_first=2-p
    reserved=policy=='reserve_later' and free_first==1 and later==0
    admitted_first=free_first>0 and not reserved
    if admitted_first:
        p+=1
    after_first=p
    if later>p:
        raise ValueError('cannot release nonexistent pages at second tick')
    p-=later
    admitted_later=p<2
    if admitted_later:
        p+=1
    return {
        'policy':policy,
        'tick_steps':2,
        'queue_limit':2,
        'initial_pending':initial_pending,
        'release_before_first':first,
        'release_before_later':later,
        'reserved_first_tick_slot':reserved,
        'first_tick_admitted':admitted_first,
        'later_tick_admitted':admitted_later,
        'first_tick_skipped':not admitted_first,
        'later_tick_skipped':not admitted_later,
        'submitted_ticks':int(admitted_first)+int(admitted_later),
        'skipped_ticks':int(not admitted_first)+int(not admitted_later),
        'pending_after_first':after_first,
        'pending_after_later':p,
    }


def compare(initial_pending=2, first_releases=1, later_releases=0):
    eager=simulate(initial_pending,first_releases,later_releases,'eager')
    reserved=simulate(initial_pending,first_releases,later_releases,
                      'reserve_later')
    return {
        'schema':'dino-rom-free-two-tick-fixed-release-counterfactual-v1',
        'status':'SYNTHETIC_NO_DEVICE_TIMING_OR_CAUSAL_PROOF',
        'eager_current_policy':eager,
        'reserve_later_hypothesis':reserved,
        'does_reserving_improve_total_admissions':
            reserved['submitted_ticks']>eager['submitted_ticks'],
        'does_reserving_shift_which_tick_is_dropped':
            eager['first_tick_skipped']!=reserved['first_tick_skipped'],
        'simulation_clock_ticks':2,
        'real_guest_execution_authenticated':False,
        'release_schedule_exogenous_and_fixed':True,
        'speaker_audibility_verified':False,
        'latency_verified':False,
        'audio_fix_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--initial-pending',type=int,default=2)
    p.add_argument('--first-releases',type=int,default=1)
    p.add_argument('--later-releases',type=int,default=0)
    args=p.parse_args(argv)
    try:
        out=compare(args.initial_pending,args.first_releases,
                    args.later_releases)
    except ValueError:
        out={
            'schema':'dino-rom-free-two-tick-fixed-release-counterfactual-v1',
            'status':'INCONCLUSIVE_INVALID_SYNTHETIC_SCHEDULE',
            'real_guest_execution_authenticated':False,
            'latency_verified':False,
            'audio_fix_verified':False,
        }
    print(json.dumps(out,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
