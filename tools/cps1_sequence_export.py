#!/usr/bin/env python3
"""Pack a bounded local CPS1SEQ1 timeline from effective-palette RAM captures.

All inputs/outputs remain on the user's computer. This tool includes no ROMs.
For a synthetic demo, use --demo: it models test scroll values and sprites,
not actual game frames, timings or artwork.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import zlib

try:
    from tools.cps1_scene_export import pack_scene, FILE_BYTES as SCENE_BYTES
except ModuleNotFoundError:
    from cps1_scene_export import pack_scene, FILE_BYTES as SCENE_BYTES

MAGIC=b'CPS1SEQ1'
HEADER_BYTES=20
MAX_FRAMES=120

def pack_sequence(frame_blobs, fps):
    if type(fps) is not int or not 1<=fps<=60:
        raise ValueError('fps must be an integer 1..60')
    if not isinstance(frame_blobs,(list,tuple)) or not 1<=len(frame_blobs)<=MAX_FRAMES:
        raise ValueError('1..120 frames required')
    for i,blob in enumerate(frame_blobs):
        if len(blob)!=SCENE_BYTES or blob[:8]!=b'CPS1SCN1':
            raise ValueError(f'Frame {i} is not a CPS1SCN1 blob')
        if struct.unpack_from('<I',blob,8)[0]!=SCENE_BYTES-16 or (
           zlib.crc32(blob[16:]) != struct.unpack_from('<I',blob,12)[0]):
            raise ValueError(f'Frame {i} failed CRC or length')
        if blob[35]!=0:
            raise ValueError(f'Frame {i} has nonzero reserved byte')
    payload=b''.join(frame_blobs)
    header=MAGIC+struct.pack('<HHII',len(frame_blobs),fps,zlib.crc32(payload),0)
    return header+payload

def demo_snapshots(count=24):
    """Build only **synthetic** test RAM/palette data; no ROM contents."""
    if not 1<=count<=MAX_FRAMES:
        raise ValueError('Invalid demo frame count')
    pal=[[0,0,0] for _ in range(3072)]
    pal[0xbff]=[12,17,27]
    for page in range(6):
        for color in range(32):
            for pen in range(16):
                p=page*512+color*16+pen
                if pen==15:continue
                pal[p]=[(30+pen*11+page*9)%256,
                        (35+pen*9+color*4)%256,
                        (20+pen*7+page*20)%256]
    frames=[]
    # Only synthetic register and OBJ positions move. The final visible
    # graphics depend on the user's own local ROM region.
    for i in range(count):
        scene={
          'layer_control':(3<<6)|(2<<8)|(1<<10)|(0<<12),
          'video_control':0x0e,
          'palette_rgb':pal,
          'priority_masks':[0,0,0,0],
          'scroll1':{'words':[0]*8192,'enabled':True,
                     'scrollx':i*2, 'scrolly':0},
          'scroll2':{'words':[0]*8192,'enabled':True,
                     'scrollx':i, 'scrolly':0},
          'scroll3':{'words':[0]*8192,'enabled':True,
                     'scrollx':i//2, 'scrolly':0},
          'buffered_obj_words':[64+i*3,100,0x100,0,
                                0,0,0,0xff00],
        }
        frames.append(scene)
    return frames

def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--frames-dir',type=Path,
                      help='Folder with numbered JSON CPS-1 frame captures')
    mode.add_argument('--demo',action='store_true',
                      help='Make synthetic 24-frame motion fixture, not original gameplay')
    ap.add_argument('--fps',type=int,default=12,help='Frames per second, 1..60')
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args(argv)
    try:
        if args.demo:
            frames=demo_snapshots()
        else:
            paths=sorted(args.frames_dir.glob('*.json'))
            if not 1<=len(paths)<=MAX_FRAMES:
                raise ValueError('Expected 1..120 JSON frames in directory')
            frames=[json.loads(p.read_text(encoding='utf-8')) for p in paths]
        packed=[pack_scene(frame) for frame in frames]
        payload=pack_sequence(packed,args.fps)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        with args.out.open('xb') as file:
            file.write(payload)
        print(f'Wrote local timeline: {args.out}; {len(frames)} frames, '
              f'{args.fps} fps, {len(payload)} bytes')
        return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print('Error:',exc,file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
