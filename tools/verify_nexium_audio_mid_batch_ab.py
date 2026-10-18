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
        start=integer(poll['tick_start'],'poll interval start')
        end=integer(poll['tick_end'],'poll interval end')
        calls=integer(poll['poll_calls'],'interval calls')
        ack=integer(poll['poll_released_pages'],'interval ack')
        later_steps=integer(position['later_tick_steps'],'interval steps')
        later_ack=integer(release['batched_later_released_pages'],
                          'interval later released')
        if (start!=idx*150 or
                end!=(idx+1)*150 or
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
    skipped=report['checkpoint_skipped_deltas']
    if (not isinstance(windows,list) or len(windows)!=6 or
            not isinstance(mode,list) or len(mode)!=6 or
            not isinstance(releases,list) or len(releases)!=6 or
            not isinstance(skipped,list) or len(skipped)!=6):
        raise ValueError('missing exposure, skip or page-return windows')
    result=[]
    for i,(w,m,r) in enumerate(zip(windows,mode,releases)):
        # Do not trust side-by-side indices as proof that their time
        # windows align. The production pair is checked more deeply,
        # but this arithmetic helper must also fail closed in isolation.
        for label,window in (
                ('batch position',w),('render mode',m),('page returns',r)):
            if not isinstance(window,dict):
                raise ValueError('malformed '+label+' window')
            start=integer(window['tick_start'],label+' start')
            end=integer(window['tick_end'],label+' end')
            if start!=150*i or end!=150*(i+1):
                raise ValueError('misaligned '+label+' interval')
        first=integer(w['first_tick_steps'],'first tick exposure')
        later=integer(w['later_tick_steps'],'later tick exposure')
        single=integer(m['single_tick_render_steps'],'single tick exposure')
        batch_total=integer(m['batched_render_steps'],'render mode batch steps')
        batch_skips=integer(m['skips_in_batched_render_frames'],
                            'render mode batch skips')
        single_skips=integer(m['skips_in_single_tick_render_frames'],
                             'render mode single skips')
        full_skips=integer(m['full_queue_skips'],'render mode full queue skips')
        checkpoint_skips=integer(skipped[i],'checkpoint skipped delta')
        first_skips=integer(w['first_tick_skips'],'first tick skips')
        later_skips=integer(w['later_tick_skips'],'later tick skips')
        later_returns=integer(r['batched_later_released_pages'],
                              'later tick page returns')
        first_returns=integer(r['batched_first_released_pages'],
                              'first batch tick page returns')
        single_returns=integer(r['single_frame_released_pages'],
                               'single frame page returns')
        if (first+later+single!=150 or
                first+later!=batch_total or
                first_skips+later_skips!=batch_skips or
                first_skips>first or later_skips>later or
                single_skips>single or
                single_skips+batch_skips!=full_skips or
                checkpoint_skips!=full_skips):
            raise ValueError('inconsistent 150-tick exposure/skip partition')
        result.append({
            'tick_start':150*i,
            'tick_end':150*(i+1),
            'single_ticks':single,
            'first_batch_ticks':first,
            'later_batch_ticks':later,
            'single_skips':single_skips,
            'first_batch_skips':first_skips,
            'later_batch_skips':later_skips,
            'single_frame_page_returns':single_returns,
            'first_batch_page_returns':first_returns,
            'later_batch_page_returns':later_returns,
        })
    # The standalone arithmetic helper also reconciles every subwindow
    # with its 900-tick total. This is defense in depth: production uses
    # the independent full ledger validator before calling this helper.
    for position,field in (
            ('single_ticks','single_tick_render_steps'),
            ('first_batch_ticks','batched_first_tick_steps'),
            ('later_batch_ticks','batched_later_tick_steps'),
            ('single_skips','skips_in_single_tick_render_frames'),
            ('first_batch_skips','batched_first_tick_skips'),
            ('later_batch_skips','batched_later_tick_skips'),
            ('single_frame_page_returns','single_frame_released_pages'),
            ('first_batch_page_returns','batched_first_released_pages'),
            ('later_batch_page_returns','batched_later_released_pages')):
        if (sum(w[position] for w in result)!=
                integer(report[field],position+' total')):
            raise ValueError('inconsistent 150-tick summary ledger: '+position)
    all_window_skips=sum(w['single_skips']+w['first_batch_skips']+
                         w['later_batch_skips'] for w in result)
    if (all_window_skips!=integer(report['full_queue_skips'],
                                 '900-tick full queue skips') or
            all_window_skips!=integer(report['audout_blocks_skipped'],
                                     '900-tick audio skips') or
            sum(w['first_batch_ticks']+w['later_batch_ticks']
                for w in result)!=integer(report['batched_render_steps'],
                                          'total batch exposure') or
            sum(w['single_ticks']+w['first_batch_ticks']+
                w['later_batch_ticks'] for w in result)!=
            integer(report['simulation_ticks'],'total simulation ticks') or
            sum(w['first_batch_skips']+w['later_batch_skips']
                for w in result)!=integer(
                    report['skips_in_batched_render_frames'],
                    'total batched frame skips')):
        raise ValueError('inconsistent global 900-tick exposure ledger')
    return result


def queue_start_profile(report):
    """Validated optional starting audout occupancy, never inferred as zero."""
    present=report.get('fixed_ack_headroom_probe_present')
    if present is not True:
        if present is not False and present is not None:
            raise ValueError('noncanonical fixed-ACK queue witness flag')
        # Explicitly absent probes may only carry null witness fields.
        if present is False and any(
                report.get(field) is not None
                for field in cross.FIXED_ACK_FIELDS[1:]):
            raise ValueError('absent fixed-ACK probe claims queue endpoints')
        return None
    start=integer(report['queue_pending_at_stress_start'],
                  'initial queue occupancy')
    end=integer(report['queue_pending_at_stress_end'],
                'final queue occupancy')
    submitted=integer(report['audout_blocks_submitted'],
                      'submitted page total')
    released=integer(report['audout_blocks_released'],
                     'released page total')
    if start>2 or end>2 or start+submitted-released!=end:
        raise ValueError('inconsistent audio queue initial/final occupancy')
    return {'start':start,'end':end}


def queue_checkpoint_profile(report, windows, endpoints):
    """Conserve page ownership at six boundaries; no per-call timestamps."""
    if endpoints is None:
        return None
    pending=endpoints['start']
    out=[]
    for window in windows:
        skipped=(window['single_skips']+window['first_batch_skips']+
                 window['later_batch_skips'])
        submitted=150-skipped
        released=(window['single_frame_page_returns']+
                  window['first_batch_page_returns']+
                  window['later_batch_page_returns'])
        after=pending+submitted-released
        if not 0<=after<=2:
            raise ValueError('150-tick audio queue boundary outside two slots')
        out.append({
            'tick_start':window['tick_start'],
            'tick_end':window['tick_end'],
            'pending_at_start':pending,
            'submitted_in_window':submitted,
            'released_in_window':released,
            'pending_at_end':after,
        })
        pending=after
    if (pending!=endpoints['end'] or
            sum(w['submitted_in_window'] for w in out)!=
            integer(report['audout_blocks_submitted'],'guest submitted pages') or
            sum(w['released_in_window'] for w in out)!=
            integer(report['audout_blocks_released'],'guest released pages')):
        raise ValueError('150-tick audio queue boundaries do not reconcile')
    return out


def compare_batch_exposure(a,b):
    """Descriptive exposure diagnostic; not an audio treatment estimate."""
    left=exposure_profile(a)
    right=exposure_profile(b)
    initial_left=queue_start_profile(a)
    initial_right=queue_start_profile(b)
    queue_left=queue_checkpoint_profile(a,left,initial_left)
    queue_right=queue_checkpoint_profile(b,right,initial_right)
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
    # Initial occupancy is an independent queue-capacity confounder.
    # Final occupancy can be the *result* of changed admission counts,
    # so it is recorded but must NOT be a gate on observed skip deltas.
    endpoints_available=(initial_left is not None and
                         initial_right is not None)
    initial_queue_matched=(
        initial_left['start']==initial_right['start']
        if matched and endpoints_available else None)
    final_queue_matched=(
        initial_left['end']==initial_right['end']
        if matched and endpoints_available else None)
    strictly_matched=(matched and all_returns_matched is True and
                      initial_queue_matched is True)
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
        'baseline_queue_150tick_boundaries':queue_left,
        'experimental_queue_150tick_boundaries':queue_right,
        'baseline_queue_pending_at_stress_start':(
            initial_left['start'] if initial_left is not None else None),
        'baseline_queue_pending_at_stress_end':(
            initial_left['end'] if initial_left is not None else None),
        'experimental_queue_pending_at_stress_start':(
            initial_right['start'] if initial_right is not None else None),
        'experimental_queue_pending_at_stress_end':(
            initial_right['end'] if initial_right is not None else None),
        'matched_exposure_initial_queue_occupancy_matched':
            initial_queue_matched,
        'matched_exposure_final_queue_occupancy_matched':
            final_queue_matched,
        'matched_exposure_initial_queue_shift_confounds_skip_comparison':(
            not initial_queue_matched if initial_queue_matched is not None
            else None),
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
