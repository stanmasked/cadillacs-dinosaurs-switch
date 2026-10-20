#!/usr/bin/env python3
"""Render locally invented ROM-free training SFX to a standard PCM WAV.

The preview compiles source/dino_sfx.c (the very same engine used by
the Nintendo Switch) on the host. It never opens original game ROMs,
audio captures, games, proprietary samples, SD data or the network.
"""
import argparse
import ctypes
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import wave

ROOT=Path(__file__).resolve().parents[1]
RATE=48000
FRAMES=800
EVENTS=tuple(1<<i for i in range(11))
COUNTER_EVENT=1<<11

class Voice(ctypes.Structure):
    _fields_=[('phase',ctypes.c_uint32),('phase_step',ctypes.c_uint32),
              ('rng',ctypes.c_uint32),('remaining',ctypes.c_uint32),
              ('total',ctypes.c_uint32),('gain',ctypes.c_int32),
              ('pan',ctypes.c_int16),('wave',ctypes.c_uint8),
              ('priority',ctypes.c_uint8)]

class Synth(ctypes.Structure):
    _fields_=[('voices',Voice*6),
              ('ticks',ctypes.c_uint32),('launched',ctypes.c_uint32),
              ('dropped',ctypes.c_uint32)]

def render_preview(include_counter=False):
    compiler=shutil.which('gcc')
    if not compiler:
        raise RuntimeError('A host GCC compiler is required')
    with tempfile.TemporaryDirectory(prefix='dino-rom-free-pcm-') as td:
        target=Path(td)/'libdinosfx.so'
        proc=subprocess.run([
            compiler,'-std=c11','-O2','-Wall','-Wextra','-Werror',
            '-shared','-fPIC','-I'+str(ROOT/'source'),
            str(ROOT/'source'/'dino_sfx.c'),'-o',str(target)],
            check=False,capture_output=True,text=True)
        if proc.returncode:
            raise RuntimeError('Failed to compile the independent ROM-free SFX engine')
        lib=ctypes.CDLL(str(target))
        lib.dino_sfx_reset.argtypes=[ctypes.POINTER(Synth)]
        lib.dino_sfx_events.argtypes=[ctypes.POINTER(Synth),ctypes.c_uint32]
        lib.dino_sfx_render_tick.argtypes=[
            ctypes.POINTER(Synth),ctypes.POINTER(ctypes.c_int16),ctypes.c_size_t]
        sound=Synth()
        frame=(ctypes.c_int16*(2*FRAMES))()
        pcm=bytearray()
        # The original eleven-cue WAV stays byte-identical by default.
        # Only the opt-in preview appends the newly invented counter cue.
        for event in EVENTS+((COUNTER_EVENT,) if include_counter else ()):
            lib.dino_sfx_reset(ctypes.byref(sound))
            lib.dino_sfx_events(ctypes.byref(sound),event)
            for _ in range(24):
                lib.dino_sfx_render_tick(ctypes.byref(sound),frame,FRAMES)
                if sys.byteorder=='little':
                    pcm.extend(bytes(frame))
                else:
                    pcm.extend(b''.join(int(v).to_bytes(
                        2,'little',signed=True) for v in frame))
            pcm.extend(bytes(2*2*FRAMES*6)) # short silence between cues
        return bytes(pcm)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True,
                   help='Explicit local WAV output path; never overwrites')
    p.add_argument('--include-counter',action='store_true',
                   help='Append the new original counter cue; default 11 cues unchanged')
    args=p.parse_args(argv)
    try:
        pcm=render_preview(include_counter=args.include_counter)
        with args.out.open('xb') as handle:
            with wave.open(handle,'wb') as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(RATE)
                wav.writeframes(pcm)
    except (RuntimeError,OSError) as exc:
        # No user-supplied paths in the error (they might be private).
        print('ROM-free WAV preview refused: compiler/output unavailable',
              file=sys.stderr)
        return 2
    count=12 if args.include_counter else 11
    print(f'Generated synthetic stereo WAV, 48 kHz, {count} cues; no original game audio')
    return 0

if __name__=='__main__':
    raise SystemExit(main())
