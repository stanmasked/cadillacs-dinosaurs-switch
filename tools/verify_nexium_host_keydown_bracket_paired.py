#!/usr/bin/env python3
"""Stage 258: required paired host-only keydown subprocess/X11 sampling bracket.

Independently recompute each real NRO-bound Stage 257 host-only observation
and demand its saved guest result agree with the raw source, after replaying
the exact Stage 256 NRO, audio-mode, libnx counter and guest↔X11 frame checks.

Not a guest HID receipt timestamp, physical controller-to-LCD latency,
first pixel appearance, audio improvement or cross-mode performance study.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_host_keydown_bracket as keydown
    from tools import verify_nexium_host_frame_token as frame
else:
    import verify_nexium_host_keydown_bracket as keydown
    import verify_nexium_host_frame_token as frame

SCHEMA='dino-nexium-paired-host-keydown-command-brackets-v1'
STATUS='BOTH_REAL_NEXIUM_HOST_KEYDOWN_X11_FRAME_BRACKETS_VERIFIED'

def one(mode,guest_dir,nro):
    if mode not in ('baseline','extra-poll'):
        raise ValueError('wrong real NRO audio mode')
    guest=Path(guest_dir)
    # The single-mode checker explicitly replays Stage 256's
    # NRO-bound actual guest/host frame/mode and 900-tick provenance.
    proof=keydown.verify(guest,nro,mode)
    saved=frame.load_json(guest/'host-keydown-bracket-attestation.json')
    if saved!=proof:
        raise ValueError('saved host xdotool bracket differs from raw recalculation')
    if (proof.get('status')!=keydown.SUCCESS or
        proof.get('host_only_bracket_verified') is not True or
        proof.get('mode')!=mode or
        proof.get('clock_domain')!='HOST_MONOTONIC_ONLY' or
        proof.get('actual_guest_input_delivery_timestamp_verified') is not False or
        proof.get('first_frame_visual_onset_verified') is not False or
        proof.get('physical_controller_verified') is not False or
        proof.get('physical_display_verified') is not False or
        proof.get('guest_host_clock_synchronized') is not False or
        proof.get('cross_mode_causal_comparison_verified') is not False):
        raise ValueError('unsupported hardware or causality claim')
    beg=proof['keydown_invocation_to_x11_call_begin_us']
    end=proof['keydown_invocation_to_x11_call_end_us']
    cmd0=proof['keydown_subprocess_call_duration_floor_us']
    cmd1=proof['keydown_subprocess_call_duration_ceil_us']
    if not (type(beg) is int and type(end) is int and
            type(cmd0) is int and type(cmd1) is int and
            0<=cmd0<=cmd1<=beg<=end<=2_500_001 and cmd1-cmd0<=1):
        raise ValueError('non-monotonic original host command bounds')
    return {
        'mode':mode,
        'host_only_bracket_verified':True,
        'native_render_iteration':proof['matched_native_render_iteration'],
        'host_frame_token_u16':proof['frame_token_u16'],
        'keydown_call_duration_floor_us':cmd0,
        'keydown_call_duration_ceil_us':cmd1,
        'keydown_invocation_to_x11_capture_start_us':beg,
        'keydown_invocation_to_x11_capture_end_us':end,
        'keydown_completion_to_x11_capture_start_us':
            proof['keydown_completion_to_x11_call_begin_us'],
        'keydown_completion_to_x11_capture_end_us':
            proof['keydown_completion_to_x11_call_end_us'],
        'whole_nro_sha256':proof['whole_nro_sha256'],
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'actual_guest_input_delivery_timestamp_verified':False,
        'precise_physical_input_to_display_latency_verified':False,
        'first_visible_frame_onset_verified':False,
        'physical_joycon_verified':False,
        'physical_switch_lcd_verified':False,
        'gpu_scanout_timing_verified':False,
    }

def verify(baseline_dir,extra_dir,baseline_nro,extra_nro):
    baseline=one('baseline',baseline_dir,baseline_nro)
    extra=one('extra-poll',extra_dir,extra_nro)
    if baseline['whole_nro_sha256']==extra['whole_nro_sha256']:
        raise ValueError('distinct real baseline/extra NROs required')
    return {
        'schema':SCHEMA,'status':STATUS,
        'both_nro_bound_host_keydown_x11_brackets_verified':True,
        'modes':{'baseline':baseline,'extra-poll':extra},
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'cross_mode_latency_comparison_verified':False,
        'actual_guest_input_delivery_timestamp_verified':False,
        'precise_physical_input_to_display_latency_verified':False,
        'first_visible_frame_onset_verified':False,
        'physical_joycon_verified':False,
        'physical_switch_lcd_verified':False,
        'gpu_scanout_timing_verified':False,
        'audible_audio_latency_verified':False,
        'original_arcade_graphics_verified':False,
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-dir','extra-dir','baseline-nro','extra-nro','out'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args(argv)
    proof=verify(args.baseline_dir,args.extra_dir,
                 args.baseline_nro,args.extra_nro)
    with args.out.open('x',encoding='ascii') as output:
        output.write(json.dumps(proof,sort_keys=True)+'\n')
    print(json.dumps(proof,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
