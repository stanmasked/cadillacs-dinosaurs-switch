#!/usr/bin/env python3
"""ROM-free WolfMAME 0.106 bootstrap/PNG receipt verification.

Neither a PNG filename nor its CRC proves playback, scene or frame timing.
Original game files/captures must remain private.
"""
import argparse
import hashlib
import json
import re
import struct
import zlib
from pathlib import Path

PLAN_SCHEMA='dino-wolfmame0106-private-reference-capture-plan-v1'
REQUEST_SCHEMA='dino-wolfmame0106-replay-bootstrap-request-v1'
RECEIPT_SCHEMA='dino-wolfmame0106-private-png-receipt-v1'
BASE_FRAMES=(0,1,2,30,60,90,119,120,180,300,600,900,1800,3600)
PNG_SIG=b'\x89PNG\r\n\x1a\n'

def distinct_pairs(pairs):
    obj={}
    for k,v in pairs:
        if k in obj:raise ValueError('duplicate JSON key')
        obj[k]=v
    return obj

def ordinary_file(path,max_bytes):
    path=Path(path)
    if path.is_symlink() or not path.is_file():raise ValueError('not an ordinary file')
    if not 1<=path.stat().st_size<=max_bytes:raise ValueError('file size outside bounds')
    return path.read_bytes()

def read_json(path,max_bytes):
    raw=ordinary_file(path,max_bytes)
    try:return json.loads(raw.decode('utf-8'),object_pairs_hook=distinct_pairs)
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError('invalid JSON') from exc

def validate_plan(plan):
    if (type(plan) is not dict or plan.get('schema')!=PLAN_SCHEMA or
        plan.get('status')!='PRIVATE_PLAYBACK_CAPTURE_REQUEST_NOT_EXECUTED'):
        raise ValueError('incorrect Stage271 plan')
    n=plan.get('total_original_recorded_frames')
    if type(n) is not int or not 3601<=n<=10000000:raise ValueError('bad recording length')
    if (plan.get('actual_emulator_frames_captured') is not False or
        plan.get('input_binding_and_exact_video_frame_alignment_verified') is not False or
        plan.get('public_GitHub_raw_capture_export_permitted') is not False):
        raise ValueError('invalid authenticity flags')
    over=plan.get('overview',{}).get('requested_frames')
    detail=plan.get('animation_detail',{}).get('requested_frames')
    if (not isinstance(over,list) or not isinstance(detail,list) or
        len(over)!=plan.get('overview_frame_count') or
        len(detail)!=plan.get('detail_frame_count') or
        any(type(x) is not int or not 0<=x<n for x in over+detail) or
        len(set(over))!=len(over) or len(set(detail))!=len(detail)):
        raise ValueError('malformed capture plan')
    return n

def make_request(plan,anchor=None):
    n=validate_plan(plan)
    if anchor is not None and (type(anchor) is not int or not 0<=anchor<n):
        raise ValueError('invalid optional Start anchor')
    frames=set(x for x in BASE_FRAMES if x<n)
    if anchor is not None:
        frames.update(x for x in
            (anchor-3,anchor-2,anchor-1,anchor,anchor+1,anchor+2,
             anchor+3,anchor+8,anchor+16) if 0<=x<n)
    selected=sorted(frames)
    return {
        'schema':REQUEST_SCHEMA,'status':'CAPTURE_REQUEST_NOT_CAPTURED',
        'game':'dino','recorded_input_frames':n,
        'input_start_anchor_unverified':anchor,
        'estimated_frame_rate_only':60,
        'image_names':[f'frame-{f:08d}.png' for f in selected],
        'frame_indices':selected,'expected_capture_count':len(selected),
        'requires_private_matching_WolfMAME_0_106':True,
        'emulator_provenance_verified':False,
        'input_to_image_sync_verified':False,
        'physical_switch_verified':False,
    }

MAX_DECODED_PNG_BYTES=64*1024*1024
PNG_CHANNELS={0:1,2:3,3:1,4:2,6:4}

