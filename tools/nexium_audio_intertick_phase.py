#!/usr/bin/env python3
"""Pre-register phase-of-release host audout experiment (ROM-free).

The same release *arrival* is offered to both real C adapter variants.
The experimental adapter can poll between guest simulation ticks; baseline
observes the same pending release at the next ordinary tick. This is not
real emulator scheduling, device latency, or proof of audible improvement.
"""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from tools import nexium_audio_control_plan as common
    from tools import nexium_audio_release_corpus as corpus
else:
    import nexium_audio_control_plan as common
    import nexium_audio_release_corpus as corpus

SCHEMA='dino-host-intertick-release-phases-v1'
RESULT_SCHEMA='dino-host-intertick-native-C-observation-v1'
PHASES=('before-extra','after-extra','alternating')


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),
                      ensure_ascii=True).encode('ascii')


def make_plan():
    original=common.make_plan()
    plan={
        'schema':SCHEMA,
        'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
        'original_frame_plan_sha256':original['stimulus_sha256'],
        'initial_pending_pages':2,
        'initial_prefill_ticks':2,
        'frames':original['frame_sizes'],
        'external_credits':original['pre_tick_external_release_credits'],
        'phase_cases':list(PHASES),
        'total_ticks_per_mode_per_case':900,
        'intertick_poll_positions':540,
        'hardware_audio_verified':False,
        'emulator_clock_matched_verified':False,
        'causal_audio_improvement_verified':False,
    }
    plan['plan_sha256']=hashlib.sha256(canonical(plan)).hexdigest()
    return plan


def check_plan(plan):
    if not corpus.exact(plan,make_plan()):
        raise ValueError('altered intertick arrival plan')
    return plan


def is_early(phase,tick,position):
    if position==0:
        return False
    if phase=='before-extra':
        return True
    if phase=='after-extra':
        return False
    if phase=='alternating':
        return tick%2==0
    raise ValueError('unregistered release arrival phase')


def oracle(plan):
    check_plan(plan)
    cases=[]
    for phase in PHASES:
        pending=2
        submitted=released=skipped=early_releases=early_events=0
        polls=tick=0
        prev={'submitted':0,'released':0,'skipped':0,
              'extra_poll_page_releases':0,'early_detection_events':0}
        windows=[]
        for frame in plan['frames']:
            for position in range(frame):
                credits=plan['external_credits'][tick]
                returned=min(pending,credits)
                released+=returned
                pending-=returned
                if position:
                    polls+=1
                    if is_early(phase,tick,position):
                        early_releases+=returned
                        early_events+=int(returned>0)
                if pending<2:
                    pending+=1
                    submitted+=1
                else:
                    skipped+=1
                tick+=1
                if tick%150==0:
                    current={
                        'submitted':submitted,
                        'released':released,
                        'skipped':skipped,
                        'extra_poll_page_releases':early_releases,
                        'early_detection_events':early_events,
                    }
                    delta={name:val-prev[name] for name,val in current.items()}
                    prev=current
                    windows.append({
                        'tick_start':tick-150,'tick_end':tick,
                        'baseline':{k:delta[k] for k in
                                    ('submitted','released','skipped')},
                        'extra-poll':{k:delta[k] for k in
                                    ('submitted','released','skipped')},
                        'extra_poll_page_releases':
                            delta['extra_poll_page_releases'],
                        'early_detection_events':delta['early_detection_events'],
                    })
        if tick!=900 or polls!=540 or len(windows)!=6:
            raise ValueError('bad fixed synthetic release frame clock')
        record={'phase':phase,
                'baseline':{'submitted':submitted,'released':released,
                            'skipped':skipped,'pending_end':pending},
                'extra-poll':{'submitted':submitted,'released':released,
                              'skipped':skipped,'pending_end':pending},
                'extra_poll_calls':polls,
                'extra_poll_page_releases':early_releases,
                'early_detection_events':early_events,
                'per_150tick_counters':windows}
        cases.append(record)
    return {
        'schema':RESULT_SCHEMA,
        'status':'THREE_INTERTICK_PHASES_NATIVE_C_MATCHED_HOST_INPUTS',
        'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
        'plan_sha256':plan['plan_sha256'],
        'cases':cases,
        'external_release_arrival_identical_for_modes':True,
        'hardware_audio_verified':False,
        'emulator_clock_matched_verified':False,
        'causal_audio_improvement_verified':False,
    }


def load(path):
    data,_=corpus.read_json(path,100,45000)
    return data


def attest(plan_path,result_path):
    plan=load(plan_path)
    observed=load(result_path)
    expected=oracle(plan)
    if not corpus.exact(observed,expected):
        raise ValueError('intertick C ledgers differ from independent oracle')
    return {
        'schema':'dino-host-intertick-audio-attestation-v1',
        'status':'INTERTICK_PHASES_C_AND_ORACLE_MATCH',
        'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
        'plan_file_sha256':hashlib.sha256(Path(plan_path).read_bytes()).hexdigest(),
        'result_file_sha256':hashlib.sha256(Path(result_path).read_bytes()).hexdigest(),
        'phase_cases':list(PHASES),
        'total_ticks_per_mode_per_case':900,
        'hardware_audio_verified':False,
        'emulator_clock_matched_verified':False,
        'causal_audio_improvement_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--result',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        if (args.plan is None)!=(args.result is None):
            raise ValueError('both input files required for attestation')
        if args.plan is not None:
            value=attest(args.plan,args.result)
        else:
            value=make_plan()
            check_plan(value)
        with args.out.open('x',encoding='ascii') as output:
            output.write(json.dumps(value,sort_keys=True)+'\n')
    except (ValueError,OSError,TypeError,KeyError,OverflowError) as err:
        print(json.dumps({
            'schema':SCHEMA,
            'status':'INCONCLUSIVE_HOST_INTERTICK_EXPERIMENT',
            'reason':type(err).__name__,
            'hardware_audio_verified':False,
            'causal_audio_improvement_verified':False,
        },sort_keys=True))
        return 1
    print(json.dumps({
        'status':'INTERTICK_NATIVE_C_ATTESTED' if args.plan is not None
                 else 'INTERTICK_HOST_PLAN_GENERATED',
        'phase_cases':list(PHASES),
        'emulator_clock_matched_verified':False,
        'hardware_audio_verified':False,
    },sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
