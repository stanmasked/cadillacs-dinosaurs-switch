#!/usr/bin/env python3
"""Stage 262 REQUIRED paired exact-NRO host-X11 ordered sample audit.

For BOTH real NeXium guest modes recompute the entire bounded actual
XGetImage sample-series evidence from raw compact four-RGB/host-clock
records, compare with each saved independent guest attestation, and
enforce prior Stage 260 native guest↔X11 frame and runtime mode gates.

This is NOT first image appearance, physical input-to-display latency,
GPU scanout, or a causal comparison across separately scheduled jobs.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_host_x11_sample_sequence as source
    from tools import verify_nexium_host_frame_token as frame
else:
    import verify_nexium_host_x11_sample_sequence as source
    import verify_nexium_host_frame_token as frame

SCHEMA='dino-nexium-paired-host-x11-full-sample-sequence-v1'
STATUS='BOTH_REAL_NE_XIUM_ORDERED_X11_SAMPLE_SERIES_NRO_BOUND'
NO_CLAIMS=(
    'exact_first_visible_frame_onset_verified',
    'guest_input_delivery_timestamp_verified',
    'physical_controller_verified',
    'physical_display_verified',
    'gpu_scanout_timestamp_verified',
    'cross_mode_causal_comparison_verified',
)

def one(mode,guest_dir,nro):
    if mode not in ('baseline','extra-poll'):
        raise ValueError('unrecognized real guest selected audio mode')
    guest=Path(guest_dir)
    fresh=source.verify(guest,nro,mode)
    stored=frame.load_json(guest/'host-x11-sample-sequence-attestation.json')
    if stored!=fresh:
        raise ValueError('saved sample-series success differs from independent source')
    if (fresh.get('status')!=source.SUCCESS or
        fresh.get('all_sampled_x11_states_ordered_and_bound') is not True or
        fresh.get('mode')!=mode or
        fresh.get('clock_domain')!='HOST_MONOTONIC_ONLY' or
        any(fresh.get(k) is not False for k in NO_CLAIMS)):
        raise ValueError('unbound X11 sample sequence or unsupported hardware claim')
    negative=fresh['negative_x11_samples']
    positive=fresh['positive_x11_samples']
    total=fresh['total_post_command_samples']
    frame_id=fresh['guest_submitted_render_iteration']
    begin=fresh['last_absent_capture_begin_offset_us']
    end=fresh['last_absent_capture_end_offset_us']
    positive_begin=fresh['first_present_capture_begin_offset_us']
    positive_end=fresh['first_present_capture_end_offset_us']
    if (any(type(n) is not int for n in
            (negative,positive,total,frame_id,begin,end,positive_begin,positive_end)) or
        not 1<=negative<=198 or positive!=1 or
        total!=negative+positive or
        not 0<=begin<=end<=positive_begin<=positive_end<=2_500_001 or
        frame_id<0):
        raise ValueError('incorrect complete sampled image count/time range')
    return {
        'mode':mode,
        'all_original_x11_sample_colors_and_time_order_verified':True,
        'number_of_negative_images_after_host_command':negative,
        'number_of_positive_images':positive,
        'total_x11_images':total,
        'guest_submitted_render_iteration':frame_id,
        'last_negative_host_x11_capture_us':[begin,end],
        'first_positive_host_x11_capture_us':[positive_begin,positive_end],
        'nro_whole_sha256':fresh['whole_nro_sha256'],
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'exact_first_visible_frame_onset_verified':False,
        'precise_input_to_display_latency_verified':False,
        'physical_joycon_verified':False,
        'physical_switch_lcd_verified':False,
        'guest_input_delivery_timestamp_verified':False,
        'cross_mode_causal_performance_verified':False,
    }

def verify(baseline_dir,extra_dir,baseline_nro,extra_nro):
    baseline=one('baseline',baseline_dir,baseline_nro)
    extra=one('extra-poll',extra_dir,extra_nro)
    if baseline['nro_whole_sha256']==extra['nro_whole_sha256']:
        raise ValueError('independent guest NRO modes require distinct whole binaries')
    return {
        'schema':SCHEMA,
        'status':STATUS,
        'both_real_ne_xium_ordered_sample_series_verified':True,
        'modes':{'baseline':baseline,'extra-poll':extra},
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'exact_first_visible_frame_onset_verified':False,
        'precise_input_to_display_latency_verified':False,
        'actual_guest_input_delivery_timestamp_verified':False,
        'physical_joycon_verified':False,
        'physical_switch_lcd_verified':False,
        'gpu_scanout_timestamp_verified':False,
        'cross_mode_causal_performance_verified':False,
        'audible_speaker_latency_verified':False,
        'original_arcade_graphics_verified':False,
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for field in ('baseline-dir','extra-dir','baseline-nro','extra-nro','out'):
        p.add_argument('--'+field,type=Path,required=True)
    a=p.parse_args(argv)
    result=verify(a.baseline_dir,a.extra_dir,a.baseline_nro,a.extra_nro)
    # Do not create a success file for any missing/inconclusive evidence.
    with a.out.open('x',encoding='ascii') as output:
        output.write(json.dumps(result,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
