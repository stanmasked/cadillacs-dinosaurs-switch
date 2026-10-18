#!/usr/bin/env python3
"""Independent ROM-free ledger oracle for the matched production C adapter test.

Pure accounting for explicitly supplied synthetic ACK credits, not evidence
of NeXium scheduling, real audio hardware, causal improvement or audibility.
"""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from tools import nexium_audio_control_plan as plan_source
else:
    import nexium_audio_control_plan as plan_source

SCHEMA='dino-controlled-audout-independent-oracle-v1'


def no_duplicate_keys(pairs):
    data={}
    for key,value in pairs:
        if key in data:
            raise ValueError('duplicate JSON key')
        data[key]=value
    return data


def load_bounded_json(path,minimum,maximum):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing or symlinked controlled audout evidence')
    size=path.stat().st_size
    if not minimum<=size<=maximum:
        raise ValueError('invalid size for controlled audout evidence')
    raw=path.read_bytes()
    if not minimum<=len(raw)<=maximum:
        raise ValueError('unstable controlled audout evidence length')
    try:
        return json.loads(raw.decode('ascii'),object_pairs_hook=no_duplicate_keys),raw
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError('invalid controlled audout JSON') from exc


def oracle(plan):
    """Compute occupancy and ACK accounting without calling native C."""
    plan_source.verify_plan(plan)
    pending=2
    submitted=2
    released=skipped=poll_releases=0
    later_polls=tick=0
    rows=[]
    previous_totals={'submitted':0,'released':0,'skipped':0}
    for frame in plan['frame_sizes']:
        for position in range(frame):
            credit=plan['pre_tick_external_release_credits'][tick]
            # Both variants see the fixed credit before the current
            # simulation step; only the extra poll location differs.
            returned=min(credit,pending)
            pending-=returned
            released+=returned
            if position>0:
                later_polls+=1
                poll_releases+=returned
            if pending<2:
                pending+=1
                submitted+=1
            else:
                skipped+=1
            tick+=1
            if tick%150==0:
                counts={'submitted':submitted-2,'released':released,
                        'skipped':skipped}
                increments={key:value-previous_totals[key]
                            for key,value in counts.items()}
                previous_totals=counts
                rows.append({
                    'tick_start':tick-150,'tick_end':tick,
                    'baseline':dict(increments),
                    'extra-poll':dict(increments),
                })
    if tick!=900 or len(rows)!=6 or pending>2:
        raise ValueError('invalid synthetic queue oracle duration')
    return {
        'schema':'dino-controlled-native-audout-comparison-v1',
        'status':'DETERMINISTIC_TWO_C_ADAPTERS_MATCHED_HOST_INPUTS',
        'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
        'stimulus_sha256':plan['stimulus_sha256'],
        'start_pending_pages':2,
        'total_measured_ticks':tick,
        'later_batch_experimental_poll_calls':later_polls,
        'extra_poll_page_releases':poll_releases,
        'per_150tick_counters':rows,
        'baseline_skipped':skipped,
        'experimental_skipped':skipped,
        'baseline_submitted_during_stress':submitted-2,
        'experimental_submitted_during_stress':submitted-2,
        'host_input_schedule_matched':True,
        'observed_queue_accounting_equal':True,
        'guest_frame_pacing_matched_verified':False,
        'emulator_audio_improvement_verified':False,
        'physical_switch_audio_verified':False,
        'original_arcade_audio_verified':False,
    }


def exactly_equal(actual,expected):
    """Keep bool, float and int distinct; Python True == 1 is unsafe."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected,dict):
        return (actual.keys()==expected.keys() and
                all(exactly_equal(actual[key],value)
                    for key,value in expected.items()))
    if isinstance(expected,list):
        return (len(actual)==len(expected) and
                all(exactly_equal(x,y) for x,y in zip(actual,expected)))
    return actual==expected


def verify(plan_file,result_file):
    plan,plan_bytes=load_bounded_json(plan_file,200,8192)
    result,result_bytes=load_bounded_json(result_file,200,8192)
    if type(plan) is not dict or type(result) is not dict:
        raise ValueError('controlled audio evidence must be objects')
    expected=oracle(plan)
    if not exactly_equal(result,expected):
        raise ValueError('native C audout counters do not match independent oracle')
    return {
        'schema':SCHEMA,
        'status':'CONTROLLED_NATIVE_C_LEDGER_MATCHES_INDEPENDENT_ORACLE',
        'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
        'plan_sha256':hashlib.sha256(plan_bytes).hexdigest(),
        'result_sha256':hashlib.sha256(result_bytes).hexdigest(),
        'stimulus_sha256':plan['stimulus_sha256'],
        'measured_guest_ticks':0,
        'host_synthetic_ticks':900,
        'independent_window_count':len(expected['per_150tick_counters']),
        'independent_experimental_poll_calls':expected[
            'later_batch_experimental_poll_calls'],
        'baseline_skipped':expected['baseline_skipped'],
        'experimental_skipped':expected['experimental_skipped'],
        'host_conditions_matched':True,
        'emulator_frame_pacing_matched_verified':False,
        'causal_audio_improvement_verified':False,
        'physical_switch_audio_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        evidence=verify(args.plan,args.result)
        with args.out.open('x',encoding='ascii') as output:
            output.write(json.dumps(evidence,sort_keys=True)+'\n')
    except (OSError,ValueError,TypeError,KeyError,OverflowError) as exc:
        print(json.dumps({
            'schema':SCHEMA,
            'status':'INCONCLUSIVE_CONTROLLED_C_ORACLE_MISMATCH',
            'reason':type(exc).__name__,
            'causal_audio_improvement_verified':False,
            'physical_switch_audio_verified':False,
        },sort_keys=True))
        return 1
    print(json.dumps(evidence,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
