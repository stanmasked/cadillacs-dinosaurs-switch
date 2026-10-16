#!/usr/bin/env python3
"""Convert explicit CPS-1 dino raw RAM/register dumps to a frame JSON snapshot.

No emulator integration is implied. Inputs must be captured at a coherent time.
The buffered object list must be captured separately from current gfx RAM.
"""
import argparse
import json
from pathlib import Path
import struct

GFX_RAM_BYTES = 0x40000
CPS_REG_BYTES = 0x40
BUFFERED_OBJ_BYTES = 0x800
SCROLL_SIZE = 0x4000
OTHER_SIZE = 0x800
PALETTE_ALIGN = 0x400


def words_from_binary(data, size, byteorder):
    if len(data) != size:
        raise ValueError(f'Expected {size} bytes, received {len(data)}')
    if byteorder not in ('big', 'little'):
        raise ValueError('Byte order must be big or little')
    return list(struct.unpack(('>' if byteorder == 'big' else '<') + str(size//2) + 'H', data))


def base_byte(register_word, boundary):
    """Matches MAME cps1_base: reg*256, align and mask into 0x40000 gfx RAM."""
    return ((register_word * 256) & ~(boundary - 1)) & 0x3ffff


def ram_slice(words, byte_offset, count):
    offset = byte_offset // 2
    if offset + count > len(words):
        raise ValueError('RAM subsection would run past end of capture')
    return words[offset:offset+count]


def convert_capture(gfxram, cps_a, cps_b, buffered_obj, *, effective_palette=None):
    """Return scene schema accepted by tools/cps1_frame.py.

    gfxram: 0x20000 words, CPS-A/CPS-B: 0x20 words each,
    buffered_obj: 0x400 words captured after OBJ VBlank latch.
    """
    for name, data, size in [('gfxram',gfxram,0x20000),('cps_a',cps_a,0x20),
                              ('cps_b',cps_b,0x20),('buffered_obj',buffered_obj,0x400)]:
        if len(data) != size or any(type(x) is not int or x < 0 or x > 0xffff for x in data):
            raise ValueError(f'{name}: expected {size} unsigned 16-bit values')
    if effective_palette is not None:
        if (len(effective_palette) != 3072 or
                any(not isinstance(x,(list,tuple)) or len(x)!=3 or
                    any(type(c) is not int or not 0 <= c <= 255 for c in x)
                    for x in effective_palette)):
            raise ValueError('Effective palette must be 3072 RGB tuples (0..255)')
    layer_control = cps_b[0x0a//2]   # CPS-B-21 QS2, dino only
    video_control = cps_a[0x22//2]
    scene = {
        'game': 'dino', 'board': 'CPS-B-21 QS2 / CD63B',
        'layer_control': layer_control,
        'priority_masks': [cps_b[n//2] for n in (0x0c, 0x0e, 0x00, 0x02)],
        'buffered_obj_words': list(buffered_obj),
        'video_control': video_control,
        'capture_note': 'Buffered OBJ must match video frame; palette source is not necessarily effective palette.'
    }
    # In MAME cps1_build_palette runs only on writes to CPS-A palette base.
    # Current gfx RAM words alone cannot recover previously copied pages.
    if effective_palette is not None:
        scene['palette_rgb'] = effective_palette
        scene['palette_fidelity'] = 'captured_effective_palette'
    else:
        addr = base_byte(cps_a[0x0a//2], PALETTE_ALIGN)
        scene['palette_source'] = {
            'control': cps_b[0x04//2],
            'words': ram_slice(gfxram, addr, 3072),
        }
        scene['palette_fidelity'] = 'approximate_current_source_not_latched'
    for i, name in enumerate(('scroll1','scroll2','scroll3')):
        base = base_byte(cps_a[(0x02 + i*2)//2], SCROLL_SIZE)
        scene[name] = {
            'words': ram_slice(gfxram, base, 0x2000),
            'scrollx': cps_a[(0x0c + i*4)//2],
            'scrolly': cps_a[(0x0e + i*4)//2],
            'enabled': bool(layer_control & 0x16) and (i==0 or bool(video_control & (1<<(i+1)))),
        }
    if video_control & 0x01:
        other_base = base_byte(cps_a[0x08//2], OTHER_SIZE)
        scene['rowscroll'] = ram_slice(gfxram, other_base, 1024)
        scene['rowscroll_offset'] = cps_a[0x20//2]
    return scene


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gfxram',type=Path,required=True, help='0x40000-byte local raw gfx RAM dump')
    p.add_argument('--cps-a',type=Path,required=True,help='0x40-byte raw CPS-A register dump')
    p.add_argument('--cps-b',type=Path,required=True,help='0x40-byte raw CPS-B register dump')
    p.add_argument('--buffered-obj',type=Path,required=True,help='0x800-byte *VBlank latched* OBJ RAM')
    p.add_argument('--endian',choices=('big','little'),required=True,
                   help='Binary dump word byte-order; do not guess host endianness')
    p.add_argument('--effective-palette',type=Path,
                   help='Optional 3072-entry JSON RGB array from effective palette RAM')
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        vals=(words_from_binary(path.read_bytes(),size,args.endian) for path,size in
              ((args.gfxram,GFX_RAM_BYTES),(args.cps_a,CPS_REG_BYTES),
               (args.cps_b,CPS_REG_BYTES),(args.buffered_obj,BUFFERED_OBJ_BYTES)))
        palette=json.loads(args.effective_palette.read_text(encoding='utf-8')) if args.effective_palette else None
        scene=convert_capture(*vals,effective_palette=palette)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(scene,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
        print(f'Snapshot created: {args.out}; palette fidelity: {scene["palette_fidelity"]}')
        return 0
    except (OSError,ValueError,KeyError,IndexError,TypeError) as exc:
        p.exit(2,f'Error: {exc}\n')

if __name__=='__main__':
    raise SystemExit(main())
