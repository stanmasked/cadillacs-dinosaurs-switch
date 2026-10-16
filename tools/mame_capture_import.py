#!/usr/bin/env python3
"""Import local MAME dino reference pixels/palette and partial RAM capture.

Never label incomplete VBlank-latched OBJ state as authentic. Converts the
native 384x224 MAME RGB24 framebuffer to a PNG with no resize or filtering.
"""
import argparse
import json
import re
from pathlib import Path
import struct
import sys
try:
    from tools.cps1_capture import convert_capture, base_byte, SCROLL_SIZE, OTHER_SIZE
    from tools.cps1_tiles import _png_rgba
except ModuleNotFoundError:
    from cps1_capture import convert_capture, base_byte, SCROLL_SIZE, OTHER_SIZE
    from cps1_tiles import _png_rgba

GFX_BYTES=0x30000
REF_W,REF_H=384,224
PALETTE_COLORS=3072

def unpack_be_words(data,expected_size,label):
    if len(data)!=expected_size:
        raise ValueError(f'{label}: expected {expected_size} bytes, got {len(data)}')
    return list(struct.unpack('>'+str(expected_size//2)+'H',data))

def decode_reference_rgb24(data):
    if len(data)!=REF_W*REF_H*3:
        raise ValueError('MAME RGB reference must be exactly 258048 bytes')
    rgba=bytearray(REF_W*REF_H*4)
    for i in range(REF_W*REF_H):
        rgba[i*4:i*4+3]=data[i*3:i*3+3]
        rgba[i*4+3]=255
    return _png_rgba(REF_W,REF_H,rgba,'MAME native CPS-1 RGB reference frame')

def import_capture(directory,frame_stem):
    if not isinstance(frame_stem, str) or not re.fullmatch(r'frame-[0-9]{8}', frame_stem):
        raise ValueError('frame_stem must match frame-XXXXXXXX (eight digits)')
    directory=Path(directory)
    stem=directory/frame_stem
    manifest=json.loads((directory/(frame_stem+'.manifest.json')).read_text())
    if (manifest.get('game')!='dino' or
        manifest.get('palette_source')!='MAME_effective_pen_color' or
        manifest.get('obj_latch')!='NOT_CAPTURED' or
        manifest.get('pixel_parity_eligible') is not False or
        manifest.get('raw_word_endianness')!='big' or
        manifest.get('reference_width')!=REF_W or
        manifest.get('reference_height')!=REF_H or
        manifest.get('reference_pixel_encoding')!='rgb32_resolved' or
        manifest.get('reference_source_format') not in ('indexed_bitmap','rgb_bitmap')):
        raise ValueError('Unsupported or misleading MAME capture provenance')
    gfx=unpack_be_words(Path(str(stem)+'.gfxram-be.bin').read_bytes(),
                        GFX_BYTES,'CPS-1 QSound gfx RAM')
    a=unpack_be_words(Path(str(stem)+'.cps-a-be.bin').read_bytes(),64,'CPS-A')
    b=unpack_be_words(Path(str(stem)+'.cps-b-be.bin').read_bytes(),64,'CPS-B')
    pal=Path(str(stem)+'.palette-rgb24.bin').read_bytes()
    if len(pal)!=PALETTE_COLORS*3:
        raise ValueError('Effective palette must contain exactly 9216 RGB bytes')
    palette=[list(pal[i:i+3]) for i in range(0,len(pal),3)]
    # Original dino QSound map exposes only 0x30000 gfx-RAM bytes.
    # Old generic adapter expects 0x40000. Reject out-of-map references
    # BEFORE extending to 0x40000, so zero padding cannot masquerade as RAM.
    for i in range(3):
        base=base_byte(a[(0x02+i*2)//2],SCROLL_SIZE)
        if base+SCROLL_SIZE>GFX_BYTES:
            raise ValueError(f'Scroll{i+1} base 0x{base:x} outside mapped RAM')
    if a[0x22//2]&1:
        addr=base_byte(a[0x08//2],OTHER_SIZE)
        if addr+OTHER_SIZE>GFX_BYTES:
            raise ValueError(f'Rowscroll base 0x{addr:x} outside mapped RAM')
    padded=gfx+[0]*((0x40000-GFX_BYTES)//2)
    # Placeholder is explicit sentinel only; no implied game sprites.
    obj=[0,0,0,0xff00]+[0]*(0x400-4)
    scene=convert_capture(padded,a,b,obj,effective_palette=palette)
    scene['buffered_obj_source']='UNAVAILABLE_MAME_LUA'
    scene['reference_frame']=frame_stem
    scene['pixel_parity_eligible']=False
    scene['capture_method']='mame_lua_frame_done'
    scene['reference_pixel_encoding']=manifest['reference_pixel_encoding']
    scene['reference_source_format']=manifest['reference_source_format']
    scene['gfxram_mapped_bytes']=GFX_BYTES
    scene['note']=('Authentic reference pixels; reconstructed RAM snapshot lacks '
                   'VBlank-latched sprite buffer and is NOT parity eligible')
    rgb=Path(str(stem)+'.reference-rgb24.bin').read_bytes()
    return scene,decode_reference_rgb24(rgb)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture_directory',type=Path)
    p.add_argument('frame_stem',help='e.g. frame-00000900')
    p.add_argument('--out-dir',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        scene,png=import_capture(args.capture_directory,args.frame_stem)
        args.out_dir.mkdir(parents=True,exist_ok=True)
        stem=args.frame_stem
        with (args.out_dir/(stem+'.partial-snapshot.json')).open('x',encoding='utf-8') as f:
            json.dump(scene,f,separators=(',',':'))
        with (args.out_dir/(stem+'.mame-reference.png')).open('xb') as f:
            f.write(png)
        print('Imported local MAME RGB and partial RAM:',stem)
        print('WARNING: internal buffered OBJ missing; no pixel-parity claim')
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(f'Capture rejected: {exc}',file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
