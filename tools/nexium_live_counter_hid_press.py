#!/usr/bin/env python3
"""Optional REAL Y -> X -> T/ZR host sequence for rendered NeXium arena.

Never claim input was received because xdotool returned zero. Only the
NRO-produced live-counter-hid.csv can attest that the *rendered* DinoArena
received three distinct real libnx edges and naturally advanced AI.
The prior Stage 245 hidden-arena natural proof is a precondition.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

if __package__:
    from tools import verify_nexium_guest_natural_counter_hid as natural
else:
    import verify_nexium_guest_natural_counter_hid as natural

if __package__:
    from tools import nexium_host_live_counter_pixel as pixels
else:
    import nexium_host_live_counter_pixel as pixels

NATURAL_FILE='cadillacs-natural-counter-hid.csv'
LIVE_READY_FILE='cadillacs-live-counter-ready.csv'
LIVE_READY_BYTES=(b'event,tick,player_x,enemy_x,windup,player_hp,enemy_hp\n'
                  b'LIVE_READY,116,90,134,12,5,3\n')


def eligible_files(roots,filename):
    visited=set()
    for root in roots:
        path=Path(root)
        if path.is_symlink() or not path.is_dir():
            continue
        real=os.fspath(path.resolve())
        if real in visited:
            continue
        visited.add(real)
        for current,dirs,files in os.walk(real,followlinks=False):
            dirs[:]=[d for d in dirs
                     if not (Path(current)/d).is_symlink()]
            if filename in files:
                path=Path(current)/filename
                if path.is_file() and not path.is_symlink():
                    yield path


def previous_guest_natural_witness(roots):
    for path in eligible_files(roots,NATURAL_FILE):
        try:
            if natural.verify(path)['status']==(
                'GUEST_UNSTAGED_AI_WINDUP_LIBNX_ZR_COUNTER_WITNESSED'):
                return True
        except (ValueError,UnicodeError,OSError):
            continue
    return False


def live_windup_marker(roots):
    for path in eligible_files(roots,LIVE_READY_FILE):
        try:
            if (path.stat().st_size==len(LIVE_READY_BYTES) and
                    path.read_bytes()==LIVE_READY_BYTES):
                return True
        except OSError:
            continue
    return False


def press(key,duration=0.18,after_keydown=None):
    subprocess.run(['xdotool','keydown',key],timeout=5,
                   check=True,capture_output=True)
    try:
        if after_keydown is not None:
            after_keydown()
        time.sleep(duration)
    finally:
        subprocess.run(['xdotool','keyup',key],timeout=5,
                       check=False,capture_output=True)


def until(fn,roots,seconds,interval):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        if fn(roots):
            return True
        time.sleep(interval)
    return False


def probe(window,roots,natural_seconds=14,ready_seconds=22,host_counter_out=None):
    if not window.isdecimal() or not 0<int(window)<2**32:
        raise ValueError('invalid NeXium X11 window')
    if not roots:
        raise ValueError('missing guest roots')
    if not until(previous_guest_natural_witness,roots,natural_seconds,0.05):
        return {'status':'INCONCLUSIVE_NO_PRIOR_GUEST_NATURAL_ZR',
                'guest_live_counter_verified':False}
    subprocess.run(['xdotool','windowfocus',window],
                   timeout=5,check=False,capture_output=True)
    # NeXium standard bindings Y='z', X='v', ZR='t'.
    # Crucially, these are three distinct host events, none of which
    # create a success CSV by themselves.
    press('z')
    time.sleep(0.25)
    press('v')
    if not until(live_windup_marker,roots,ready_seconds,0.05):
        return {'status':'INCONCLUSIVE_NO_LIVE_ARENA_WINDUP_MARKER',
                'guest_live_counter_verified':False}
    # Stage 250: an independent, optional X11 window sampler is armed
    # BEFORE T/ZR. It never creates or changes guest evidence and saves
    # only bounded JSON; a missing window cannot invalidate real guest HID.
    watcher=pixels.CounterWindowWatcher(window) if host_counter_out else None
    if watcher:
        watcher.start()
    try:
        press('t',0.12,after_keydown=watcher.trigger if watcher else None)
    finally:
        if watcher:
            pixels.save(host_counter_out,watcher.finish())
    return {'status':'HOST_LIVE_SCENE_ZR_ATTEMPT_AFTER_REAL_Y_X',
            'guest_live_counter_verified':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--window',required=True)
    p.add_argument('--root',type=Path,required=True,action='append')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--host-counter-out',type=Path)
    a=p.parse_args(argv)
    try:
        report=probe(a.window,a.root,host_counter_out=a.host_counter_out)
    except (ValueError,OSError,subprocess.SubprocessError):
        report={'status':'INCONCLUSIVE_LIVE_HOST_INPUT_UNAVAILABLE',
                'guest_live_counter_verified':False}
    # Early exits must explicitly say inconclusive, never synthesize a pass.
    if a.host_counter_out and not a.host_counter_out.is_file():
        pixels.save(a.host_counter_out,pixels.result(
            pixels.INCONCLUSIVE,reason='NO_REAL_ZR_ATTEMPT'))
    report={'schema':'dino-nexium-host-live-counter-attempt-v1',**report}
    a.out.write_text(json.dumps(report,sort_keys=True)+'\n',encoding='ascii')
    print(json.dumps(report,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
