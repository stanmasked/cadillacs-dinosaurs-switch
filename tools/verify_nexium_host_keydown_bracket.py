#!/usr/bin/env python3
"""Stage 257 OPTIONAL: host xdotool command invocation and X11 sample brackets.

Only bounds two HOST monotonic-clock calls. Does NOT prove physical key press,
libnx guest input delivery, first-frame onset, GPU scanout or display latency.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_host_capture_window as capture
    from tools import verify_nexium_host_frame_token as frame
else:
    import verify_nexium_host_capture_window as capture
    import verify_nexium_host_frame_token as frame

SCHEMA='dino-nexium-host-keydown-call-capture-v1'
RAW_SUCCESS='HOST_KEYDOWN_COMMAND_AND_X11_SAMPLE_BRACKET_WITNESSED'
SUCCESS='HOST_KEYDOWN_SUBPROCESS_AND_X11_SAMPLE_BRACKET_GUEST_FRAME_BOUND'
INCONCLUSIVE='INCONCLUSIVE_NO_BOUND_HOST_KEYDOWN_CALL'
FIELDS={
    'schema','status','host_command_to_x11_bracket_observed','host_frame_token_u16',
    'keydown_command_duration_floor_us','keydown_command_duration_ceil_us',
    'keydown_call_begin_to_x11_begin_us','keydown_call_begin_to_x11_end_us',
    'keydown_call_complete_to_x11_begin_us','keydown_call_complete_to_x11_end_us',
    'clock_domain','guest_input_delivery_timestamp_verified',
    'first_visible_frame_onset_verified','physical_joycon_latency_verified',
    'physical_switch_lcd_latency_verified','gpu_scanout_timestamp_verified',
    'cross_mode_causal_comparison_verified',
}
FALSE_CLAIMS=(
    'guest_input_delivery_timestamp_verified',
    'first_visible_frame_onset_verified','physical_joycon_latency_verified',
    'physical_switch_lcd_latency_verified','gpu_scanout_timestamp_verified',
    'cross_mode_causal_comparison_verified',
)


def verify(guest_dir,nro,mode):
    guest=Path(guest_dir)
    prior=capture.verify(guest,nro,mode)
    raw=frame.load_json(guest/'host-keydown-bracket-evidence.json')
    if set(raw)!=FIELDS or raw['schema']!=SCHEMA or raw['status']!=RAW_SUCCESS:
        raise ValueError('not genuine host keydown X11 interval proof')
    if (raw['host_command_to_x11_bracket_observed'] is not True or
        raw['clock_domain']!='HOST_MONOTONIC_ONLY' or
        raw['host_frame_token_u16']!=prior['host_frame_token_u16'] or
        type(raw['host_frame_token_u16']) is not int or
        any(raw[k] is not False for k in FALSE_CLAIMS)):
        raise ValueError('unsupported clock/frame/physical claim')
    ints=(
        'keydown_command_duration_floor_us','keydown_command_duration_ceil_us',
        'keydown_call_begin_to_x11_begin_us','keydown_call_begin_to_x11_end_us',
        'keydown_call_complete_to_x11_begin_us','keydown_call_complete_to_x11_end_us',
    )
    if any(type(raw[k]) is not int for k in ints):
        raise ValueError('noncanonical host monotonic timing value')
    low=raw['keydown_command_duration_floor_us']
    high=raw['keydown_command_duration_ceil_us']
    first=raw['keydown_call_begin_to_x11_begin_us']
    last=raw['keydown_call_begin_to_x11_end_us']
    after_begin=raw['keydown_call_complete_to_x11_begin_us']
    after_end=raw['keydown_call_complete_to_x11_end_us']
    if (not 0<=low<=high<=2_500_001 or high-low>1 or
        not 0<=after_begin<=after_end<=2_500_001 or
        not 0<=first<=last<=2_500_001):
        raise ValueError('host monotonic interval impossible')
    if (after_begin!=prior['host_command_completion_to_x11_call_start_us'] or
        after_end!=prior['host_command_completion_to_x11_call_end_us']):
        raise ValueError('host capture bounds contradict Stage 256')
    # All six integral µs offsets are derived from one exact host ns
    # clock domain, with independent floor/ceil rounding. Account for
    # rounding but never hide a reversed or inconsistent sample.
    if not (after_begin+low<=first<=after_begin+high and
            after_end+low<=last<=after_end+high):
        raise ValueError('host keydown command and XGetImage windows inconsistent')
    return {
        'schema':'dino-nexium-host-keydown-command-bound-to-frame-v1',
        'status':SUCCESS,
        'mode':mode,'host_only_bracket_verified':True,
        'frame_token_u16':raw['host_frame_token_u16'],
        'matched_native_render_iteration':prior['matched_native_render_iteration'],
        'whole_nro_sha256':prior['nro_sha256'],
        'keydown_subprocess_call_duration_floor_us':low,
        'keydown_subprocess_call_duration_ceil_us':high,
        'keydown_invocation_to_x11_call_begin_us':first,
        'keydown_invocation_to_x11_call_end_us':last,
        'keydown_completion_to_x11_call_begin_us':after_begin,
        'keydown_completion_to_x11_call_end_us':after_end,
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'actual_guest_input_delivery_timestamp_verified':False,
        'first_frame_visual_onset_verified':False,
        'physical_controller_verified':False,
        'physical_display_verified':False,
        'guest_host_clock_synchronized':False,
        'cross_mode_causal_comparison_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--guest-dir',type=Path,required=True)
    p.add_argument('--nro',type=Path,required=True)
    p.add_argument('--mode',choices=('baseline','extra-poll'),required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        report=verify(args.guest_dir,args.nro,args.mode)
    except (OSError,ValueError,UnicodeError,TypeError,KeyError,OverflowError) as exc:
        report={
            'schema':'dino-nexium-host-keydown-command-bound-to-frame-v1',
            'status':INCONCLUSIVE,'reason':type(exc).__name__,
            'host_only_bracket_verified':False,
            'clock_domain':'HOST_MONOTONIC_ONLY',
            'actual_guest_input_delivery_timestamp_verified':False,
            'physical_controller_verified':False,
            'physical_display_verified':False,
            'guest_host_clock_synchronized':False,
            'cross_mode_causal_comparison_verified':False,
        }
    with args.out.open('x',encoding='ascii') as output:
        output.write(json.dumps(report,sort_keys=True)+'\n')
    print(json.dumps(report,sort_keys=True))
    return 0  # An OPTIONAL inconclusive is not a success.


if __name__=='__main__':
    raise SystemExit(main())
