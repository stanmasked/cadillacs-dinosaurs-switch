#!/usr/bin/env python3
"""Import same-render-pass CPS-1 dino RAM, palette, OBJ and RGB reference.

This enables ATTEMPTING pixel parity, not claiming that pixel parity matched.
All captured data and exported snapshots remain private/local.
"""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
try:
    from tools.cps1_capture import convert_capture, base_byte, SCROLL_SIZE, OTHER_SIZE
    from tools.cps1_tiles import _png_rgba
except ModuleNotFoundError:
    from cps1_capture import convert_capture, base_byte, SCROLL_SIZE, OTHER_SIZE
    from cps1_tiles import _png_rgba

RAM_BYTES=0x30000
SIZES={'gfxram-be.bin':RAM_BYTES,'cps-a-be.bin':64,'cps-b-be.bin':64,
       'buffered-obj-be.bin':2048,'palette-rgb24.bin':9216,
       'reference-rgb24.bin':384*224*3}
STEM=re.compile(r'frame-([0-9]{8,20})\Z')

def import_render(directory, stem):
    if not isinstance(stem,str) or not STEM.fullmatch(stem):
        raise ValueError('Invalid frame stem')
    directory=Path(directory)
    info=json.loads((directory/(stem+'.manifest.json')).read_text('utf-8'))
    expected={'game':'dino','frame':int(stem[6:]),
              'capture_hook':'screen_update_cps1_complete',
              'full_cliprect':True,'buffered_obj_same_render_pass':True,
              'reference_pixel_encoding':'rgb24_palette_resolved',
              'raw_word_endianness':'big',
              'palette_source':'MAME_effective_pen_color',
              'gfxram_bytes':RAM_BYTES,'cps_a_bytes':64,'cps_b_bytes':64,
              'buffered_obj_bytes':2048,'palette_bytes':9216,
              'reference_rgb_bytes':258048,
              'reference_width':384,'reference_height':224,
              'pixel_parity_verified':False}
    for k,value in expected.items():
        if type(info.get(k)) is not type(value) or info.get(k)!=value:
            raise ValueError(f'Manifest field {k} missing or wrong')
    data={}
    for suffix,size in SIZES.items():
        raw=(directory/(stem+'.'+suffix)).read_bytes()
        if len(raw)!=size:
            raise ValueError(f'{suffix}: expected {size} bytes, got {len(raw)}')
        data[suffix]=raw
    def words(suffix):
        raw=data[suffix]
        return list(struct.unpack('>'+str(len(raw)//2)+'H',raw))
    gfx=words('gfxram-be.bin')
    a=words('cps-a-be.bin')
    b=words('cps-b-be.bin')
    obj=words('buffered-obj-be.bin')
    for layer in range(3):
        offset=base_byte(a[(0x02+layer*2)//2],SCROLL_SIZE)
        if offset+SCROLL_SIZE>RAM_BYTES:
            raise ValueError('Scroll base outside mapped 192KiB graphics RAM')
    if a[0x22//2]&1:
        offset=base_byte(a[0x08//2],OTHER_SIZE)
        if offset+OTHER_SIZE>RAM_BYTES:
            raise ValueError('Rowscroll outside mapped 192KiB graphics RAM')
    raw_palette=data['palette-rgb24.bin']
    colors=[list(raw_palette[i:i+3]) for i in range(0,len(raw_palette),3)]
    snapshot=convert_capture(gfx+[0]*((0x40000-RAM_BYTES)//2),a,b,obj,
                             effective_palette=colors)
    snapshot.update(reference_frame=stem,
        capture_hook='screen_update_cps1_complete',
        buffered_obj_source='MAME_RENDER_CALLBACK_SAME_PASS',
        gfxram_mapped_bytes=RAM_BYTES,
        pixel_parity_eligible=True,
        pixel_parity_verified=False,
        capture_note='Screen RGB and buffered OBJ from same render callback; '
                     'matching reconstruction has not yet been proven.')
    rgb=data['reference-rgb24.bin']
    rgba=bytearray(384*224*4)
    for i in range(384*224):
        rgba[i*4:i*4+3]=rgb[i*3:i*3+3]
        rgba[i*4+3]=255
    return snapshot,_png_rgba(384,224,rgba,'CPS-1 same render-pass reference; parity NOT verified')

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture_dir',type=Path)
    p.add_argument('frame_stem')
    p.add_argument('--out-dir',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        snapshot,png=import_render(args.capture_dir,args.frame_stem)
        args.out_dir.mkdir(parents=True,exist_ok=True)
        with (args.out_dir/(args.frame_stem+'.snapshot.json')).open('x',encoding='utf-8') as f:
            json.dump(snapshot,f,separators=(',',':'))
        with (args.out_dir/(args.frame_stem+'.reference.png')).open('xb') as f:
            f.write(png)
        print('Imported render-pass scene. Pixel parity NOT verified.')
        return 0
    except (ValueError,KeyError,OSError,TypeError) as exc:
        print('Import rejected:',exc,file=sys.stderr)
        return 2

if __name__=='__main__':
    raise SystemExit(main())