def png_integrity(raw):
    """Inspect complete PNG scanlines, including packed 1/2/4-bit palettes.

    These checks authenticate well-formed image *bytes*, not what game,
    emulator, time or input event the pixels depict.
    """
    if raw[:8]!=PNG_SIG:raise ValueError('invalid PNG signature')
    pos=8
    ihdr=None
    idat=[]
    seen_palette=False
    palette_entries=0
    idat_started=False
    idat_finished=False
    iend=False
    for _ in range(100000):
        if pos+12>len(raw):raise ValueError('truncated PNG chunk')
        length=struct.unpack('>I',raw[pos:pos+4])[0]
        name=raw[pos+4:pos+8]
        if (length>8*1024*1024 or pos+length+12>len(raw) or
            len(name)!=4 or any(not(65<=v<=90 or 97<=v<=122) for v in name)):
            raise ValueError('bad PNG chunk length/type')
        data=raw[pos+8:pos+8+length]
        crc=struct.unpack('>I',raw[pos+8+length:pos+12+length])[0]
        if zlib.crc32(name+data)&0xffffffff!=crc:
            raise ValueError('bad PNG chunk CRC')
        pos+=12+length
        if ihdr is None and name!=b'IHDR':
            raise ValueError('PNG must begin with IHDR')
        if name==b'IHDR':
            if ihdr is not None or length!=13:raise ValueError('repeated/invalid IHDR')
            w,h,depth,colour,comp,filt,interlace=struct.unpack('>IIBBBBB',data)
            if not(1<=w<=4096 and 1<=h<=4096 and w*h<=16000000 and
                   ((colour==3 and depth in (1,2,4,8)) or
                    (colour!=3 and depth==8 and colour in PNG_CHANNELS)) and
                   comp==0 and filt==0 and interlace==0):
                raise ValueError('unsupported PNG dimensions/mode')
            ihdr=(w,h,colour,depth)
        elif name==b'PLTE':
            if seen_palette or idat_started or not length or length%3 or length>768:
                raise ValueError('invalid PNG palette')
            if ihdr is None: raise ValueError('palette before IHDR')
            if ihdr[2]==3 and length//3 > (1 << ihdr[3]):
                raise ValueError('PNG palette exceeds indexed bit depth')
            seen_palette=True
            palette_entries=length//3
        elif name==b'IDAT':
            if idat_finished:raise ValueError('noncontiguous PNG IDAT')
            idat_started=True
            idat.append(data)
        elif name==b'IEND':
            if length or pos!=len(raw) or not idat_started:
                raise ValueError('bad PNG end')
            iend=True
            break
        elif name[0]&32==0:
            raise ValueError('unsupported critical PNG chunk')
        if idat_started and name!=b'IDAT':
            idat_finished=True
    if not iend or not idat or ihdr is None:
        raise ValueError('incomplete PNG')
    w,h,colour,depth=ihdr
    if colour==3 and not seen_palette:
        raise ValueError('indexed PNG has no palette')
    row_stride=1+((w*depth+7)//8 if colour==3 else w*PNG_CHANNELS[colour])
    expected=row_stride*h
    if expected>MAX_DECODED_PNG_BYTES:
        raise ValueError('image scanlines too large')
    stream=zlib.decompressobj()
    decoded=bytearray()
    try:
        for chunk in idat:
            remaining=expected+1-len(decoded)
            if remaining<=0:raise ValueError('PNG inflated beyond dimensions')
            decoded.extend(stream.decompress(chunk,remaining))
            if stream.unconsumed_tail or stream.unused_data:
                raise ValueError('PNG inflated beyond dimensions/trailing zlib stream')
        if not stream.eof:raise ValueError('incomplete PNG deflate stream')
        decoded.extend(stream.flush())
    except zlib.error as exc:
        raise ValueError('corrupted PNG IDAT') from exc
    if len(decoded)!=expected:
        raise ValueError('PNG scanline data length does not match IHDR')
    if any(decoded[y*row_stride]>4 for y in range(h)):
        raise ValueError('invalid PNG scanline filter')
    return {'width':w,'height':h,'png_color_type':colour,
            'png_bit_depth':depth,
            'palette_entries':palette_entries,
            'idat_decoded_bytes':len(decoded),
            'scanline_size_and_filters_verified':True}

def audit_captures(request,folder,expected_width=None,expected_height=None):
    if (request.get('schema')!=REQUEST_SCHEMA or
        request.get('status')!='CAPTURE_REQUEST_NOT_CAPTURED'):
        raise ValueError('unsupported request')
    expected=request.get('image_names')
    if (not isinstance(expected,list) or
        len(expected)!=request.get('expected_capture_count') or
        len(set(expected))!=len(expected) or
        any(not re.fullmatch(r'frame-\d{8}\.png',str(x)) for x in expected)):
        raise ValueError('malformed filename list')
    folder=Path(folder)
    if folder.is_symlink() or not folder.is_dir():raise ValueError('invalid capture directory')
    if {x.name for x in folder.iterdir()}!=set(expected):
        raise ValueError('missing/unexpected screenshot files')
    entries=[]
    for name in expected:
        raw=ordinary_file(folder/name,40*1024*1024)
        png=png_integrity(raw)
        if ((expected_width is not None and png['width']!=expected_width) or
            (expected_height is not None and png['height']!=expected_height)):
            raise ValueError('unexpected screenshot resolution')
        entries.append({'name':name,'sha256':hashlib.sha256(raw).hexdigest(),**png})
    return {
        'schema':RECEIPT_SCHEMA,
        'status':'PNG_FILE_BYTES_ONLY_NOT_AUTHENTICATED_EMULATION',
        'frames_received':len(entries),'png_integrity_passed':True,
        'image_files':entries,'game_content_verified':False,
        'capture_counter_sync_verified':False,
        'pixel_parity_verified':False,
        'safe_to_publish_actual_game_frames':False,
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--start-anchor',type=int)
    p.add_argument('--captures',type=Path)
    p.add_argument('--width',type=int)
    p.add_argument('--height',type=int)
    a=p.parse_args(argv)
    req=make_request(read_json(a.plan,200000),a.start_anchor)
    result=(audit_captures(req,a.captures,a.width,a.height)
            if a.captures else req)
    with a.out.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2)
        f.write('\n')
    print(result['status'])

if __name__=='__main__':
    main()
