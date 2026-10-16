#!/usr/bin/env python3
"""Convert verified same-render-pass CPS-1 dino captures to native CPS1SEQ1.

Captures must be generated locally by the optional MAME screen_update
instrumentation from the parent PR. No ROM bytes or copyrighted data are
included in the program; gameplay/pixel parity are NOT thereby verified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

try:
    from tools.mame_render_import import import_render
    from tools.cps1_scene_export import pack_scene
    from tools.cps1_sequence_export import pack_sequence
except ModuleNotFoundError:
    from mame_render_import import import_render
    from cps1_scene_export import pack_scene
    from cps1_sequence_export import pack_sequence

MAX_FRAMES=120
SUFFIXES=('gfxram-be.bin','cps-a-be.bin','cps-b-be.bin',
          'buffered-obj-be.bin','palette-rgb24.bin','reference-rgb24.bin',
          'manifest.json')


def sha256(payload):
    return hashlib.sha256(payload).hexdigest()


def build_timeline(directory, first, count, *, stride=1, fps=60):
    """Rebuild one complete CPS1SEQ1; never interpolate a missing frame."""
    if type(first) is not int or not 0<=first<=99999999:
        raise ValueError('First frame must fit the 8-digit MAME frame name')
    if type(count) is not int or not 1<=count<=MAX_FRAMES:
        raise ValueError('Scene count must be 1..120')
    if type(stride) is not int or not 1<=stride<=120:
        raise ValueError('Frame stride must be explicitly 1..120')
    if type(fps) is not int or not 1<=fps<=60:
        raise ValueError('Viewer playback FPS must be 1..60')
    if first+(count-1)*stride>99999999:
        raise ValueError('Frame number exceeds 8-digit capture naming contract')
    directory=Path(directory)
    packed=[]
    sources=[]
    for slot in range(count):
        frame=first+slot*stride
        stem=f'frame-{frame:08d}'
        scene,reference_png=import_render(directory,stem)
        if (scene.get('buffered_obj_source')!='MAME_RENDER_CALLBACK_SAME_PASS'
                or scene.get('capture_hook')!='screen_update_cps1_complete'
                or scene.get('pixel_parity_eligible') is not True
                or scene.get('pixel_parity_verified') is not False
                or len(scene.get('buffered_obj_words',[]))!=1024):
            raise ValueError(f'Frame {frame}: missing real render-pass buffered OBJ')
        blob=pack_scene(scene)
        packed.append(blob)
        hashes={suffix:sha256((directory/(stem+'.'+suffix)).read_bytes())
                for suffix in SUFFIXES}
        sources.append({
            'slot':slot,'mame_frame':frame,'capture_stem':stem,
            'captured_stream_sha256':hashes,
            'scene_blob_sha256':sha256(blob),
            'reference_png_sha256':sha256(reference_png),
            'buffered_obj_confirmed':True,
        })
    timeline=pack_sequence(packed,fps)
    report={
        'format':'cps1_mame_render_timeline_provenance_v1',
        'game':'dino',
        'target':'Nintendo Switch native CPS1SEQ1 viewer v0.5+',
        'source':'external_MAME_screen_update_cps1_complete_capture',
        'capture_authenticity':'unverified_live_MAME_run',
        'first_mame_frame':first,'frame_stride':stride,
        'frame_count':count,'viewer_fps':fps,
        'timeline_bytes':len(timeline),
        'timeline_sha256':sha256(timeline),
        'all_frames_same_render_pass':True,
        'all_frames_have_buffered_obj':True,
        'pixel_parity_verified':False,
        'gameplay_reconstructed':False,
        'switch_hardware_tested':False,
        'notes':('This imports external same-pass captures, not game logic. '
                 'Successful import is not proof of MAME parity or a '
                 'playable original stage. FPS is viewer playback rate, '
                 'not proof of original emulation timing.'),
        'frames':sources,
    }
    return timeline,report


def export_timeline(directory,first,count,out_dir,*,stride=1,fps=60):
    """Do not commit outputs until all frame data have passed validation."""
    out_dir=Path(out_dir)
    sequence=out_dir/'sequence.bin'
    report_path=out_dir/'sequence-provenance.json'
    if sequence.exists() or report_path.exists():
        raise FileExistsError('Refusing to overwrite existing timeline or provenance')
    blob,report=build_timeline(directory,first,count,stride=stride,fps=fps)
    out_dir.mkdir(parents=True,exist_ok=True)
    written=[]
    try:
        with sequence.open('xb') as stream:
            written.append(sequence)
            stream.write(blob)
        with report_path.open('x',encoding='utf-8') as stream:
            written.append(report_path)
            json.dump(report,stream,ensure_ascii=False,indent=2)
            stream.write('\n')
    except (OSError,ValueError,TypeError):
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('capture_directory',type=Path)
    p.add_argument('--first-frame',type=int,required=True)
    p.add_argument('--count',type=int,required=True)
    p.add_argument('--stride',type=int,default=1)
    p.add_argument('--fps',type=int,default=60)
    p.add_argument('--out-dir',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        result=export_timeline(args.capture_directory,args.first_frame,args.count,
                               args.out_dir,stride=args.stride,fps=args.fps)
        print(f"Converted {result['frame_count']} verified-format captures to "
              f"{result['timeline_bytes']}-byte CPS1SEQ1; "
              'actual gameplay and pixel parity NOT verified')
        return 0
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:
        print('Capture timeline refused:',exc,file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
