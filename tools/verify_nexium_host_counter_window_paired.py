#!/usr/bin/env python3
"""Stage 251: mandatory paired real NeXium host X11 counter pixels.

An X11 host-window four-pixel witness is NOT hardware Switch display,
physical Joy-Con latency, speaker playback, or exact guest frame identity.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

STATUS='HOST_WINDOW_COUNTER_PIXELS_OBSERVED_UNBOUND'
HOST_KEYS={
 'schema','status','host_x11_window_counter_pixels_observed',
 'counter_transition_baseline_observed','same_x11_image_four_pixel_match',
 'frames_sampled','diagnostic_code','native_guest_counter_event_bound',
 'host_window_pixel_latency_verified','physical_display_verified',
 'physical_controller_verified','original_arcade_graphics_verified',
}
PIXELS={'caption_rgba':'FFC9EB5B','impact_rgba':'FFA4F3FF',
        'player_rgba':'FFD0B43E','background_rgba':'FF4A533E'}
PIXEL_COLUMNS=('event','render_iteration','arena_tick','feedback_ttl',
               'impact_ttl',*PIXELS)
LIVE_COLUMNS=('event','tick','player_x','enemy_x','pre_windup',
              'player_hp','enemy_hp','post_windup','stun','cooldown',
              'event_mask','hid_edge','pcm_nonzero','pcm_fnv64')


def pairs_unique(pairs):
    obj={}
    for k,v in pairs:
        if k in obj:
            raise ValueError('duplicate JSON evidence key')
        obj[k]=v
    return obj


def file(path,minimum=1,maximum=4096):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or not minimum<=path.stat().st_size<=maximum:
        raise ValueError('missing/oversized/linked evidence: '+path.name)
    return path


def jread(path):
    try:
        return json.loads(file(path).read_text(encoding='ascii'),
                          object_pairs_hook=pairs_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError('invalid real witness JSON') from exc


def csvread(path,fields):
    try:
        with file(path,75,640).open(encoding='ascii',newline='') as handle:
            r=csv.DictReader(handle)
            if tuple(r.fieldnames or ())!=tuple(fields):
                raise ValueError('guest CSV schema mismatch')
            rows=list(r)
    except (UnicodeError,csv.Error) as exc:
        raise ValueError('invalid guest CSV') from exc
    if len(rows)!=1 or None in rows[0] or any(v is None for v in rows[0].values()):
        raise ValueError('one strict guest CSV event required')
    return rows[0]


def check_host(report):
    if not isinstance(report,dict) or set(report)!=HOST_KEYS:
        raise ValueError('host X11 evidence keys mismatch')
    if (report['schema']!='dino-nexium-host-counter-frame-v1' or
        report['status']!=STATUS or report['diagnostic_code']!=''):
        raise ValueError('no confirmed real host X11 counter')
    for key in ('host_x11_window_counter_pixels_observed',
                'counter_transition_baseline_observed',
                'same_x11_image_four_pixel_match'):
        if report[key] is not True:
            raise ValueError('host X11 baseline/four-color witness missing')
    for key in ('native_guest_counter_event_bound',
                'host_window_pixel_latency_verified','physical_display_verified',
                'physical_controller_verified','original_arcade_graphics_verified'):
        if report[key] is not False:
            raise ValueError('unsupported physical/causal host claim')
    n=report['frames_sampled']
    if type(n) is not int or not 2<=n<=200:
        raise ValueError('host X11 sample count invalid')
    return n


def metadata(path):
    props={}
    for row in file(path,50,4096).read_text(encoding='ascii').splitlines():
        if '=' not in row:
            continue
        key,value=row.split('=',1)
        if key in props and key in ('scope','nro_sha256'):
            raise ValueError('duplicate critical metadata')
        if key not in props:
            props[key]=value
    return props


def check_mode(mode,guest,nro):
    guest=Path(guest)
    if guest.is_symlink() or not guest.is_dir():
        raise ValueError('guest evidence directory missing')
    samples=check_host(jread(guest/'host-counter-window-evidence.json'))
    attempt=jread(guest/'host-live-zr-attempt.json')
    if attempt!={'schema':'dino-nexium-host-live-counter-attempt-v1',
                 'status':'HOST_LIVE_SCENE_ZR_ATTEMPT_AFTER_REAL_Y_X',
                 'guest_live_counter_verified':False}:
        raise ValueError('host Y/X/T sequence not attempted')
    live=csvread(guest/'guest-live-counter-hid.csv',LIVE_COLUMNS)
    if (live['event']!='LIVE_HID_COUNTER' or live['player_x']!='90' or
        live['enemy_x']!='134' or live['hid_edge']!='1' or
        live['pcm_nonzero']!='1'):
        raise ValueError('real libnx counter guest edge absent')
    tick=int(live['tick'])
    if not 117<=tick<=128 or int(live['pre_windup'])!=129-tick:
        raise ValueError('natural pursuit tick invalid')
    frame=csvread(guest/'guest-live-counter-framebuffer.csv',PIXEL_COLUMNS)
    if frame['event']!='SUBMITTED_COUNTER_FRAME' or any(
        frame[k]!=v for k,v in PIXELS.items()):
        raise ValueError('real native guest framebuffer four pixels missing')
    if (int(frame['arena_tick'])<tick or
        not 1<=int(frame['feedback_ttl'])<=6 or
        not 1<=int(frame['impact_ttl'])<=6):
        raise ValueError('invalid counter-frame visual TTL')
    saved=jread(guest/'guest-live-counter-framebuffer-evidence.json')
    if (saved.get('status')!='GUEST_SUBMITTED_COUNTER_FRAMEBUFFER_PIXELS_WITNESSED' or
        saved.get('native_guest_framebuffer_pixels_verified') is not True or
        saved.get('host_emulator_screen_pixel_verified') is not False):
        raise ValueError('native submitted-frame witness mismatch')
    for col,key in [('render_iteration','render_iteration'),('arena_tick','arena_tick'),
                    ('feedback_ttl','counter_caption_feedback_ttl'),
                    ('impact_ttl','enemy_impact_flash_ttl')]:
        if int(frame[col])!=saved.get(key):
            raise ValueError('native frame JSON/CSV conflict')
    data=file(nro,100000,2000000).read_bytes()
    if data[16:20]!=b'NRO0':
        raise ValueError('not a genuine NRO binary')
    sha=hashlib.sha256(data).hexdigest()
    props=metadata(guest/'metadata.txt')
    if (props.get('nro_sha256')!=sha or
        props.get('scope')!='REAL_NE_XIUM_GUEST_CI_NO_NINTENDO_ROM'):
        raise ValueError('guest evidence does not bind to exact NRO')
    if 'PASS: actual NeXium NRO guest' not in file(
        guest/'result.txt',1,1024).read_text(encoding='ascii'):
        raise ValueError('real guest did not pass')
    return {'mode':mode,'host_x11_window_counter_pixels_verified':True,
            'x11_samples':samples,'counter_tick':tick,
            'native_counter_frame_tick':int(frame['arena_tick']),
            'native_framebuffer_verified':True,'nro_sha256':sha,
            'exact_host_x11_to_guest_frame_identity_verified':False,
            'physical_switch_display_verified':False}


def verify(baseline,extra,baseline_nro,extra_nro):
    first=check_mode('baseline',baseline,baseline_nro)
    second=check_mode('extra-poll',extra,extra_nro)
    if first['nro_sha256']==second['nro_sha256']:
        raise ValueError('independent guest NRO binaries required')
    return {'schema':'dino-nexium-paired-host-counter-window-v1',
            'status':'BOTH_REAL_NEXIUM_HOST_X11_COUNTER_WINDOWS_OBSERVED',
            'modes':{'baseline':first,'extra-poll':second},
            'both_nro_bound_host_x11_counter_pixels_verified':True,
            'physical_switch_display_verified':False,
            'physical_joycon_latency_verified':False,
            'speaker_audio_verified':False,
            'exact_guest_frame_to_host_sample_identity_verified':False,
            'original_arcade_graphics_verified':False}


def main():
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--baseline-dir',type=Path,required=True)
    a.add_argument('--extra-dir',type=Path,required=True)
    a.add_argument('--baseline-nro',type=Path,required=True)
    a.add_argument('--extra-nro',type=Path,required=True)
    a.add_argument('--out',type=Path,required=True)
    options=a.parse_args()
    result=verify(options.baseline_dir,options.extra_dir,
                  options.baseline_nro,options.extra_nro)
    options.out.write_text(json.dumps(result,sort_keys=True)+'\n',encoding='ascii')
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':
    main()
