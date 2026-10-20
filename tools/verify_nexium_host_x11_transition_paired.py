#!/usr/bin/env python3
"""Stage 260 mandatory paired real-NRO X11 image transition sample proof.

Require independently captured X11 image ABSENCE after host command and
a subsequent genuine four-pixel counter + 16-bit guest frame POSITIVE,
both modes. Bound only the observation interval, NOT display onset.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_host_x11_transition as transition
    from tools import verify_nexium_host_frame_token as frame
else:
    import verify_nexium_host_x11_transition as transition
    import verify_nexium_host_frame_token as frame

SCHEMA='dino-nexium-paired-host-x11-sampled-transition-v1'
STATUS='BOTH_REAL_NEXIUM_ABSENT_TO_COUNTER_X11_SAMPLES_NRO_BOUND'

def one(mode,guest,nro):
    if mode not in ('baseline','extra-poll'):
        raise ValueError('not a real NRO mode')
    guest=Path(guest)
    # Rechecks the complete Stage 258 guest libnx input, native frame,
    # X11 pixel/token ID, host command bounds, guest-selected audio
    # mode, 900-tick stress report and full original NRO SHA.
    fresh=transition.verify(guest,nro,mode)
    saved=frame.load_json(guest/'host-x11-transition-bracket-attestation.json')
    if saved!=fresh:
        raise ValueError('stored X11 transition report differs from raw independent data')
    if (fresh.get('status')!=transition.SUCCESS or
        fresh.get('real_negative_x11_pixels_verified') is not True or
        fresh.get('first_positive_token_matches_native_guest_frame') is not True or
        fresh.get('clock_domain')!='HOST_MONOTONIC_ONLY' or
        fresh.get('mode')!=mode or
        fresh.get('first_visible_frame_onset_verified') is not False or
        fresh.get('precise_input_to_display_latency_verified') is not False or
        fresh.get('guest_input_delivery_timestamp_verified') is not False or
        fresh.get('physical_controller_verified') is not False or
        fresh.get('physical_display_verified') is not False or
        fresh.get('gpu_scanout_timestamp_verified') is not False or
        fresh.get('cross_mode_causal_comparison_verified') is not False):
        raise ValueError('false X11 first-frame-onset or physical latency claim')
    t0=fresh['last_negative_xgetimage_begin_offset_us']
    t1=fresh['last_negative_xgetimage_end_offset_us']
    t2=fresh['first_positive_xgetimage_begin_offset_us']
    t3=fresh['first_positive_xgetimage_end_offset_us']
    count=fresh['post_trigger_absent_x11_images']
    if (type(count) is not int or not 1<=count<=199 or
        any(type(t) is not int for t in (t0,t1,t2,t3)) or
        not 0<=t0<=t1<=t2<=t3<=2_500_001):
        raise ValueError('invalid sampled X11 transition range')
    return {
        'mode':mode,
        'observed_two_x11_states_verified':True,
        'post_trigger_x11_absent_samples':count,
        'guest_render_iteration':fresh['guest_render_iteration'],
        'last_absent_x11_capture_begin_us':t0,
        'last_absent_x11_capture_end_us':t1,
        'first_present_x11_capture_begin_us':t2,
        'first_present_x11_capture_end_us':t3,
        'conservative_observed_transition_interval_us':[t0,t3],
        'whole_nro_sha256':fresh['whole_nro_sha256'],
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'first_visible_frame_onset_verified':False,
        'precise_input_to_display_latency_verified':False,
        'guest_input_delivery_timestamp_verified':False,
        'physical_switch_joycon_verified':False,
        'physical_switch_lcd_verified':False,
        'cross_mode_causal_comparison_verified':False,
    }

def verify(baseline_dir,extra_dir,baseline_nro,extra_nro):
    base=one('baseline',baseline_dir,baseline_nro)
    extra=one('extra-poll',extra_dir,extra_nro)
    if base['whole_nro_sha256']==extra['whole_nro_sha256']:
        raise ValueError('two independently compiled NRO modes required')
    return {
        'schema':SCHEMA,'status':STATUS,
        'both_nro_bound_host_x11_state_transitions_verified':True,
        'modes':{'baseline':base,'extra-poll':extra},
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'exact_first_visible_frame_onset_verified':False,
        'precise_input_to_display_latency_verified':False,
        'actual_guest_input_delivery_timestamp_verified':False,
        'physical_switch_joycon_verified':False,
        'physical_switch_lcd_verified':False,
        'gpu_scanout_timestamp_verified':False,
        'cross_mode_causal_comparison_verified':False,
        'audible_speaker_latency_verified':False,
        'original_arcade_graphics_verified':False,
    }

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for field in ('baseline-dir','extra-dir','baseline-nro','extra-nro','out'):
        parser.add_argument('--'+field,type=Path,required=True)
    args=parser.parse_args(argv)
    result=verify(args.baseline_dir,args.extra_dir,
                  args.baseline_nro,args.extra_nro)
    with args.out.open('x',encoding='ascii') as output:
        output.write(json.dumps(result,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
