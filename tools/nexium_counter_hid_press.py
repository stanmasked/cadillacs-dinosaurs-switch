#!/usr/bin/env python3
"""Best-effort external NeXium X11 T (default ZR) after guest audio stress.

Does NOT assert delivery by itself. Only the NRO's separate guest-written
CSV can show that libnx actually consumed a ZR edge and produced the
original counter combat event. No ROM, private paths or key logs retained.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

STRESS='cadillacs-audio-stress.csv'


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
                if not 100 <= path.stat().st_size <= 65536:
                    continue
                with path.open(encoding='ascii',errors='strict') as stream:
                    tail=stream.read()[-8192:]
                if any(line.startswith('STRESS_DONE,900,')
                       for line in tail.splitlines()):
                    return True
            except (OSError,UnicodeError):
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
