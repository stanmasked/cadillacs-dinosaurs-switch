#!/usr/bin/env python3
"""Audit native CPS-1 planar decoding against Python using ONLY local GFX bytes.

Supply graphics region privately extracted from your legitimately held dino
ROM. No original bytes are committed or uploaded by this tool.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile

try:
    from tools.cps1_tiles import decode_tile
except ModuleNotFoundError:
    from cps1_tiles import decode_tile

ROOT=Path(__file__).resolve().parents[1]
FORMATS=(
    ('8x8-left','cps1_decode_tile8',8,64,False),
    ('8x8-right','cps1_decode_tile8',8,64,True),
    ('16x16','cps1_decode_tile16',16,128,False),
    ('32x32','cps1_decode_tile32',32,512,False),
)


def audit(region, count=256, seed=38102026, compiler='gcc'):
    if not isinstance(region,(bytes,bytearray)) or len(region)==0:
        raise ValueError('Nonempty raw CPS-1 GFX region required')
    if type(count) is not int or count<1 or count>65536:
        raise ValueError('Sample size must be 1..65536 tiles per format')
    if not shutil.which(compiler):
        raise ValueError('Host C compiler unavailable: '+compiler)
    with tempfile.TemporaryDirectory(prefix='cps1-gfx-verify-') as temp:
        library=Path(temp)/'libcps1verify.so'
        build=subprocess.run(
            [compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror','-shared',
             '-fPIC','-Isource','source/cps1_tile.c','-o',str(library)],
            cwd=ROOT,capture_output=True,text=True)
        if build.returncode:
            raise ValueError('Native C layout library did not compile: '+build.stderr)
        dll=ctypes.CDLL(str(library))
        results=[]
        for layout,symbol,side,unit,right in FORMATS:
            if len(region)%unit:
                raise ValueError('GFX byte count is not aligned to '+layout)
            codes=len(region)//unit
            chosen={0,codes-1,codes//2}
            rng=random.Random(seed+unit+int(right))
            while len(chosen)<min(count,codes):
                chosen.add(rng.randrange(codes))
            fn=getattr(dll,symbol)
            fn.argtypes=([ctypes.c_void_p,ctypes.c_size_t,ctypes.c_size_t,
                          ctypes.c_bool,ctypes.c_void_p] if side==8 else
                         [ctypes.c_void_p,ctypes.c_size_t,ctypes.c_size_t,
                          ctypes.c_void_p])
            fn.restype=ctypes.c_bool
            digest=hashlib.sha256()
            mismatches=[]
            for code in sorted(chosen):
                out=ctypes.create_string_buffer(side*side)
                ok=fn(region,len(region),code,right,out) if side==8 else (
                    fn(region,len(region),code,out))
                if not ok:
                    raise ValueError(f'Native {layout} decoder rejected valid tile {code}')
                digest.update(out.raw)
                if out.raw!=decode_tile(region,layout,code):
                    mismatches.append(code)
            results.append({
                'layout':layout,'tile_count':codes,'tested_tiles':len(chosen),
                'tested_pixels':len(chosen)*side*side,
                'mismatched_tiles':len(mismatches),
                'mismatch_codes_first_10':mismatches[:10],
                'decoded_sample_sha256':digest.hexdigest(),
            })
    return {'tool':'cps1_native_gfx_audit','format':1,
            'source':'user_local_gfx_region','commercial_assets_embedded':False,
            'sample_seed':seed,'samples_requested_per_format':count,
            'tested_pixels':sum(x['tested_pixels'] for x in results),
            'mismatched_tiles':sum(x['mismatched_tiles'] for x in results),
            'checks':results}


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('gfx',type=Path,help='Private local 4 MiB deinterleaved gfx.bin')
    ap.add_argument('--samples',type=int,default=256)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args(argv)
    try:
        region=args.gfx.read_bytes()
        if len(region)!=0x400000:
            raise ValueError('dino GFX must contain exactly 4194304 bytes')
        result=audit(region,args.samples)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8') as f:
            json.dump(result,f,indent=2)
            f.write('\n')
        print('C/Python parity:',result['tested_pixels'],'pixels;',
              result['mismatched_tiles'],'mismatched tiles')
        return int(result['mismatched_tiles']!=0)
    except (OSError,ValueError,TypeError) as exc:
        print('GFX audit failed:',exc,file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
