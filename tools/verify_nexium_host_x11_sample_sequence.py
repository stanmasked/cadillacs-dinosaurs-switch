#!/usr/bin/env python3
"""Stage 261 OPTIONAL host X11 complete post-command sample-series audit.

Re-check every compact 4-point RGB observation with its monotonic
XGetImage call bounds. All negative images must precede exactly one
NRO guest-frame-token-bound positive capture. No actual first-onset,
physical photons or cross-mode latency claim is possible.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_host_x11_transition as prior
    from tools import verify_nexium_host_frame_token as frames
    from tools import nexium_host_live_counter_pixel as pixel
else:
    import verify_nexium_host_x11_transition as prior
    import verify_nexium_host_frame_token as frames
    import nexium_host_live_counter_pixel as pixel

SCHEMA='dino-nexium-host-x11-sample-sequence-v1'
RAW_SUCCESS='HOST_X11_ORDERED_SAMPLES_OBSERVED_UNBOUND'
SUCCESS='HOST_X11_FULL_POST_COMMAND_SAMPLE_SERIES_GUEST_NRO_BOUND'
INCONCLUSIVE='INCONCLUSIVE_UNVERIFIED_X11_SAMPLE_SERIES'
FALSE_FLAGS=(
    'precise_first_visible_frame_onset_verified',
    'guest_input_delivery_timestamp_verified',
    'physical_controller_verified',
    'physical_display_verified',
    'gpu_scanout_timestamp_verified',
    'cross_mode_causal_latency_verified',
)
REQUIRED_FIELDS={
    'schema','status','ordered_host_x11_samples_observed',
    'post_command_negative_samples','matching_positive_frame_token_u16',
    'samples','clock_domain',*FALSE_FLAGS,
}
SAMPLE_FIELDS={
    'index','capture_begin_offset_us','capture_end_offset_us',
    'counter_four_pixels_present','four_counter_point_rgb','frame_token_u16',
}


def verify(guest_dir,nro,mode):
    guest=Path(guest_dir)
    previous=prior.verify(guest,nro,mode)
    raw=frames.load_json(guest/'host-x11-sample-sequence-evidence.json')
    if (set(raw)!=REQUIRED_FIELDS or raw['schema']!=SCHEMA or
        raw['status']!=RAW_SUCCESS or
        raw['ordered_host_x11_samples_observed'] is not True or
        raw['clock_domain']!='HOST_MONOTONIC_ONLY' or
        any(raw[k] is not False for k in FALSE_FLAGS)):
        raise ValueError('invalid host-only X11 sample-series envelope')
    series=raw['samples']
    count=raw['post_command_negative_samples']
    token=raw['matching_positive_frame_token_u16']
    if (type(series) is not list or type(count) is not int or
        not 1<=count<=198 or len(series)!=count+1 or len(series)>199 or
        type(token) is not int or token!=previous['guest_render_iteration']):
        raise ValueError('unproven negative count/guest frame identity')
    earlier_end=-1
    for n,entry in enumerate(series,1):
        if type(entry) is not dict or set(entry)!=SAMPLE_FIELDS:
            raise ValueError('wrong sample schema')
        start=entry['capture_begin_offset_us']
        end=entry['capture_end_offset_us']
        present=entry['counter_four_pixels_present']
        colors=entry['four_counter_point_rgb']
        if (type(entry['index']) is not int or entry['index']!=n or
            type(start) is not int or type(end) is not int or
            not 0<=start<=end<=2_500_001 or
            (n>1 and start<earlier_end) or
            type(present) is not bool or type(colors) is not dict or
            set(colors)!=set(pixel.POINTS)):
            raise ValueError('out-of-order, duplicated or invalid XGetImage record')
        for k,v in colors.items():
            if type(v) is not list or len(v)!=3 or any(
                    type(c) is not int or not 0<=c<=255 for c in v):
                raise ValueError('bad actual sampled X11 four-point RGB')
        actual=all(tuple(colors[k])==rgb for k,rgb in pixel.EXPECTED.items())
        if actual!=present or present!=(n==len(series)):
            raise ValueError('missing/forged X11 negative→positive sample order')
        if n==len(series):
            if (type(entry['frame_token_u16']) is not int or
                entry['frame_token_u16']!=token):
                raise ValueError('positive X11 token mismatched genuine guest frame')
        elif entry['frame_token_u16'] is not None:
            raise ValueError('negative sampled image claiming guest counter frame ID')
        earlier_end=end
    negative=series[-2]
    positive=series[-1]
    if (negative['four_counter_point_rgb'] != {
            k:list(v) for k,v in
            frames.load_json(guest/'host-x11-transition-bracket-evidence.json')[
                'last_negative_x11_pixel_rgb'].items()} or
        negative['capture_begin_offset_us'] !=
            previous['last_negative_xgetimage_begin_offset_us'] or
        negative['capture_end_offset_us'] !=
            previous['last_negative_xgetimage_end_offset_us'] or
        positive['capture_begin_offset_us'] !=
            previous['first_positive_xgetimage_begin_offset_us'] or
        positive['capture_end_offset_us'] !=
            previous['first_positive_xgetimage_end_offset_us']):
        raise ValueError('sample series contradicts independent Stage 260 X11 proof')
    return {
        'schema':'dino-nexium-host-x11-full-sample-series-bound-v1',
        'status':SUCCESS,'mode':mode,
        'all_sampled_x11_states_ordered_and_bound':True,
        'negative_x11_samples':count,
        'positive_x11_samples':1,
        'total_post_command_samples':len(series),
        'last_absent_capture_begin_offset_us':
            negative['capture_begin_offset_us'],
        'last_absent_capture_end_offset_us':
            negative['capture_end_offset_us'],
        'first_present_capture_begin_offset_us':
            positive['capture_begin_offset_us'],
        'first_present_capture_end_offset_us':
            positive['capture_end_offset_us'],
        'guest_submitted_render_iteration':token,
        'whole_nro_sha256':previous['whole_nro_sha256'],
        'clock_domain':'HOST_MONOTONIC_ONLY',
        'exact_first_visible_frame_onset_verified':False,
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
    except (OSError,ValueError,UnicodeError,TypeError,KeyError,OverflowError):
        proof={
            'schema':'dino-nexium-host-x11-full-sample-series-bound-v1',
            'status':INCONCLUSIVE,
            'all_sampled_x11_states_ordered_and_bound':False,
            'clock_domain':'HOST_MONOTONIC_ONLY',
            'exact_first_visible_frame_onset_verified':False,
            'guest_input_delivery_timestamp_verified':False,
            'physical_controller_verified':False,
            'physical_display_verified':False,
            'gpu_scanout_timestamp_verified':False,
            'cross_mode_causal_comparison_verified':False,
        }
    with a.out.open('x',encoding='ascii') as output:
        output.write(json.dumps(proof,sort_keys=True)+'\n')
    print(json.dumps(proof,sort_keys=True))
    return 0  # Diagnostic only: INCONCLUSIVE is not authenticated success.


if __name__=='__main__':
    raise SystemExit(main())
