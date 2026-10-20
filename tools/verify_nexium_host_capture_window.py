#!/usr/bin/env python3
"""Stage 255 OPTIONAL: host X11 capture-call window after xdotool command.

This is a bounded interval ON THE HOST MONOTONIC CLOCK between the return
of xdotool keydown('t') and a call to XGetImage that samples a proven
guest-frame-ID marker. It is NOT keydown-to-display latency, frame-onset
time, guest clock synchronization, GPU scanout timing or physical photons.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_host_frame_token_paired as paired
    from tools import verify_nexium_host_frame_token as frame
else:
    import verify_nexium_host_frame_token_paired as paired
    import verify_nexium_host_frame_token as frame

SCHEMA='dino-nexium-host-x11-sample-window-v1'
SUCCESS='HOST_COMMAND_COMPLETION_TO_X11_CAPTURE_WINDOW_WITNESSED'
BOUND='HOST_MONOTONIC_X11_SAMPLE_WINDOW_BOUND_TO_GUEST_FRAME'
INCONCLUSIVE='INCONCLUSIVE_HOST_X11_CAPTURE_INTERVAL'
KEYS={
    'schema','status','host_x11_capture_window_observed','frame_token_u16',
    'post_keydown_command_to_capture_begin_us',
    'post_keydown_command_to_capture_end_us',
    'xgetimage_call_duration_upper_us','clock_domain',
    'precise_input_to_display_latency_verified',
    'actual_guest_input_delivery_timestamp_verified',
    'physical_controller_verified','physical_display_verified',
    'gpu_scanout_timestamp_verified',
}
FALSE_FLAGS=(
    'precise_input_to_display_latency_verified',
    'actual_guest_input_delivery_timestamp_verified',
    'physical_controller_verified','physical_display_verified',
    'gpu_scanout_timestamp_verified',
)


def verify(guest_dir,nro,mode):
    if mode not in ('baseline','extra-poll'):
        raise ValueError('unknown real NRO audio mode')
    guest=Path(guest_dir)
    # Stage 254 replays the full guest-selected-mode, 900-tick stress,
    # actual live HID Y/X/T, X11 4 pixels, 16-bit marker uniqueness,
    # NRO SHA and saved native frame report. Do not trust the saved
    # optional interval JSON to prove any of those independent facts.
    verified=paired.check_mode(mode,guest,nro)
    raw=frame.load_json(guest/'host-capture-window-evidence.json')
    if set(raw)!=KEYS:
        raise ValueError('host interval report unexpected schema')
    if (raw['schema']!=SCHEMA or raw['status']!=SUCCESS or
        raw['host_x11_capture_window_observed'] is not True or
        raw['clock_domain']!='HOST_MONOTONIC_ONLY' or
        type(raw['frame_token_u16']) is not int or
        raw['frame_token_u16']!=verified['x11_token_u16']):
        raise ValueError('host interval sample not bound to proven X11 frame')
    if any(raw[k] is not False for k in FALSE_FLAGS):
        raise ValueError('unsupported physical input/display latency claim')
    start=raw['post_keydown_command_to_capture_begin_us']
    end=raw['post_keydown_command_to_capture_end_us']
    duration=raw['xgetimage_call_duration_upper_us']
    if (any(type(v) is not int for v in (start,end,duration)) or
        not 0<=start<=end<=2_500_001 or duration!=end-start):
        raise ValueError('non-monotonic/out-of-window XGetImage timestamp bounds')
    return {
        'schema':'dino-nexium-host-x11-command-capture-v1',
        'status':BOUND,
        'mode':mode,
        'host_sampling_interval_verified':True,
        'host_command_completion_to_x11_call_start_us':start,
        'host_command_completion_to_x11_call_end_us':end,
        'xgetimage_call_duration_upper_us':duration,
        'matched_native_render_iteration':verified['matched_native_render_iteration'],
        'host_frame_token_u16':verified['x11_token_u16'],
        'nro_sha256':verified['nro_sha256'],
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'precise_input_to_display_latency_verified':False,
        'actual_guest_input_delivery_timestamp_verified':False,
        'physical_controller_verified':False,
        'physical_display_verified':False,
        'gpu_scanout_timestamp_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guest-dir',type=Path,required=True)
    parser.add_argument('--nro',type=Path,required=True)
    parser.add_argument('--mode',required=True,choices=('baseline','extra-poll'))
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        report=verify(args.guest_dir,args.nro,args.mode)
    except (ValueError,TypeError,KeyError,OSError,UnicodeError,
            OverflowError) as exc:
        report={
            'schema':'dino-nexium-host-x11-command-capture-v1',
            'status':INCONCLUSIVE,
            'reason':type(exc).__name__,
            'host_sampling_interval_verified':False,
            'clock_domain':'HOST_MONOTONIC_ONLY',
            'precise_input_to_display_latency_verified':False,
            'actual_guest_input_delivery_timestamp_verified':False,
            'physical_controller_verified':False,
            'physical_display_verified':False,
            'gpu_scanout_timestamp_verified':False,
        }
    with args.out.open('x',encoding='ascii') as handle:
        handle.write(json.dumps(report,sort_keys=True)+'\n')
    print(json.dumps(report,sort_keys=True))
    return 0  # Diagnostic ONLY. An inconclusive is not a pass.


if __name__=='__main__':
    raise SystemExit(main())
