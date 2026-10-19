#!/usr/bin/env python3
"""Bound how well *real guest* 900-tick reports locate audout ACK events.

Consumes the existing SHA-256/NRO-bound baseline+extra guest evidence.
Six 150-tick checkpoints classify releases by single/first/later tick
position, but DO NOT record the precise tick of each release, libnx service
arrival timestamps, wall-clock time, speaker latency or a causal A/B study.

The reported event-count interval is a conservative arithmetic OUTER bound
on the number of ticks that could have contained >=1 released page. It does
not assert every integer within the interval is constructible under FIFO
ownership or scheduling. No commercial ROM or PCM payload is read.
"""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from tools import compare_nexium_audio_stress_runs as cross
    from tools import verify_nexium_audio_mid_batch_ab as ab
    from tools import verify_nexium_audio_paired_artifacts as paired
else:
    import compare_nexium_audio_stress_runs as cross
    import verify_nexium_audio_mid_batch_ab as ab
    import verify_nexium_audio_paired_artifacts as paired

SCHEMA='dino-nexium-guest-ack-observability-v1'
GROUPS=(
    ('single','single_tick_render_steps','single_frame_released_pages',
     'single_recovered_after_poll'),
    ('first-batch','first_tick_steps','batched_first_released_pages',
     'first_recovered_after_poll'),
    ('later-batch','later_tick_steps','batched_later_released_pages',
     'later_recovered_after_poll'),
)


