#!/usr/bin/env python3
"""Fixed ROM-free ACK scenario corpus and a pure-Python queue oracle.

All credits are artificial host-mock stimuli: no NeXium runtime or physical
speaker/console timing is controlled or established by this experiment.
"""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from tools import nexium_audio_control_plan as single
else:
    import nexium_audio_control_plan as single

SCHEMA='dino-controlled-audout-release-corpus-v1'
RESULT_SCHEMA='dino-controlled-audout-release-corpus-result-v1'
NAMES=('none','steady','first-only','later-only','burst-11','original-mix')


def exact(a,b):
    if type(a) is not type(b):
        return False
    if isinstance(b,dict):
        return a.keys()==b.keys() and all(exact(a[k],v) for k,v in b.items())
    if isinstance(b,list):
        return len(a)==len(b) and all(exact(x,y) for x,y in zip(a,b))
    return a==b


def stable_bytes(obj):
    return json.dumps(obj,sort_keys=True,separators=(',',':'),
                      ensure_ascii=True).encode('ascii')


def make_corpus():
    base=single.make_plan()
    frames=base['frame_sizes']
    positions=[]
    for size in frames:
        positions.extend(range(size))
    if len(positions)!=900:
        raise ValueError('incorrect frame-position stimulus')
    scenarios=[]
    for name in NAMES:
        credits=[]
        for tick,position in enumerate(positions):
            if name=='none':
                credit=0
            elif name=='steady':
                credit=1
            elif name=='first-only':
                credit=int(position==0)
            elif name=='later-only':
                credit=int(position>0)
            elif name=='burst-11':
                credit=2 if tick%11==0 else 0
            else:
                credit=single.release_credit(tick)
            credits.append(credit)
        scenarios.append({'name':name,'credits':credits})
    corpus={
        'schema':SCHEMA,
        'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
        'base_stimulus_sha256':base['stimulus_sha256'],
        'start_pending_pages':2,
        'ticks_per_mode':900,
        'frame_sizes':frames,
        'scenarios':scenarios,
        'host_release_credits_identical_for_modes':True,
        'emulator_frame_pacing_matched_verified':False,
        'physical_switch_audio_verified':False,
        'causal_audio_improvement_verified':False,
    }
    corpus['corpus_sha256']=hashlib.sha256(stable_bytes(corpus)).hexdigest()
    return corpus


def verify_corpus(corpus):
    if not exact(corpus,make_corpus()):
        raise ValueError('noncanonical or modified host-only release corpus')
    return True


def oracle(corpus):
    """Compute expected observed C ledgers without consulting the C code."""
    verify_corpus(corpus)
    frames=corpus['frame_sizes']
    outcomes=[]
    for scenario in corpus['scenarios']:
        pending=2
        submitted=released=skipped=poll_releases=poll_calls=0
        previous={'submitted':0,'released':0,'skipped':0,
                  'extra_poll_released_pages':0}
        windows=[]
        tick=0
        for size in frames:
            for position in range(size):
                credit=scenario['credits'][tick]
                ack=min(credit,pending)
                pending-=ack
                released+=ack
                if position>0:
                    poll_calls+=1
                    poll_releases+=ack
                if pending<2:
                    submitted+=1
                    pending+=1
                else:
                    skipped+=1
                tick+=1
                if tick%150==0:
                    totals={
                        'submitted':submitted,
                        'released':released,
                        'skipped':skipped,
                        'extra_poll_released_pages':poll_releases,
                    }
                    diff={k:v-previous[k] for k,v in totals.items()}
                    windows.append({
                        'tick_start':tick-150,
                        'tick_end':tick,
                        'baseline':{k:diff[k] for k in
                                    ('submitted','released','skipped')},
                        'extra-poll':{k:diff[k] for k in
                                    ('submitted','released','skipped')},
                        'extra_poll_released_pages':diff[
                            'extra_poll_released_pages'],
                    })
                    previous=totals
        if tick!=900 or poll_calls!=540 or len(windows)!=6:
            raise ValueError('invalid synthetic host schedule')
        outcomes.append({
            'name':scenario['name'],
            'baseline':{'submitted':submitted,'released':released,
                        'skipped':skipped,'pending_end':pending},
            'extra-poll':{'submitted':submitted,'released':released,
                          'skipped':skipped,'pending_end':pending},
            'extra_poll_calls':poll_calls,
            'extra_poll_released_pages':poll_releases,
            'per_150tick_counters':windows,
        })
    return {
        'schema':RESULT_SCHEMA,
        'status':'MATCHED_SYNTHETIC_C_RELEASE_CORPUS_ONLY',
        'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
        'corpus_sha256':corpus['corpus_sha256'],
        'scenarios':outcomes,
        'frame_pacing_identical_on_host':True,
        'external_release_credits_identical_on_host':True,
        'real_ne_xium_guest_timing_verified':False,
        'physical_switch_audio_verified':False,
        'causal_audio_improvement_verified':False,
    }


def read_json(path,lower=100,upper=85000):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing or symlinked host corpus file')
    if not lower<=path.stat().st_size<=upper:
        raise ValueError('host corpus file outside allowed bounds')
    raw=path.read_bytes()
    if not lower<=len(raw)<=upper:
        raise ValueError('unstable host corpus size')
    def no_duplicates(pairs):
        obj={}
        for k,v in pairs:
            if k in obj:
                raise ValueError('duplicate host corpus JSON key')
            obj[k]=v
        return obj
    try:
        result=json.loads(raw.decode('ascii'),object_pairs_hook=no_duplicates)
    except (UnicodeError,json.JSONDecodeError) as err:
        raise ValueError('invalid host corpus JSON') from err
    return result,raw


def attest(corpus_path,result_path):
    corpus,corpus_raw=read_json(corpus_path)
    recorded,result_raw=read_json(result_path)
    if not exact(recorded,oracle(corpus)):
        raise ValueError('native C ledgers differ from independent oracle')
    return {
        'schema':'dino-controlled-audout-release-corpus-attestation-v1',
        'status':'SIX_NATIVE_C_RELEASE_SCENARIOS_MATCH_ORACLE',
        'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
        'corpus_file_sha256':hashlib.sha256(corpus_raw).hexdigest(),
        'result_file_sha256':hashlib.sha256(result_raw).hexdigest(),
        'corpus_sha256':corpus['corpus_sha256'],
        'verified_scenarios':list(NAMES),
        'verified_ticks_per_mode':900,
        'independent_emulator_guest_runs_verified':False,
        'physical_switch_audio_verified':False,
        'causal_audio_improvement_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--corpus',type=Path)
    p.add_argument('--result',type=Path)
    args=p.parse_args(argv)
    try:
        if bool(args.corpus)!=bool(args.result):
            raise ValueError('provide both controlled host evidence files')
        if args.corpus:
            value=attest(args.corpus,args.result)
        else:
            value=make_corpus()
            verify_corpus(value)
        with args.out.open('x',encoding='ascii') as f:
            f.write(json.dumps(value,sort_keys=True)+'\n')
    except (OSError,ValueError,TypeError,KeyError,OverflowError) as err:
        print(json.dumps({'schema':SCHEMA,'status':'INCONCLUSIVE_HOST_RELEASE_CORPUS',
                          'reason':type(err).__name__,
                          'causal_audio_improvement_verified':False}))
        return 1
    print(json.dumps({'status':'HOST_RELEASE_CORPUS_WITNESSED' if args.corpus
                      else 'HOST_RELEASE_CORPUS_GENERATED',
                      'scenario_count':len(NAMES),
                      'corpus_sha256':value['corpus_sha256']},
                     sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
