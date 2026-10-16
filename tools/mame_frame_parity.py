#!/usr/bin/env python3
"""Local-only CPS-1 MAME capture-to-reconstruction pixel comparison.

Zero differences verify only one captured frame, not game-wide fidelity.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

try:
    from tools.mame_render_import import import_render
    from tools.cps1_frame import render_frame
    from tools.cps1_gfx import assemble_gfx
    from tools.cps1_tiles import _png_rgba
    from tools.frame_compare import compare_frames, load_rgba_png
    from tools.frame_error_profile import profile_rgba
except ModuleNotFoundError:
    from mame_render_import import import_render
    from cps1_frame import render_frame
    from cps1_gfx import assemble_gfx
    from cps1_tiles import _png_rgba
    from frame_compare import compare_frames, load_rgba_png
    from frame_error_profile import profile_rgba

DIMENSIONS=(384,224)


def run_parity(capture_directory, stem, graphics_region):
    """Measure per-pixel RGB error for a validated same-render-pass dump."""
    if len(graphics_region)!=0x400000:
        raise ValueError('Expected 4194304-byte interleaved CPS-1 GFX region')
    snapshot, reference_png=import_render(capture_directory,stem)
    if (snapshot.get('buffered_obj_source')!='MAME_RENDER_CALLBACK_SAME_PASS'
            or snapshot.get('pixel_parity_eligible') is not True
            or snapshot.get('pixel_parity_verified') is not False):
        raise ValueError('Not a valid unverified same-render-pass capture')
    rgba=render_frame(graphics_region,snapshot['palette_rgb'],snapshot)
    reconstructed_png=_png_rgba(*DIMENSIONS,rgba,
        'Independent partial CPS-1 reconstruction, ROM private')
    w,h,reference_rgba=load_rgba_png(reference_png)
    if (w,h)!=DIMENSIONS:
        raise ValueError('MAME reference resolution does not match 384x224')
    metrics,diff=compare_frames(reference_rgba,rgba,*DIMENSIONS)
    report={
        'format':'cps1_render_parity_report_v1',
        'game':'dino','capture_frame':stem,
        'same_render_callback_input':True,
        'effective_palette_source':'MAME_effective_pen_color',
        'buffered_sprite_source':'MAME_RENDER_CALLBACK_SAME_PASS',
        'pixel_parity_verified_for_this_frame':metrics['identical'],
        'game_wide_parity_verified':False,
        'native_switch_runtime_tested':False,
        'reconstruction_uses_partial_python_renderer':True,
        'reference_png_sha256':hashlib.sha256(reference_png).hexdigest(),
        'reconstructed_png_sha256':hashlib.sha256(reconstructed_png).hexdigest(),
        'comparison':metrics,
        'spatial_error_profile':profile_rgba(reference_rgba,raw,*DIMENSIONS),
    }
    return report,reference_png,reconstructed_png,_png_rgba(*DIMENSIONS,diff,
        'Pixel error; red channel = max abs error')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom_zip',type=Path,help='Your private dino.zip original ROM')
    p.add_argument('capture_directory',type=Path)
    p.add_argument('frame_stem',help='frame-XXXXXXXX')
    p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--require-exact',action='store_true',
        help='Exit 1 unless every pixel matches; still save report')
    args=p.parse_args(argv)
    try:
        with zipfile.ZipFile(args.rom_zip) as z:
            region=assemble_gfx(z.read)
        report,ref,recreated,diff=run_parity(args.capture_directory,
            args.frame_stem,region)
        args.out_dir.mkdir(parents=True,exist_ok=True)
        files={
            args.frame_stem+'.mame-reference.png':ref,
            args.frame_stem+'.reconstructed.png':recreated,
            args.frame_stem+'.error-heatmap.png':diff,
            args.frame_stem+'.parity-report.json':(json.dumps(report,indent=2)+'\n').encode(),
        }
        existing=[name for name in files if (args.out_dir/name).exists()]
        if existing:
            raise FileExistsError('Refusing to overwrite: '+', '.join(existing))
        for name,data in files.items():
            with (args.out_dir/name).open('xb') as out:
                out.write(data)
        print(json.dumps(report['comparison'],indent=2))
        print('Game-wide parity NOT verified; single-frame comparison only.')
        return int(args.require_exact and not report['comparison']['identical'])
    except (OSError,ValueError,TypeError,KeyError,zipfile.BadZipFile) as exc:
        print('CPS-1 frame comparison failed:',exc,file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
