#!/usr/bin/env python3
"""Stage 259 optional host-X11 sampled-counter transition bracket.

Bound only the interval between a genuinely sampled post-ZR X11 image
lacking the 4-pixel counter pattern and the first subsequent X11 image
containing that pattern AND an exact NRO-bound guest frame token.

This does NOT timestamp first visible frame onset, libnx input, scanout,
photons, physical controller latency or speed differences across CI runs.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_host_keydown_bracket as parent
    from tools import verify_nexium_host_frame_token as frame
    from tools import nexium_host_live_counter_pixel as pixels
else:
    import verify_nexium_host_keydown_bracket as parent
    import verify_nexium_host_frame_token as frame
    import nexium_host_live_counter_pixel as pixels

SCHEMA='dino-nexium-host-x11-transition-bracket-v1'
RAW_SUCCESS='HOST_X11_ABSENT_TO_COUNTER_FRAME_SAMPLE_BRACKET_OBSERVED'
SUCCESS='HOST_X11_COUNTER_IMAGE_SAMPLE_TRANSITION_GUEST_FRAME_BOUND'
INCONCLUSIVE='INCONCLUSIVE_NO_PROVEN_POST_TRIGGER_X11_TRANSITION'
FIELDS={
    'schema','status','post_trigger_absent_x11_images',
    'host_x11_transition_sample_bracket_observed','x11_positive_frame_token_u16',
    'last_negative_x11_pixel_rgb',
    'last_negative_xgetimage_begin_offset_us',
    'last_negative_xgetimage_end_offset_us',
    'first_positive_xgetimage_begin_offset_us',
    'first_positive_xgetimage_end_offset_us','clock_domain',
    'first_visible_frame_onset_verified',
    'precise_input_to_display_latency_verified',
    'guest_input_delivery_timestamp_verified',
    'physical_controller_verified','physical_display_verified',
    'gpu_scanout_timestamp_verified','cross_mode_causal_comparison_verified',
}
FALSE={
    'first_visible_frame_onset_verified',
    'precise_input_to_display_latency_verified',
    'guest_input_delivery_timestamp_verified',
    'physical_controller_verified','physical_display_verified',
    'gpu_scanout_timestamp_verified','cross_mode_causal_comparison_verified',
}

def verify(guest_dir,nro,mode):
    guest=Path(guest_dir)
    prior=parent.verify(guest,nro,mode)
    raw=frame.load_json(guest/'host-x11-transition-bracket-evidence.json')
    if (set(raw)!=FIELDS or raw['schema']!=SCHEMA or
        raw['status']!=RAW_SUCCESS or
        raw['host_x11_transition_sample_bracket_observed'] is not True or
        raw['clock_domain']!='HOST_MONOTONIC_ONLY' or
        any(raw[k] is not False for k in FALSE)):
        raise ValueError('not an authentic host X11 transition sampling bracket')
    count=raw['post_trigger_absent_x11_images']
    token=raw['x11_positive_frame_token_u16']
    negative=raw['last_negative_x11_pixel_rgb']
    if (type(count) is not int or not 1<=count<=199 or
        type(token) is not int or token!=prior['frame_token_u16'] or
        type(negative) is not dict or set(negative)!=set(pixels.POINTS)):
        raise ValueError('missing genuine last negative X11 image')
    for key,value in negative.items():
        if (type(value) is not list or len(value)!=3 or
            any(type(c) is not int or not 0<=c<=255 for c in value)):
            raise ValueError('X11 RGB pixel is missing or malformed')
    if all(tuple(negative[key])==rgb for key,rgb in pixels.EXPECTED.items()):
        raise ValueError('last negative X11 image already contains counter')
    fields=(
        'last_negative_xgetimage_begin_offset_us',
        'last_negative_xgetimage_end_offset_us',
        'first_positive_xgetimage_begin_offset_us',
        'first_positive_xgetimage_end_offset_us')
    values=[raw[k] for k in fields]
    if (any(type(v) is not int for v in values) or
        not 0<=prior['keydown_subprocess_call_duration_floor_us']<=
            values[0]<=values[1]<=values[2]<=values[3]<=2_500_001):
        raise ValueError('host negative image must PRECEDE positive X11 sample')
    if (values[2]!=prior['keydown_invocation_to_x11_call_begin_us'] or
        values[3]!=prior['keydown_invocation_to_x11_call_end_us']):
        raise ValueError('first positive X11 sample not the NRO-bound frame')
    return {
        'schema':'dino-nexium-host-x11-counter-transition-samples-v1',
        'status':SUCCESS,
        'mode':mode,
        'post_trigger_absent_x11_images':count,
        'real_negative_x11_pixels_verified':True,
        'first_positive_token_matches_native_guest_frame':True,
        'guest_render_iteration':prior['matched_native_render_iteration'],
        'last_negative_xgetimage_begin_offset_us':values[0],
        'last_negative_xgetimage_end_offset_us':values[1],
        'first_positive_xgetimage_begin_offset_us':values[2],
        'first_positive_xgetimage_end_offset_us':values[3],
        'conservative_observed_pixel_transition_interval_start_us':values[0],
        'conservative_observed_pixel_transition_interval_end_us':values[3],
        'whole_nro_sha256':prior['whole_nro_sha256'],
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'first_visible_frame_onset_verified':False,
        'precise_input_to_display_latency_verified':False,
        'guest_input_delivery_timestamp_verified':False,
        'physical_controller_verified':False,
        'physical_display_verified':False,
        'gpu_scanout_timestamp_verified':False,
        'cross_mode_causal_comparison_verified':False,
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--guest-dir',type=Path,required=True)
    p.add_argument('--nro',type=Path,required=True)
    p.add_argument('--mode',choices=('baseline','extra-poll'),required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(argv)
    try:
        proof=verify(a.guest_dir,a.nro,a.mode)
    except (OSError,ValueError,UnicodeError,TypeError,KeyError,OverflowError) as exc:
        proof={
            'schema':'dino-nexium-host-x11-counter-transition-samples-v1',
            'status':INCONCLUSIVE,'reason':type(exc).__name__,
            'real_negative_x11_pixels_verified':False,
            'first_positive_token_matches_native_guest_frame':False,
            'clock_domain':'HOST_MONOTONIC_ONLY',
            'first_visible_frame_onset_verified':False,
            'precise_input_to_display_latency_verified':False,
            'physical_controller_verified':False,
            'physical_display_verified':False,
            'cross_mode_causal_comparison_verified':False,
        }
    with a.out.open('x',encoding='ascii') as out:
        out.write(json.dumps(proof,sort_keys=True)+'\n')
    print(json.dumps(proof,sort_keys=True))
    return 0  # Optional. Inconclusive must never be interpreted as a pass.

if __name__=='__main__':
    raise SystemExit(main())
