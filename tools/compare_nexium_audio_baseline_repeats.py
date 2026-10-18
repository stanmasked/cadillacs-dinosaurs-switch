#!/usr/bin/env python3
"""ROM-free two-baseline NeXium audio dispersion; not an A/B effect estimate.

Both reports must independently attest that the optional guest mid-batch
poll was disabled. The paired summary describes run-to-run variation
without interpreting natural host scheduling differences as treatment.
No original ROM, PCM samples or emulator invocation are used here.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import compare_nexium_audio_stress_runs as cross
    from tools import verify_nexium_audio_mid_batch_ab as ab
else:
    import compare_nexium_audio_stress_runs as cross
    import verify_nexium_audio_mid_batch_ab as ab


def compare(first, second):
    first=Path(first)
    second=Path(second)
    # Validate all 900 guest ticks, six checkpoints and all available
    # queue evidence before calculating any descriptive cross-run deltas.
    cross.compare([first,second])
    _,left=cross.read_report(first)
    _,right=cross.read_report(second)
    first_baseline=ab.verify_mode(left,False)
    second_baseline=ab.verify_mode(right,False)
    if (left['guest_mid_batch_extra_poll_released_pages']!=0 or
            right['guest_mid_batch_extra_poll_released_pages']!=0):
        raise ValueError('extra poll acknowledgement in baseline')
    left_profile=ab.exposure_profile(left)
    right_profile=ab.exposure_profile(right)
    # The previous A/B diagnostics are reused purely to describe how the
    # two baselines differed, including queue start and six boundaries.
    exposure=ab.compare_batch_exposure(left,right)
    window_deltas=[
        {
            'tick_start':a['tick_start'],
            'tick_end':a['tick_end'],
            'second_minus_first_single_steps':b['single_ticks']-a['single_ticks'],
            'second_minus_first_first_batch_steps':(
                b['first_batch_ticks']-a['first_batch_ticks']),
            'second_minus_first_later_batch_steps':(
                b['later_batch_ticks']-a['later_batch_ticks']),
            'second_minus_first_skips':(
                b['single_skips']+b['first_batch_skips']+
                b['later_batch_skips']-
                a['single_skips']-a['first_batch_skips']-
                a['later_batch_skips']),
            'second_minus_first_page_returns':(
                b['single_frame_page_returns']+
                b['first_batch_page_returns']+
                b['later_batch_page_returns']-
                a['single_frame_page_returns']-
                a['first_batch_page_returns']-
                a['later_batch_page_returns']),
        }
        for a,b in zip(left_profile,right_profile)
    ]
    return {
        'schema':'dino-ne-xium-baseline-repeatability-v1',
        'status':'UNCONTROLLED_GUEST_BASELINE_REPEATS_DESCRIPTIVE_ONLY',
        'optional_mid_batch_poll_disabled_in_both':True,
        'total_ticks_per_run':900,
        'first':first_baseline,
        'second':second_baseline,
        'second_minus_first_skips':(
            second_baseline['audio_blocks_skipped']-
            first_baseline['audio_blocks_skipped']),
        'second_minus_first_submitted':(
            ab.integer(right['audout_blocks_submitted'],'submitted')-
            ab.integer(left['audout_blocks_submitted'],'submitted')),
        'second_minus_first_released':(
            second_baseline['total_pages_released']-
            first_baseline['total_pages_released']),
        'second_minus_first_later_batch_skips':(
            second_baseline['later_tick_skips']-
            first_baseline['later_tick_skips']),
        'per_150tick_deltas':window_deltas,
        'exposure_and_queue_diagnostics':exposure,
        'independent_guest_execution_authenticated':False,
        'host_workloads_matched':False,
        'exact_frame_pacing_matched':False,
        'causal_audio_improvement_verified':False,
        'physical_switch_audio_verified':False,
        'audio_latency_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first',type=Path,required=True)
    parser.add_argument('--second',type=Path,required=True)
    parser.add_argument('--out',type=Path)
    opts=parser.parse_args(argv)
    try:
        report=compare(opts.first,opts.second)
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,
            OverflowError) as exc:
        report={
            'schema':'dino-ne-xium-baseline-repeatability-v1',
            'status':'INCONCLUSIVE_UNVERIFIED_BASELINE_REPEATABILITY',
            'reason':type(exc).__name__,
            'causal_audio_improvement_verified':False,
            'physical_switch_audio_verified':False,
            'audio_latency_verified':False,
        }
        rc=1
    else:
        rc=0
    line=json.dumps(report,sort_keys=True)+'\n'
    print(line,end='')
    if opts.out is not None:
        opts.out.write_text(line,encoding='ascii')
    return rc


if __name__=='__main__':
    raise SystemExit(main())
