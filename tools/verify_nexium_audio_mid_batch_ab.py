#!/usr/bin/env python3
"""Strict ROM-free A/B witness pairing, not causal or hardware latency proof.

The guest's verified Stage 157 counters must show *zero* additional sweeps
in baseline and precisely one sweep per later batched tick in experimental.
These reports are observations from different uncontrolled executions.
"""
import argparse
import json
from pathlib import Path
if __package__:
    from tools import compare_nexium_audio_stress_runs as cross
else:
    import compare_nexium_audio_stress_runs as cross

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



def exposure_profile(report):
    """Extract validated render exposure, without pretending clocks matched."""
    windows=report['checkpoint_batch_position_intervals']
    mode=report['checkpoint_mode_intervals']
    releases=report['checkpoint_release_position_intervals']
    if (not isinstance(windows,list) or len(windows)!=6 or
            not isinstance(mode,list) or len(mode)!=6 or
            not isinstance(releases,list) or len(releases)!=6):
        raise ValueError('missing exposure or page-return windows')
    result=[]
    for i,(w,m,r) in enumerate(zip(windows,mode,releases)):
        first=integer(w['first_tick_steps'],'first tick exposure')
        later=integer(w['later_tick_steps'],'later tick exposure')
        single=integer(m['single_tick_render_steps'],'single tick exposure')
        first_skips=integer(w['first_tick_skips'],'first tick skips')
        later_skips=integer(w['later_tick_skips'],'later tick skips')
        later_returns=integer(r['batched_later_released_pages'],
                              'later tick page returns')
        first_returns=integer(r['batched_first_released_pages'],
                              'first batch tick page returns')
        single_returns=integer(r['single_frame_released_pages'],
                               'single frame page returns')
        if (first+later+single!=150 or
                first_skips>first or later_skips>later or
                w['tick_start']!=150*i or w['tick_end']!=150*(i+1) or
                r['tick_start']!=150*i or r['tick_end']!=150*(i+1)):
            raise ValueError('inconsistent 150-tick exposure partition')
        result.append({
            'tick_start':150*i,
            'tick_end':150*(i+1),
            'single_ticks':single,
            'first_batch_ticks':first,
            'later_batch_ticks':later,
            'first_batch_skips':first_skips,
            'later_batch_skips':later_skips,
            'single_frame_page_returns':single_returns,
            'first_batch_page_returns':first_returns,
            'later_batch_page_returns':later_returns,
        })
    for position,field in (
            ('single_frame_page_returns','single_frame_released_pages'),
            ('first_batch_page_returns','batched_first_released_pages'),
            ('later_batch_page_returns','batched_later_released_pages')):
        if (sum(w[position] for w in result)!=
                integer(report[field],position+' total')):
            raise ValueError('inconsistent 150-tick page-return ledger: '+position)
    return result


