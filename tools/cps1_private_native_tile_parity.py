#!/usr/bin/env python3
"""Private user-owned CPS-1 graphics: native Switch C/Python tile comparison.

Never commit or publish the original ROM, 4-MiB assembled graphics, hashes
or original pixel data. Matching tile indices do not establish CPS-1
runtime palette, VRAM, original MAME gameplay, or Switch pixel parity.
"""
import argparse
import ctypes
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import zipfile

try:
    from tools.cps1_gfx import LANES, ROM_SIZE, assemble_gfx
except ModuleNotFoundError:
    from cps1_gfx import LANES, ROM_SIZE, assemble_gfx

TILE_BYTES=128
TILE_PIXELS=256
GFX_BYTES=0x400000
TILE_COUNT=GFX_BYTES//TILE_BYTES
SAMPLE_SEED=0xC0A029


def sampled_codes():
    rng=random.Random(SAMPLE_SEED)
    return tuple(sorted(set(
        list(range(128))+
        list(range(TILE_COUNT-128,TILE_COUNT))+
        list(range(0,TILE_COUNT,64))+
        [rng.randrange(TILE_COUNT) for _ in range(768)]
    )))


def python_reference_tile(region,code):
    """Independent planar 16x16 extraction without calling C."""
    if not 0<=code<TILE_COUNT:
        raise ValueError('Private tile code out of range')
    start=code*TILE_BYTES
    out=bytearray(TILE_PIXELS)
    for y in range(16):
        for x in range(16):
            base=start+y*8+(x//8)*4
            bit=7-(x%8)
            out[y*16+x]=sum(
                ((region[base+p]>>bit)&1)<<(3-p) for p in range(4))
    return bytes(out)


def read_private_gfx(archive_path):
    """Bound ZIP extraction to the eight 512-KiB original GFX lanes."""
    with zipfile.ZipFile(archive_path) as z:
        names=z.namelist()
        if any(names.count(name)!=1 for name,_ in LANES):
            raise ValueError('Private graphics ROM lanes absent or ambiguous')
        if any(z.getinfo(name).file_size!=ROM_SIZE for name,_ in LANES):
            raise ValueError('Private graphics ROM lane length mismatch')
        region=assemble_gfx(z.read)
    if len(region)!=GFX_BYTES:
        raise ValueError('Assembled private graphics size invalid')
    return region


def compile_native_decoder(output):
    """Compile the actual ROM-free portable C used by Nintendo Switch NRO."""
    source=Path(__file__).resolve().parents[1]/'source'/'cps1_tile.c'
    subprocess.run(
        ['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
         '-fPIC','-shared',str(source),'-o',str(output)],
        check=True,capture_output=True,timeout=60)


def _report(status, **counts):
    return {
        'schema':'PRIVATE_DINO_NATIVE_TILE_PARITY_V1',
        'status':status,
        'diagnostic_only':True,
        'original_rom_bytes_written_to_disk':False,
        'original_game_data_in_report':False,
        'original_game_authenticity_verified':False,
        'mame_gameplay_verified':False,
        'physical_vblank_verified':False,
        'switch_pixel_parity_verified':False,
        **counts,
    }


def compare_private_rom_native_tiles(archive_path):
    region=read_private_gfx(archive_path)
    with tempfile.TemporaryDirectory(prefix='cps1-native-rom-free-build-') as directory:
        binary=Path(directory)/'cps1_tile.so'
        compile_native_decoder(binary)
        library=ctypes.CDLL(str(binary))
        fn=library.cps1_decode_tile16
        fn.argtypes=[ctypes.c_void_p,ctypes.c_size_t,
                     ctypes.c_size_t,ctypes.c_void_p]
        fn.restype=ctypes.c_bool
        source=(ctypes.c_uint8*len(region)).from_buffer_copy(region)
        out=(ctypes.c_uint8*TILE_PIXELS)()
        counts=set()
        mismatch=uniform=0
        codes=sampled_codes()
        for code in codes:
            if not fn(source,len(region),code,out):
                raise ValueError('Native decoder refused a valid tile')
            actual=bytes(out)
            expected=python_reference_tile(region,code)
            mismatch+=actual!=expected
            uniform+=len(set(actual))==1
            counts.update(actual)
        bounds_rejected=(
            not fn(source,len(region),TILE_COUNT,out) and
            not fn(source,129,0,out))
        if mismatch or not bounds_rejected:
            return _report('PRIVATE_DINO_NATIVE_TILE_PARITY_FAILED',
                           sampled_tiles=len(codes),
                           compared_pixels=len(codes)*TILE_PIXELS,
                           mismatching_tiles=mismatch,
                           native_bounds_rejected=bounds_rejected)
        return _report('PRIVATE_DINO_NATIVE_TILE_PARITY_PASSED',
                       assembled_gfx_bytes=GFX_BYTES,
                       available_tile_codes=TILE_COUNT,
                       sampled_tiles=len(codes),
                       compared_pixels=len(codes)*TILE_PIXELS,
                       mismatching_tiles=0,
                       uniform_sampled_tiles=uniform,
                       sampled_palette_index_count=len(counts),
                       native_bounds_rejected=True)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('private_owned_dino_zip',type=Path)
    args=p.parse_args(argv)
    try:
        result=compare_private_rom_native_tiles(args.private_owned_dino_zip)
    except (OSError,ValueError,zipfile.BadZipFile,
            subprocess.SubprocessError,RuntimeError,AttributeError) as exc:
        reason=('PRIVATE_NATIVE_DECODER_BUILD_REFUSED'
                if isinstance(exc,subprocess.SubprocessError)
                else 'PRIVATE_NATIVE_TILE_INPUT_REFUSED')
        result=_report(reason)
    print(json.dumps(result,sort_keys=True))
    return 0 if result['status']=='PRIVATE_DINO_NATIVE_TILE_PARITY_PASSED' else 2


if __name__=='__main__':
    raise SystemExit(main())
