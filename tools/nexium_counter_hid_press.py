#!/usr/bin/env python3
"""Best-effort external NeXium X11 T (default ZR) after guest audio stress.

Does NOT assert delivery by itself. Only the NRO's separate guest-written
CSV can show that libnx actually consumed a ZR edge and produced the
original counter combat event. No ROM, private paths or key logs retained.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess
import time

if __package__:
    from tools import verify_nexium_audio_stress as stress_schema
else:
    import verify_nexium_audio_stress as stress_schema

STRESS='cadillacs-audio-stress.csv'
HEX16=re.compile(r'[0-9A-F]{16}\\Z')


def is_complete_guest_stress(path):
    """Preflight only: accept a full 7-row NRO-written stress trace.

    This does NOT replace the separate deep numeric stress verifier,
    guest timeline binding, provenance checks or audout validation.
    Reject files still being written before attempting host key T.
    """
    if path.is_symlink() or not path.is_file():
        return False
    if not 128 <= path.stat().st_size <= 4096:
        return False
    with path.open(encoding='ascii',newline='') as stream:
        reader=csv.DictReader(stream)
        if reader.fieldnames != stress_schema.COLUMNS:
            return False
        rows=list(reader)
    if len(rows)!=7:
        return False
    start_tick=None
    for index,row in enumerate(rows):
        if None in row or any(value is None for value in row.values()):
            return False
        if row['event']!=stress_schema.EVENTS[index]:
            return False
        numeric_columns=(name for name in stress_schema.COLUMNS[1:]
                         if name!='pcm_fnv64')
        if any(not row[name].isascii() or not row[name].isdecimal() or
               (len(row[name])>1 and row[name].startswith('0')) or
               int(row[name])>0xffffffff for name in numeric_columns):
            return False
        if not HEX16.fullmatch(row['pcm_fnv64']):
            return False
        elapsed=int(row['elapsed_ticks'])
        arena=int(row['arena_ticks'])
        if elapsed != stress_schema.CHECKPOINTS[index]:
            return False
        if index==0:
            start_tick=arena
        elif arena!=start_tick+elapsed:
            return False
        if (int(row['audio_ticks']) != int(rows[0]['audio_ticks'])+elapsed or
                int(row['pcm_ticks']) != int(rows[0]['pcm_ticks'])+elapsed):
            return False
        if (row['active']!='1' or row['queue_valid']!='1' or
                int(row['pending'])>2 or
                int(row['submitted'])-int(row['released'])!=int(row['pending'])):
            return False
    return True


def stress_complete(roots):
    # Only consider regular, non-symlinked expected guest witness files.
    visited=set()
    for directory in roots:
        parent=Path(directory)
        if not parent.is_dir() or parent.is_symlink():
            continue
        real=os.fspath(parent.resolve())
        if real in visited:
            continue
        visited.add(real)
        for current, subdirs, files in os.walk(real,followlinks=False):
            subdirs[:]=[d for d in subdirs
                        if not (Path(current)/d).is_symlink()]
            if STRESS not in files:
                continue
            path=Path(current)/STRESS
            if path.is_symlink() or not path.is_file():
                continue
            try:
                if is_complete_guest_stress(path):
                    return True
            except (OSError,UnicodeError,csv.Error,ValueError):
                continue
    return False


def probe(window,roots,timeout_seconds=45,interval_seconds=0.5):
    if not window.isdecimal() or not 0<int(window)<2**32:
        raise ValueError('window identifier invalid')
    if not roots:
        raise ValueError('no emulated SD roots')
    deadline=time.monotonic()+timeout_seconds
    while time.monotonic()<deadline:
        if stress_complete(roots):
            # Standard NeXium keyboard binding from upstream
            # nexium-gui/src/controller_config.rs: ZR -> "T".
            # This is NOT a physical Joy-Con or confirmed guest input.
            subprocess.run(['xdotool','windowfocus',window],
                           timeout=5,check=False,capture_output=True)
            subprocess.run(['xdotool','keydown','t'],
                           timeout=5,check=True,capture_output=True)
            try:
                time.sleep(0.3)
            finally:
                subprocess.run(['xdotool','keyup','t'],
                               timeout=5,check=False,capture_output=True)
            return {'status':'HOST_ZR_KEY_ATTEMPT_AFTER_STRESS',
                    'guest_hid_counter_verified':False}
        time.sleep(interval_seconds)
    return {'status':'INCONCLUSIVE_NO_COMPLETED_GUEST_STRESS',
            'guest_hid_counter_verified':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--window',required=True)
    p.add_argument('--root',type=Path,action='append',required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        result=probe(args.window,args.root)
    except (ValueError,OSError,subprocess.SubprocessError):
        result={'status':'INCONCLUSIVE_HOST_ZR_UNAVAILABLE',
                'guest_hid_counter_verified':False}
    result={'schema':'dino-nexium-host-zr-attempt-v1',**result}
    args.out.write_text(json.dumps(result,sort_keys=True)+'\n',encoding='ascii')
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