def bounded_group(steps, pages, recovered):
    for key,value in (('steps',steps),('pages',pages),
                      ('recovered',recovered)):
        if type(value) is not int or not 0<=value<=900:
            raise ValueError('noncanonical guest '+key)
    if pages>2*steps or recovered>steps or recovered>pages:
        raise ValueError('impossible release-bearing tick bounds')
    lower=max((pages+1)//2,recovered)
    upper=min(pages,steps)
    if lower>upper:
        raise ValueError('guest ACK lower bound exceeds upper bound')
    return {'ticks_in_group':steps,'released_pages':pages,
            'full_pre_poll_recovery_ticks':recovered,
            'release_bearing_ticks_lower_bound':lower,
            'release_bearing_ticks_upper_bound':upper,
            'exact_release_tick_numbers_observed':False}


def guest_ack_profile(report,mode):
    cross.validate(report)  # complete checks on guest-origin 900-tick report
    ab.verify_mode(report,mode=='extra-poll')
    windows=[]
    sum_pages=sum_lower=sum_upper=sum_recovered=0
    for i,(position,release,poll) in enumerate(zip(
            report['checkpoint_batch_position_intervals'],
            report['checkpoint_release_position_intervals'],
            report['checkpoint_batch_position_poll_intervals'])):
        start,end=i*150,(i+1)*150
        for row in (position,release,poll):
            if (type(row) is not dict or row.get('tick_start')!=start or
                    row.get('tick_end')!=end):
                raise ValueError('misaligned 150-tick guest counter windows')
        mode_window=report['checkpoint_mode_intervals'][i]
        if (type(mode_window) is not dict or
                mode_window.get('tick_start')!=start or
                mode_window.get('tick_end')!=end):
            raise ValueError('misaligned mode window')
        groups=[]
        for label,step_key,ack_key,recovered_key in GROUPS:
            steps=(mode_window['single_tick_render_steps']
                   if label=='single' else position[step_key])
            entry=bounded_group(steps,release[ack_key],poll[recovered_key])
            groups.append({'position':label,**entry})
        count=sum(g['released_pages'] for g in groups)
        total_recovery=sum(g['full_pre_poll_recovery_ticks'] for g in groups)
        if (count!=sum(release[k] for _,_,k,_ in GROUPS) or
                count<total_recovery or
                sum(g['ticks_in_group'] for g in groups)!=150):
            raise ValueError('guest positional ACK partition mismatch')
        lower=sum(g['release_bearing_ticks_lower_bound'] for g in groups)
        upper=sum(g['release_bearing_ticks_upper_bound'] for g in groups)
        extra=report['checkpoint_guest_mid_batch_extra_poll_intervals'][i]
        if (type(extra) is not dict or extra.get('tick_start')!=start or
                extra.get('tick_end')!=end):
            raise ValueError('misaligned extra poll window')
        calls=extra['poll_calls']
        extra_pages=extra['poll_released_pages']
        later=groups[2]
        if (type(calls) is not int or type(extra_pages) is not int or
                calls<0 or calls>later['ticks_in_group'] or
                extra_pages<0 or extra_pages>2*calls or
                extra_pages>later['released_pages']):
            raise ValueError('guest optional poll timing evidence inconsistent')
        # Optional-poll ACK count can be distributed across >=ceil(P/2)
        # and <=min(P,calls) calls; it is a subset of later-tick ACKs.
        optional={'poll_calls':calls,'released_pages':extra_pages,
                  'release_bearing_poll_calls_lower_bound':(extra_pages+1)//2,
                  'release_bearing_poll_calls_upper_bound':min(extra_pages,calls),
                  'exact_poll_call_timestamps_observed':False}
        windows.append({
            'tick_start':start,'tick_end':end,
            'observed_pages_released':count,
            'release_bearing_ticks_lower_bound':lower,
            'release_bearing_ticks_upper_bound':upper,
            'pre_poll_full_recovered_ticks':total_recovery,
            'groups':groups,'optional_mid_poll':optional,
            'exact_release_tick_timestamps_observed':False,
        })
        sum_pages+=count
        sum_lower+=lower
        sum_upper+=upper
        sum_recovered+=total_recovery
    if (sum_pages!=report['audout_blocks_released'] or
            sum_recovered!=report['full_recovered_before_admission_ticks'] or
            sum_lower>sum_upper):
        raise ValueError('guest release envelope does not reconcile')
    return {
        'selected_mode':mode,
        'observed_guest_ticks':900,
        'observed_guest_released_pages':sum_pages,
        'release_bearing_ticks_conservative_lower_bound':sum_lower,
        'release_bearing_ticks_conservative_upper_bound':sum_upper,
        'observed_full_pre_poll_recovery_ticks':sum_recovered,
        'exact_release_tick_timestamps_observed':False,
        'exact_libnx_service_ack_arrival_timestamps_observed':False,
        'windows':windows,
    }


def make_report(base_report,base_binding,extra_report,extra_binding,
                base_nro,extra_nro):
    # Validates every report field, both mode bindings, complete NRO bytes,
    # and mode-selected guest-origin optional-poll counters.
    comparison=paired.compare(base_report,base_binding,extra_report,
                              extra_binding,base_nro,extra_nro)
    summaries=[]
    for mode,path in (('baseline',base_report),('extra-poll',extra_report)):
        raw,report=cross.read_report(Path(path))
        summary=guest_ack_profile(report,mode)
        summary['bound_guest_report_sha256']=hashlib.sha256(raw).hexdigest()
        summaries.append(summary)
    if (summaries[0]['bound_guest_report_sha256']!=
            comparison['baseline_report_sha256'] or
            summaries[1]['bound_guest_report_sha256']!=
            comparison['experimental_report_sha256']):
        raise ValueError('guest release envelope not bound to paired reports')
    return {
        'schema':SCHEMA,
        'status':'BOUND_GUEST_ACK_COUNT_ENVELOPE_NO_SERVICE_TIMESTAMPS',
        'scope':'SHA256_NRO_BOUND_GUEST_COUNTERS_ONLY',
        'baseline_guest_nro_sha256':comparison['baseline_guest_nro_sha256'],
        'experimental_guest_nro_sha256':comparison['experimental_guest_nro_sha256'],
        'window_size_ticks':150,'window_count':6,
        'max_queue_pages_during_guest':2,
        'max_pages_releasable_within_one_guest_tick':2,
        'profiles':summaries,
        'real_guest_counter_provenance_validated':True,
        'guest_frame_exposure_matched_verified':False,
        'exact_release_tick_timestamps_observed':False,
        'libnx_service_policy_identified':False,
        'guest_wall_clock_latency_verified':False,
        'physical_switch_audio_verified':False,
        'original_arcade_audio_verified':False,
        'causal_audio_improvement_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('baseline-report','baseline-binding','baseline-nro',
                'experimental-report','experimental-binding','experimental-nro'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=make_report(
            args.baseline_report,args.baseline_binding,args.experimental_report,
            args.experimental_binding,args.baseline_nro,args.experimental_nro)
        with args.out.open('x',encoding='ascii') as dest:
            dest.write(json.dumps(result,sort_keys=True)+'\n')
    except (OSError,ValueError,TypeError,KeyError,OverflowError,
            UnicodeError) as exc:
        print(json.dumps({
            'schema':SCHEMA,
            'status':'INCONCLUSIVE_GUEST_ACK_OBSERVABILITY',
            'reason':type(exc).__name__,
            'exact_release_tick_timestamps_observed':False,
            'physical_switch_audio_verified':False,
        },sort_keys=True))
        return 1
    print(json.dumps({
        'status':result['status'],
        'baseline_pages':result['profiles'][0]['observed_guest_released_pages'],
        'extra_pages':result['profiles'][1]['observed_guest_released_pages'],
        'exact_release_tick_timestamps_observed':False,
        'physical_switch_audio_verified':False,
    },sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
