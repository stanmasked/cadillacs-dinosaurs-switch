#!/usr/bin/env python3
"""Stage 253 OPTIONAL NeXium 16-bit host-frame token / native-guest match.

Only a confirmed token, read in the SAME X11 image as four counter pixels,
may match an independently submitted native guest render iteration.
No physical display, latency or real-world photon measurement is inferred.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

HOST_SCHEMA='dino-nexium-host-frame-token-v1'
STATUS='HOST_X11_FRAME_TOKEN_OBSERVED_UNBOUND'
CSV_FIELDS=('event','render_iteration','arena_tick','feedback_ttl',
            'impact_ttl','token_u16')
GUEST_FIELDS=('event','render_iteration','arena_tick','feedback_ttl',
              'impact_ttl','caption_rgba','impact_rgba',
              'player_rgba','background_rgba')
PIXELS=('FFC9EB5B','FFA4F3FF','FFD0B43E','FF4A533E')
SUCCESS='HOST_X11_TOKEN_MATCHES_REAL_GUEST_SUBMITTED_FRAME'
INCONCLUSIVE='INCONCLUSIVE_NO_SAME_FRAME_IDENTITY'


def unique_keys(pairs):
    value={}
    for key,entry in pairs:
        if key in value:
            raise ValueError('duplicate evidence key')
        value[key]=entry
    return value


def file_bytes(path,limit=10000):
    path=Path(path)
    if path.is_symlink() or not path.is_file() or not 1<=path.stat().st_size<=limit:
        raise ValueError('missing/oversized/linked evidence')
    return path.read_bytes()


def load_json(path):
    try:
        value=json.loads(file_bytes(path),object_pairs_hook=unique_keys,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             ValueError('nonfinite evidence')))
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError('invalid JSON evidence') from exc
    if not isinstance(value,dict):
        raise ValueError('invalid object evidence')
    return value


def rows(path,fields,max_rows):
    try:
        raw=file_bytes(path,8192).decode('ascii')
        reader=csv.DictReader(raw.splitlines())
        if tuple(reader.fieldnames or ())!=tuple(fields):
            raise ValueError('invalid CSV header')
        entries=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise ValueError('invalid CSV evidence') from exc
    if (not 1<=len(entries)<=max_rows or
        any(None in row or any(value is None for value in row.values())
            for row in entries)):
        raise ValueError('truncated/ragged/overflow guest CSV')
    return entries


def exact_number(value,low,high):
    if not isinstance(value,str) or not value.isascii() or not value.isdecimal():
        raise ValueError('noncanonical integer')
    if len(value)>1 and value.startswith('0'):
        raise ValueError('noncanonical leading zero')
    n=int(value)
    if not low<=n<=high:
        raise ValueError('out-of-range number')
    return n


def verify(host_path,window_path,trace_path,frame_path,metadata_path,nro_path):
    host=load_json(host_path)
    window=load_json(window_path)
    if (set(host)!={'schema','status','token_u16',
                   'token_same_x11_image_as_counter_pixels',
                   'guest_submitted_frame_identity_verified',
                   'exact_host_guest_frame_latency_verified',
                   'physical_display_verified'} or
        host['schema']!=HOST_SCHEMA or host['status']!=STATUS or
        host['token_same_x11_image_as_counter_pixels'] is not True or
        host['guest_submitted_frame_identity_verified'] is not False or
        host['exact_host_guest_frame_latency_verified'] is not False or
        host['physical_display_verified'] is not False or
        window.get('status')!='HOST_WINDOW_COUNTER_PIXELS_OBSERVED_UNBOUND' or
        window.get('host_x11_window_counter_pixels_observed') is not True or
        window.get('counter_transition_baseline_observed') is not True or
        window.get('same_x11_image_four_pixel_match') is not True):
        raise ValueError('no authentic same-X11-image counter token')
    token=host['token_u16']
    if type(token) is not int or not 0<=token<=65535:
        raise ValueError('noncanonical host token')
    trace=rows(trace_path,CSV_FIELDS,64)
    guest=rows(frame_path,GUEST_FIELDS,1)[0]
    if (guest['event']!='SUBMITTED_COUNTER_FRAME' or
        tuple(guest[key] for key in GUEST_FIELDS[5:])!=PIXELS):
        raise ValueError('counter framebuffer witness invalid')
    frame_id=exact_number(guest['render_iteration'],1,2**32-1)
    frame_tick=exact_number(guest['arena_tick'],1,2**32-1)
    frame_feedback=exact_number(guest['feedback_ttl'],1,6)
    frame_impact=exact_number(guest['impact_ttl'],1,6)
    prev_iteration=0
    prev_tick=0
    matching=[]
    first_frame_found=False
    for row in trace:
        if row['event']!='TOKEN_SUBMITTED':
            raise ValueError('not a genuine submitted token frame')
        iteration=exact_number(row['render_iteration'],1,2**32-1)
        tick=exact_number(row['arena_tick'],1,2**32-1)
        ttl=exact_number(row['feedback_ttl'],1,6)
        flash=exact_number(row['impact_ttl'],1,6)
        encoded=exact_number(row['token_u16'],0,65535)
        if (iteration<=prev_iteration or tick<prev_tick or
            iteration&65535!=encoded):
            raise ValueError('invalid native frame sequence/token')
        prev_iteration,prev_tick=iteration,tick
        if iteration==frame_id:
            # The guest framebuffer sample and native trace are recorded
            # at the SAME framebuffer submission. Bind ALL ephemeral
            # state values, not merely the matching 32-bit frame/tick.
            # This first submitted pixel frame need not be the LATER
            # token-matched host X11 image: software rendering can lag.
            if (tick!=frame_tick or ttl!=frame_feedback or
                    flash!=frame_impact):
                raise ValueError('native framebuffer CSV/trace state mismatch')
            first_frame_found=True
        if encoded==token:
            matching.append((iteration,tick,ttl,flash))
    if not first_frame_found:
        raise ValueError('pixel CSV frame missing from token trace')
    if len(matching)!=1:
        raise ValueError('host token missing or ambiguous in native frames')
    nro=file_bytes(nro_path,64*1024*1024)
    if len(nro)<128 or nro[16:20]!=b'NRO0':
        raise ValueError('invalid NRO binary')
    digest=hashlib.sha256(nro).hexdigest()
    metadata=file_bytes(metadata_path,8192).decode('ascii').splitlines()
    exact_hash=[line[11:] for line in metadata if line.startswith('nro_sha256=')]
    if len(exact_hash)!=1 or exact_hash[0]!=digest:
        raise ValueError('native token not bound to actual NRO')
    render_id,tick,ttl,flash=matching[0]
    return {
        'schema':'dino-nexium-host-guest-frame-token-v1',
        'status':SUCCESS,
        'host_x11_guest_submitted_frame_identity_verified':True,
        'host_frame_token_u16':token,
        'matched_native_render_iteration':render_id,
        'matched_native_arena_tick':tick,
        'matched_caption_ttl':ttl,
        'matched_impact_ttl':flash,
        'guest_trace_frame_count':len(trace),
        'nro_sha256':digest,
        'precise_input_to_display_latency_verified':False,
        'physical_switch_display_verified':False,
        'exact_display_scanout_timing_verified':False,
        'original_arcade_graphics_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('host-token','host-window','guest-trace','guest-framebuffer',
                'metadata','nro','out'):
        p.add_argument('--'+arg,required=True,type=Path)
    a=p.parse_args(argv)
    try:
        result=verify(a.host_token,a.host_window,a.guest_trace,
                      a.guest_framebuffer,a.metadata,a.nro)
    except (OSError,ValueError,UnicodeError,OverflowError,KeyError,TypeError) as exc:
        result={
            'schema':'dino-nexium-host-guest-frame-token-v1',
            'status':INCONCLUSIVE,
            'reason':type(exc).__name__,
            'host_x11_guest_submitted_frame_identity_verified':False,
            'precise_input_to_display_latency_verified':False,
            'physical_switch_display_verified':False,
            'exact_display_scanout_timing_verified':False,
            'original_arcade_graphics_verified':False,
        }
    a.out.write_text(json.dumps(result,sort_keys=True)+'\n',encoding='ascii')
    print(json.dumps(result,sort_keys=True))
    return 0  # Stage 253 is OPTIONAL; an inconclusive report is not success.


if __name__=='__main__':
    raise SystemExit(main())