def compare_batch_exposure(a,b):
    """Descriptive exposure diagnostic; not an audio treatment estimate."""
    left=exposure_profile(a)
    right=exposure_profile(b)
    fields=('single_ticks','first_batch_ticks','later_batch_ticks')
    matched=all(all(x[k]==y[k] for k in fields)
                for x,y in zip(left,right))
    # Only compare skips inside matching coarse tick populations. A pooled
    # total can hide opposing per-window changes even when exposure matches.
    skip_windows=([
        {
            'tick_start':x['tick_start'],
            'tick_end':x['tick_end'],
            'extra_minus_baseline_later_skips':(
                y['later_batch_skips']-x['later_batch_skips']),
        }
        for x,y in zip(left,right)
    ] if matched else None)
    improvements=(sum(w['extra_minus_baseline_later_skips']<0
                      for w in skip_windows) if matched else None)
    regressions=(sum(w['extra_minus_baseline_later_skips']>0
                     for w in skip_windows) if matched else None)
    ack_windows=([
        {
            'tick_start':x['tick_start'],
            'tick_end':x['tick_end'],
            'extra_minus_baseline_later_page_returns':(
                y['later_batch_page_returns']-x['later_batch_page_returns']),
        }
        for x,y in zip(left,right)
    ] if matched else None)
    more_returns=(sum(w['extra_minus_baseline_later_page_returns']>0
                      for w in ack_windows) if matched else None)
    fewer_returns=(sum(w['extra_minus_baseline_later_page_returns']<0
                       for w in ack_windows) if matched else None)
    # Coarse frame exposure is not the whole source of selection bias.
    # Even when the same kinds of ticks occur, different page-return
    # distributions can independently change whether admission succeeds.
    # Keep the earlier descriptive deltas, but expose a strictly gated
    # counterpart that is null whenever return counts differ by window.
    return_counts_matched=(
        all(x['later_batch_page_returns']==y['later_batch_page_returns']
            for x,y in zip(left,right)) if matched else None)
    # Equal later-tick returns alone do not control the audout queue:
    # single-frame/first-batch releases affect the same two slots.
    return_position_fields=(
        'single_frame_page_returns',
        'first_batch_page_returns',
        'later_batch_page_returns',
    )
    all_returns_matched=(
        all(all(x[k]==y[k] for k in return_position_fields)
            for x,y in zip(left,right)) if matched else None)
    return_position_windows=([
        {
            'tick_start':x['tick_start'],
            'tick_end':x['tick_end'],
            'extra_minus_baseline_single_frame_page_returns':(
                y['single_frame_page_returns']-x['single_frame_page_returns']),
            'extra_minus_baseline_first_batch_page_returns':(
                y['first_batch_page_returns']-x['first_batch_page_returns']),
            'extra_minus_baseline_later_batch_page_returns':(
                y['later_batch_page_returns']-x['later_batch_page_returns']),
        }
        for x,y in zip(left,right)
    ] if matched else None)
    strictly_matched=(matched and all_returns_matched is True)
    return {
        'per_150tick_batch_exposure_matched':matched,
        'matched_exposure_later_skip_window_deltas':skip_windows,
        'matched_exposure_later_skip_windows_improved':improvements,
        'matched_exposure_later_skip_windows_worsened':regressions,
        'matched_exposure_later_skip_directions_mixed':(
            improvements>0 and regressions>0 if matched else None),
        'matched_exposure_later_ack_window_deltas':ack_windows,
        'matched_exposure_later_ack_windows_increased':more_returns,
        'matched_exposure_later_ack_windows_decreased':fewer_returns,
        'matched_exposure_later_ack_directions_mixed':(
            more_returns>0 and fewer_returns>0 if matched else None),
        'matched_exposure_later_return_counts_matched':return_counts_matched,
        'matched_exposure_return_shift_confounds_skip_comparison':(
            not return_counts_matched if matched else None),
        'matched_exposure_return_position_window_deltas':return_position_windows,
        'matched_exposure_all_position_return_counts_matched':
            all_returns_matched,
        'matched_exposure_any_position_return_shift_confounds_skip_comparison':(
            not all_returns_matched if matched else None),
        'matched_exposure_and_returns_later_skip_window_deltas':(
            skip_windows if strictly_matched else None),
        'matched_exposure_and_returns_later_skip_count_delta':(
            sum(w['extra_minus_baseline_later_skips']
                for w in skip_windows) if strictly_matched else None),
        'exact_frame_pacing_matched':False,
        'baseline_150tick_batch_exposure':left,
        'experimental_150tick_batch_exposure':right,
        # Suppress apparent skip improvements if the exposed tick
        # population differs at this coarse resolution. Even with
        # matched exposure, a rate change is descriptive, not causal.
        'matched_exposure_later_skip_count_delta':(
            sum(y['later_batch_skips']-x['later_batch_skips']
                for x,y in zip(left,right)) if matched else None),
        'matched_exposure_later_ack_count_delta':(
            sum(w['extra_minus_baseline_later_page_returns']
                for w in ack_windows) if matched else None),
    }


def compare(baseline, experimental):
    # Deep validation of every preceding guest stress field and all six
    # checkpoint windows is reused; no raw game ROM or PCM is required.
    pair=cross.compare([Path(baseline),Path(experimental)])
    _,a=cross.read_report(Path(baseline))
    _,b=cross.read_report(Path(experimental))
    first=verify_mode(a,False)
    second=verify_mode(b,True)
    exposure=compare_batch_exposure(a,b)
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
        **exposure,
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
    except (ValueError,OSError,TypeError,KeyError,UnicodeError,OverflowError) as exc:
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
