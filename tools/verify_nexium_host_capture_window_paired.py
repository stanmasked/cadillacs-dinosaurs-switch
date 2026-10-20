#!/usr/bin/env python3
"""Stage 256: REQUIRED paired NRO-bound X11 capture-call interval audit.

Both independently submitted NeXium modes MUST have valid host-monotonic
XGetImage call windows associated with a unique native guest render ID.
These are NOT physical controller, first pixel appearance or latency tests.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_host_capture_window as sample
    from tools import verify_nexium_host_frame_token as frame
else:
    import verify_nexium_host_capture_window as sample
    import verify_nexium_host_frame_token as frame

SCHEMA='dino-nexium-paired-host-x11-capture-call-v1'
STATUS='BOTH_REAL_NEXIUM_X11_CAPTURE_WINDOWS_MODE_AND_FRAME_BOUND'
REQUIRED_FALSE=(
    'precise_input_to_display_latency_verified',
    'actual_guest_input_delivery_timestamp_verified',
    'physical_controller_verified',
    'physical_display_verified',
    'gpu_scanout_timestamp_verified',
)

def one(mode,guest_dir,nro):
    guest=Path(guest_dir)
    # Independently revalidate native guest frame, host 16-bit ID,
    # real libnx Y/X/ZR, 900-tick selected audio mode and NRO digest.
    measured=sample.verify(guest,nro,mode)
    stored=frame.load_json(guest/'host-capture-interval-attestation.json')
    if stored!=measured:
        raise ValueError('saved X11 timing proof not equal to original raw evidence')
    if (measured.get('status')!=sample.BOUND or
        measured.get('host_sampling_interval_verified') is not True or
        measured.get('clock_domain')!='HOST_MONOTONIC_ONLY' or
        any(measured.get(k) is not False for k in REQUIRED_FALSE)):
        raise ValueError('invalid host-only timing evidence or unsupported latency claim')
    start=measured['host_command_completion_to_x11_call_start_us']
    end=measured['host_command_completion_to_x11_call_end_us']
    duration=measured['xgetimage_call_duration_upper_us']
    if not (type(start) is type(end) is type(duration) is int and
            0<=start<=end<=2_500_001 and duration==end-start):
        raise ValueError('host X11 call interval is nonmonotonic')
    return {
        'mode':mode,
        'host_sampling_interval_verified':True,
        'native_render_iteration':measured['matched_native_render_iteration'],
        'host_frame_token_u16':measured['host_frame_token_u16'],
        'host_xgetimage_call_begin_offset_us':start,
        'host_xgetimage_call_end_offset_us':end,
        'host_xgetimage_call_duration_upper_us':duration,
        'nro_sha256':measured['nro_sha256'],
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'guest_input_delivery_timestamp_verified':False,
        'physical_switch_lcd_verified':False,
        'precise_input_to_display_latency_verified':False,
    }

def verify(baseline_dir,extra_dir,baseline_nro,extra_nro):
    base=one('baseline',baseline_dir,baseline_nro)
    experimental=one('extra-poll',extra_dir,extra_nro)
    if base['nro_sha256']==experimental['nro_sha256']:
        raise ValueError('two independently compiled real guest NROs required')
    # Do not compare the two offsets as a causal performance metric:
    # independently scheduled NeXium runs are not paired clock experiments.
    return {
        'schema':SCHEMA,'status':STATUS,
        'both_real_guest_host_x11_capture_call_windows_bound':True,
        'modes':{'baseline':base,'extra-poll':experimental},
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'cross_mode_latency_comparison_verified':False,
        'actual_guest_input_delivery_timestamp_verified':False,
        'precise_input_to_display_latency_verified':False,
        'physical_joycon_verified':False,
        'physical_switch_lcd_verified':False,
        'gpu_scanout_timestamp_verified':False,
        'original_arcade_graphics_verified':False,
        'audible_speaker_latency_verified':False,
    }

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-dir','extra-dir','baseline-nro','extra-nro','out'):
        parser.add_argument('--'+name,required=True,type=Path)
    a=parser.parse_args(argv)
    proof=verify(a.baseline_dir,a.extra_dir,a.baseline_nro,a.extra_nro)
    with a.out.open('x',encoding='ascii') as output:
        output.write(json.dumps(proof,sort_keys=True)+'\n')
    print(json.dumps(proof,sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
