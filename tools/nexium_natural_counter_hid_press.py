#!/usr/bin/env python3
"""Best-effort second host T/ZR attempt during guest's *natural* AI windup.

The marker is guest-written only after 116 genuine simulation ticks and
natural enemy pursuit. A marker/host attempt by itself never claims a
counter, valid input, real guest execution or physical controller.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

READY_FILE='cadillacs-natural-counter-ready.csv'
READY_BYTES=(b'event,tick,player_x,enemy_x,windup,player_hp,enemy_hp\n'
             b'NATURAL_READY,116,90,134,12,5,3\n')


def natural_ready(roots):
    visited=set()
    for root in roots:
        parent=Path(root)
        if not parent.is_dir() or parent.is_symlink():
            continue
        resolved=os.fspath(parent.resolve())
        if resolved in visited:
            continue
        visited.add(resolved)
        for current,subdirs,files in os.walk(resolved,followlinks=False):
            subdirs[:]=[d for d in subdirs
                        if not (Path(current)/d).is_symlink()]
            if READY_FILE not in files:
                continue
            path=Path(current)/READY_FILE
            try:
                if (not path.is_symlink() and path.is_file() and
                        path.stat().st_size==len(READY_BYTES) and
                        path.read_bytes()==READY_BYTES):
                    return True
            except OSError:
                continue
    return False


def probe(window,roots,timeout_seconds=12,interval_seconds=0.05):
    if not window.isdecimal() or not 0<int(window)<2**32:
        raise ValueError('invalid X11 window id')
    if not roots:
        raise ValueError('no possible guest sd roots')
    deadline=time.monotonic()+timeout_seconds
    while time.monotonic()<deadline:
        if natural_ready(roots):
            subprocess.run(['xdotool','windowfocus',window],
                           timeout=5,check=False,capture_output=True)
            subprocess.run(['xdotool','keydown','t'],
                           timeout=5,check=True,capture_output=True)
            try:
                time.sleep(0.12)
            finally:
                subprocess.run(['xdotool','keyup','t'],
                               timeout=5,check=False,capture_output=True)
            return {'status':'HOST_SECOND_ZR_ATTEMPT_AT_NATURAL_WINDUP',
                    'guest_natural_counter_verified':False}
        time.sleep(interval_seconds)
    return {'status':'INCONCLUSIVE_NO_COMPLETE_NATURAL_READY_MARKER',
            'guest_natural_counter_verified':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--window',required=True)
    p.add_argument('--root',type=Path,required=True,action='append')
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        report=probe(args.window,args.root)
    except (ValueError,OSError,subprocess.SubprocessError):
        report={'status':'INCONCLUSIVE_NATURAL_ZR_ATTEMPT_UNAVAILABLE',
                'guest_natural_counter_verified':False}
    report={'schema':'dino-nexium-natural-host-zr-attempt-v1',**report}
    args.out.write_text(json.dumps(report,sort_keys=True)+'\n',
                        encoding='ascii')
    print(json.dumps(report,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
