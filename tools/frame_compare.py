#!/usr/bin/env python3
"""Local-only pixel-exact comparison of 8-bit RGBA PNG reference frames.

Accepts PNG filters 0..4, noninterlaced RGBA. Outputs JSON metrics and an
optional absolute-error heatmap. No third-party packages or ROMs required.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import zlib

SIGNATURE = b'\x89PNG\r\n\x1a\n'


def _paeth(a, b, c):
    p = a+b-c
    pa,pb,pc = abs(p-a),abs(p-b),abs(p-c)
    if pa <= pb and pa <= pc: return a
    if pb <= pc: return b
    return c


def load_rgba_png(data):
    if not data.startswith(SIGNATURE):
        raise ValueError('Not a PNG')
    pos = len(SIGNATURE)
    ihdr = None
    compressed = []
    seen_end = False
    seen_plte = False
    seen_idat = False
    ended_idat = False
    while pos + 12 <= len(data):
        size = struct.unpack_from('>I',data,pos)[0]
        if size > len(data)-pos-12:
            raise ValueError('Truncated PNG chunk')
        kind = data[pos+4:pos+8]
        payload = data[pos+8:pos+8+size]
        checksum = struct.unpack_from('>I',data,pos+8+size)[0]
        if zlib.crc32(kind+payload) & 0xffffffff != checksum:
            raise ValueError('PNG chunk CRC mismatch')
        pos += size+12
        # PNG chunk types are ASCII letters with uppercase reserved bit.
        if (any(not (65 <= c <= 90 or 97 <= c <= 122) for c in kind)
                or not 65 <= kind[2] <= 90):
            raise ValueError('Invalid PNG chunk type')
        if ihdr is None and kind != b'IHDR':
            raise ValueError('IHDR must be first PNG chunk')
        if seen_idat and kind != b'IDAT':
            ended_idat = True
        if kind == b'IHDR':
            if ihdr is not None or size != 13:
                raise ValueError('Malformed or duplicate IHDR')
            ihdr = struct.unpack('>IIBBBBB',payload)
        elif kind == b'PLTE':
            if seen_plte or seen_idat or not 0 < size <= 768 or size % 3:
                raise ValueError('Invalid or misplaced PLTE')
            seen_plte = True
        elif kind == b'IDAT':
            # IDATs may be split, but must occupy consecutive chunks.
            if ended_idat:
                raise ValueError('Noncontiguous PNG IDAT chunks')
            compressed.append(payload)
            seen_idat = True
        elif kind == b'IEND':
            if size:
                raise ValueError('Nonempty PNG IEND')
            seen_end = True
            break
        elif not (kind[0] & 0x20):
            # Never ignore an unknown critical chunk that could change pixels.
            raise ValueError('Unsupported critical PNG chunk')
    if ihdr is None or not compressed or not seen_end:
        raise ValueError('Incomplete PNG')
    if pos != len(data):
        raise ValueError('Trailing data after PNG IEND')
    width,height,depth,mode,compression,filtering,interlace = ihdr
    if not 0 < width <= 8192 or not 0 < height <= 8192:
        raise ValueError('Invalid PNG dimensions')
    if (depth,mode,compression,filtering,interlace) != (8,6,0,0,0):
        raise ValueError('Only 8-bit noninterlaced RGBA PNG supported')
    stride = width*4
    expected = height*(stride+1)
    try:
        decompressor = zlib.decompressobj()
        raw = decompressor.decompress(b''.join(compressed),expected+1)
        if len(raw) != expected or not decompressor.eof or decompressor.unused_data:
            raise ValueError('Incorrect PNG pixel stream length')
    except zlib.error as exc:
        raise ValueError('Invalid PNG compression') from exc
    rgba=bytearray(height*stride)
    prev=bytearray(stride)
    for row in range(height):
        start = row*(stride+1)
        kind=raw[start]
        if kind > 4: raise ValueError('Unsupported PNG filter')
        pixels=bytearray(raw[start+1:start+1+stride])
        for i in range(stride):
            a=pixels[i-4] if i>=4 else 0
            b=prev[i]
            c=prev[i-4] if i>=4 else 0
            if kind==1: pixels[i]=(pixels[i]+a)&255
            elif kind==2: pixels[i]=(pixels[i]+b)&255
            elif kind==3: pixels[i]=(pixels[i]+(a+b)//2)&255
            elif kind==4: pixels[i]=(pixels[i]+_paeth(a,b,c))&255
        rgba[row*stride:(row+1)*stride]=pixels
        prev=pixels
    return width,height,bytes(rgba)


def compare_frames(reference,candidate,width,height,*,ignore_alpha=False):
    if len(reference)!=width*height*4 or len(candidate)!=len(reference):
        raise ValueError('RGBA buffer dimensions do not match')
    total=width*height
    count=0
    absolute=0
    peak=0
    first=None
    nch=3 if ignore_alpha else 4
    diff=bytearray(total*4)
    for i in range(total):
        index=i*4
        errors=[abs(reference[index+c]-candidate[index+c]) for c in range(nch)]
        err=max(errors)
        if err:
            count+=1
            if first is None: first=[i%width,i//width]
        absolute+=sum(errors)
        peak=max(peak,err)
        diff[index:index+4]=bytes((err,0,0,255))
    return {
        'width':width,'height':height,
        'compared_channels':'RGB' if ignore_alpha else 'RGBA',
        'pixels':total,'different_pixels':count,'different_ratio':count/total,
        'mean_absolute_channel_error':absolute/(total*nch),
        'max_channel_error':peak,'first_difference_xy':first,
        'identical':count==0
    },bytes(diff)



def diagnose_translation(reference, candidate, width, height, max_shift=2, *, ignore_alpha=False):
    """Find a diagnostic XY registration offset on actual overlapping pixels.

    An offset (dx,dy) compares reference(x,y) to candidate(x+dx,y+dy).
    Off-screen areas are excluded, never wrapped or padded. This does not
    modify the strict full-frame result or its process exit status.
    """
    if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
        raise ValueError('Frame dimensions must be positive integers')
    if type(max_shift) is not int or not 1 <= max_shift <= 4:
        raise ValueError('max_shift must be in 1..4')
    if width * height > 512 * 256:
        raise ValueError('Translation diagnostic is limited to 512x256 CPS-1 pixels')
    if len(reference) != width * height * 4 or len(candidate) != width * height * 4:
        raise ValueError('RGBA buffer dimensions do not match')
    nch = 3 if ignore_alpha else 4
    best = None
    best_score = None
    xlimit = min(max_shift, width - 1)
    ylimit = min(max_shift, height - 1)
    for dy in range(-ylimit, ylimit + 1):
        for dx in range(-xlimit, xlimit + 1):
            overlap_w = width - abs(dx)
            overlap_h = height - abs(dy)
            total = overlap_w * overlap_h
            rx = max(0, -dx)
            ry = max(0, -dy)
            mismatches = 0
            absolute = 0
            for y in range(ry, ry + overlap_h):
                ref_offset = (y * width + rx) * 4
                cand_offset = ((y + dy) * width + rx + dx) * 4
                for _ in range(overlap_w):
                    differs = False
                    for channel in range(nch):
                        error = abs(reference[ref_offset + channel] -
                                    candidate[cand_offset + channel])
                        absolute += error
                        if error:
                            differs = True
                    if differs:
                        mismatches += 1
                    ref_offset += 4
                    cand_offset += 4
            # Compare relative mismatch rather than unnormalized pixel counts,
            # but publish overlap so an edge crop cannot masquerade as parity.
            score = (mismatches / total, absolute / (total * nch),
                     abs(dx) + abs(dy), abs(dy), abs(dx), dy, dx)
            if best_score is None or score < best_score:
                best_score = score
                best = {'dx': dx, 'dy': dy,
                        'overlap_pixels': total,
                        'overlap_fraction': total / (width * height),
                        'different_pixels': mismatches,
                        'different_ratio': mismatches / total,
                        'mean_absolute_channel_error': absolute / (total * nch)}
    return {'max_shift': max_shift,
            'compared_channels': 'RGB' if ignore_alpha else 'RGBA',
            'best_translation': best,
            'diagnostic_only': True}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('reference_png',type=Path)
    p.add_argument('candidate_png',type=Path)
    p.add_argument('--diff',type=Path,help='Optional red absolute-error heatmap')
    p.add_argument('--ignore-alpha',action='store_true')
    p.add_argument('--max-different-pixels',type=int,default=0)
    p.add_argument('--diagnose-shift',type=int,default=0,
                   help='Optional XY offset diagnosis up to 4 pixels; strict pass/fail is unchanged')
    args=p.parse_args(argv)
    if args.max_different_pixels<0:
        p.error('--max-different-pixels must be nonnegative')
    if not 0 <= args.diagnose_shift <= 4:
        p.error('--diagnose-shift must be in 0..4')
    try:
        width,height,ref=load_rgba_png(args.reference_png.read_bytes())
        w2,h2,cur=load_rgba_png(args.candidate_png.read_bytes())
        if (width,height)!=(w2,h2):
            raise ValueError(f'Image sizes differ: {(width,height)} vs {(w2,h2)}')
        result,diff=compare_frames(ref,cur,width,height,ignore_alpha=args.ignore_alpha)
        if args.diagnose_shift:
            result['translation_diagnostic'] = diagnose_translation(
                ref,cur,width,height,args.diagnose_shift,
                ignore_alpha=args.ignore_alpha)
        print(json.dumps(result,indent=2))
        if args.diff:
            try: from tools.cps1_tiles import _png_rgba
            except ModuleNotFoundError: from cps1_tiles import _png_rgba
            args.diff.parent.mkdir(parents=True,exist_ok=True)
            args.diff.write_bytes(_png_rgba(width,height,diff,'Absolute RGB/RGBA error'))
        return int(result['different_pixels']>args.max_different_pixels)
    except (OSError,ValueError,TypeError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
