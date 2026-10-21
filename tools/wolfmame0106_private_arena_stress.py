#!/usr/bin/env python3
"""PRIVATE WolfMAME P1 button stream -> invented ROM-free C training arena.

This tests handling of long recorded controller sequences. It does NOT
execute the original game, reproduce the original physics, or verify video.
The original input and derived complete byte stream NEVER enter GitHub.
"""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from tools.wolfmame0106_dino_input_reference import (
    metadata, HEADER_BYTES, FRAME_BYTES, PORTS)

ROOT=Path(__file__).resolve().parents[1]

def private_replay(inp,wlf,compiler='gcc'):
    if inp.is_symlink() or wlf.is_symlink():
        raise ValueError('Private input paths must not be symlinks')
    frames,version,_duration=metadata(inp,wlf)
    original=inp.read_bytes()
    if len(original)!=HEADER_BYTES+FRAME_BYTES*frames:
        raise ValueError('INP truncated during read')
    stream=memoryview(original)[HEADER_BYTES+PORTS['p1']::FRAME_BYTES].tobytes()
    if len(stream)!=frames:raise ValueError('P1 input count mismatch')
    executable=shutil.which(compiler)
    if executable is None:raise ValueError('Unavailable C compiler')
    with tempfile.TemporaryDirectory(prefix='dino274-') as directory:
        binary=Path(directory)/'arena_stress'
        subprocess.run([
            executable,'-std=c99','-O2','-Wall','-Wextra','-Werror',
            '-I',str(ROOT/'source'),str(ROOT/'source'/'dino_arena.c'),
            str(ROOT/'tools'/'dino_arena_recorded_input_stress.c'),
            '-o',str(binary)],check=True,capture_output=True,text=True,timeout=30)
        trials=[]
        for mode in ((),('--spar',)):
            proc=subprocess.run([str(binary),*mode],input=stream,
                                capture_output=True,timeout=45,check=True)
            result=json.loads(proc.stdout.decode('ascii'))
            if result['nominal_input_records']!=frames:
                raise ValueError('Native step count mismatch')
            if result['wolfmame_playback_verified'] is not False:
                raise ValueError('Training cannot certify emulator playback')
            trials.append(result)
    return {'schema':'dino-private-wolfmame-input-native-training-stress-v1',
            'status':'PRIVATE_INPUT_APPLIED_TO_INVENTED_ARENA_NOT_WOLFMAME',
            'game_tag':'dino','recording_version':version,
            'recording_frame_count':frames,
            'original_gameplay_emulated':False,
            'original_animation_verified':False,'training_runs':trials,
            'no_original_input_stream_embedded':True}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inp',type=Path,required=True)
    p.add_argument('--wlf',type=Path,required=True)
    p.add_argument('--compiler',choices=('gcc','clang'),default='gcc')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(argv)
    if ROOT in a.out.resolve().parents:
        raise ValueError('Private report must stay outside Git working tree')
    result=private_replay(a.inp,a.wlf,a.compiler)
    with a.out.open('x',encoding='utf-8') as out:
        json.dump(result,out,indent=2)
        out.write('\n')
    print(result['status'],result['recording_frame_count'])

if __name__=='__main__':
    main()
