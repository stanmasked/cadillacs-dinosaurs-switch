#!/usr/bin/env python3
"""Strict ROM-free A/B witness pairing, not causal or hardware latency proof.

The guest's verified Stage 157 counters must show *zero* additional sweeps
in baseline and precisely one sweep per later batched tick in experimental.
These reports are observations from different uncontrolled executions.
"""
import argparse
import json
from pathlib import Path
from tools import compare_nexium_audio_stress_runs as cross

POLL_FIELDS=(
    'guest_mid_batch_extra_poll_probe_present',
    'guest_mid_batch_extra_poll_enabled',
    'guest_mid_batch_extra_poll_calls',
    'guest_mid_batch_extra_poll_released_pages',
    'checkpoint_guest_mid_batch_extra_poll_intervals',
)


def integer(value, name):
    if type(value) is not int or not 0 <= value <= 2**32-1:
        raise ValueError('noncanonical '+name)
    return value


def verify_mode(report, expect_enabled):
    if report.get('guest_mid_batch_extra_poll_probe_present') is not True:
        raise ValueError('guest experiment poll probe absent')
    if report.get('guest_mid_batch_extra_poll_enabled') is not expect_enabled:
        raise ValueError('incorrect guest binary experimental flag')
    if (report.get('simulation_ticks')!=900 or
            report.get('queued_buffers_never_above_two') is not True or
            report.get('native_guest_hid_bound') is not True):
        raise ValueError('guest simulation prerequisite absent')
    total_calls=integer(
        report.get('guest_mid_batch_extra_poll_calls'),'extra calls')
    extra_ack=integer(
        report.get('guest_mid_batch_extra_poll_released_pages'),
        'extra acknowledged pages')
    expected_calls=integer(
        report.get('batched_later_tick_steps'),'later tick steps')
    pages=integer(
        report.get('batched_later_released_pages'),'later released pages')
    if (total_calls!=(expected_calls if expect_enabled else 0) or
            extra_ack>pages or extra_ack>2*total_calls):
        raise ValueError('guest experimental call/release totals mismatch')
    poll_windows=report.get('checkpoint_guest_mid_batch_extra_poll_intervals')
    release_windows=report.get('checkpoint_release_position_intervals')
    position_windows=report.get('checkpoint_batch_position_intervals')
    if any(not isinstance(w,list) or len(w)!=6 for w in (
            poll_windows,release_windows,position_windows)):
        raise ValueError('guest experimental windows missing')
    sums=[0,0]
    for idx,(poll,release,position) in enumerate(zip(
            poll_windows,release_windows,position_windows)):
        if (not isinstance(poll,dict) or
                set(poll)!={'tick_start','tick_end',
                           'poll_calls','poll_released_pages'}):
            raise ValueError('guest poll window malformed')
        calls=integer(poll['poll_calls'],'interval calls')
        ack=integer(poll['poll_released_pages'],'interval ack')
        later_steps=integer(position['later_tick_steps'],'interval steps')
        later_ack=integer(release['batched_later_released_pages'],
                          'interval later released')
        if (poll['tick_start']!=idx*150 or
                poll['tick_end']!=(idx+1)*150 or
                calls!=(later_steps if expect_enabled else 0) or
                ack>later_ack or ack>2*calls):
            raise ValueError('guest experimental interval contradiction')
        sums[0]+=calls
        sums[1]+=ack
    if sums!=[total_calls,extra_ack]:
        raise ValueError('guest experimental intervals do not sum')
    return {
        'total_guest_ticks':900,
        'later_batch_ticks':expected_calls,
        'additional_nonblocking_poll_calls':total_calls,
        'pages_released_by_additional_polls':extra_ack,
        'total_pages_released':integer(
            report['audout_blocks_released'],'total releases'),
        'audio_blocks_skipped':integer(
            report['audout_blocks_skipped'],'skipped blocks'),
        'later_tick_skips':integer(
            report['batched_later_tick_skips'],'later skips'),
        'later_tick_page_returns':pages,
        'fixed_ack_max_recoverable_skips_upper_bound':integer(
            report['fixed_ack_max_recoverable_skips_upper_bound'],
            'fixed ack recovery bound'),
    }


def compare(baseline, experimental):
    # Deep validation of every preceding guest stress field and all six
    # checkpoint windows is reused; no raw game ROM or PCM is required.
    pair=cross.compare([Path(baseline),Path(experimental)])
    _,a=cross.read_report(Path(baseline))
    _,b=cross.read_report(Path(experimental))
    first=verify_mode(a,False)
    second=verify_mode(b,True)
    return {
        'schema':'dino-audout-opt-in-mid-batch-ab-descriptive-v2',
        'status':'UNCONTROLLED_GUEST_RUN_DESCRIPTIVE_ONLY',
        'baseline':first,
        'experimental':second,
        'extra_minus_baseline_skips':(
            second['audio_blocks_skipped']-first['audio_blocks_skipped']),
        'extra_minus_baseline_page_returns':(
            second['total_pages_released']-first['total_pages_released']),
        'extra_minus_baseline_later_tick_pages':(
            second['later_tick_page_returns']-
            first['later_tick_page_returns']),
        'preexisting_comparator_status':pair['status'],
        'runtime_and_host_conditions_held_constant':False,
        'independent_guest_execution_authenticated':False,
        'causal_audio_improvement_verified':False,
        'physical_switch_audio_verified':False,
        'audio_latency_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--experimental',type=Path,required=True)
    p.add_argument('--out',type=Path)
    args=p.parse_args(argv)
    try:
        report=compare(args.baseline,args.experimental)
    except (ValueError,OSError,TypeError,UnicodeError,OverflowError) as exc:
        report={
            'schema':'dino-audout-opt-in-mid-batch-ab-descriptive-v2',
            'status':'INCONCLUSIVE_MISSING_OR_INCONSISTENT_AB_GUEST_PROOF',
            'reason':type(exc).__name__,
            'causal_audio_improvement_verified':False,
            'physical_switch_audio_verified':False,
            'audio_latency_verified':False,
        }
        code=1
    else:
        code=0
    line=json.dumps(report,sort_keys=True)+'\n'
    print(line,end='')
    if args.out:
        args.out.write_text(line,encoding='ascii')
    return code


if __name__=='__main__':
    raise SystemExit(main())
