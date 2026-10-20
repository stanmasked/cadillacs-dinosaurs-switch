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


def press(key,duration=0.18,after_keydown=None,before_keydown=None):
    if before_keydown is not None:
        before_keydown()
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


def probe(window,roots,natural_seconds=14,ready_seconds=22,host_counter_out=None,host_frame_token_out=None,host_capture_window_out=None,host_command_bracket_out=None,host_transition_out=None):
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
    # Arm X11 BEFORE waiting for the naturally simulated 116-tick pursuit.
    # Arming only after the READY marker can consume the short ZR window
    # or race with the first post-ZR X11 image.
    watcher=pixels.CounterWindowWatcher(window) if (host_counter_out or host_frame_token_out or host_capture_window_out or host_command_bracket_out or host_transition_out) else None
    if watcher:
        watcher.start()
    if not until(live_windup_marker,roots,ready_seconds,0.05):
        if watcher:
            watcher.cancel('NO_LIVE_ARENA_WINDUP_MARKER')
            record=watcher.finish()
            if host_counter_out:
                pixels.save(host_counter_out,record)
            if host_frame_token_out:
                pixels.save(host_frame_token_out,watcher.frame_token_result())
            if host_capture_window_out:
                pixels.save(host_capture_window_out,watcher.capture_interval_result())
            if host_command_bracket_out:
                pixels.save(host_command_bracket_out,watcher.command_bracket_result())
            if host_transition_out:
                pixels.save(host_transition_out,watcher.transition_bracket_result())
        return {'status':'INCONCLUSIVE_NO_LIVE_ARENA_WINDUP_MARKER',
                'guest_live_counter_verified':False}
    input_failed=False
    try:
        press('t',0.12,after_keydown=watcher.trigger if watcher else None,
              before_keydown=watcher.begin_keydown_command if watcher else None)
    except (OSError,subprocess.SubprocessError):
        input_failed=True
        if watcher:
            watcher.cancel('HOST_ZR_INPUT_ERROR')
        raise
    finally:
        if watcher:
            record=watcher.finish()
            if input_failed:
                record=pixels.result(pixels.INCONCLUSIVE,
                                     reason='HOST_ZR_INPUT_ERROR')
            if host_counter_out:
                pixels.save(host_counter_out,record)
            if host_frame_token_out:
                token_record=watcher.frame_token_result()
                if input_failed:
                    token_record={**token_record,
                        'status':'INCONCLUSIVE_NO_X11_FRAME_TOKEN',
                        'token_u16':None,
                        'token_same_x11_image_as_counter_pixels':False}
                pixels.save(host_frame_token_out,token_record)
            if host_capture_window_out:
                window_record=watcher.capture_interval_result()
                if input_failed:
                    window_record=pixels.empty_capture_interval_result()
                pixels.save(host_capture_window_out,window_record)
            if host_command_bracket_out:
                bracket=watcher.command_bracket_result()
                if input_failed:
                    bracket=pixels.empty_command_bracket_result()
                pixels.save(host_command_bracket_out,bracket)
            if host_transition_out:
                bracket=watcher.transition_bracket_result()
                if input_failed:
                    bracket=pixels.empty_transition_bracket_result()
                pixels.save(host_transition_out,bracket)
    return {'status':'HOST_LIVE_SCENE_ZR_ATTEMPT_AFTER_REAL_Y_X',
            'guest_live_counter_verified':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--window',required=True)
    p.add_argument('--root',type=Path,required=True,action='append')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--host-counter-out',type=Path)
    p.add_argument('--host-frame-token-out',type=Path)
    p.add_argument('--host-capture-window-out',type=Path)
    p.add_argument('--host-command-bracket-out',type=Path)
    p.add_argument('--host-transition-out',type=Path)
    a=p.parse_args(argv)
    try:
        report=probe(a.window,a.root,host_counter_out=a.host_counter_out,
                     host_frame_token_out=a.host_frame_token_out,
                     host_capture_window_out=a.host_capture_window_out,
                     host_command_bracket_out=a.host_command_bracket_out,
                     host_transition_out=a.host_transition_out)
    except (ValueError,OSError,subprocess.SubprocessError):
        report={'status':'INCONCLUSIVE_LIVE_HOST_INPUT_UNAVAILABLE',
                'guest_live_counter_verified':False}
    # Early exits must explicitly say inconclusive, never synthesize a pass.
    if a.host_counter_out and not a.host_counter_out.is_file():
        pixels.save(a.host_counter_out,pixels.result(
            pixels.INCONCLUSIVE,reason='NO_REAL_ZR_ATTEMPT'))
    if a.host_frame_token_out and not a.host_frame_token_out.is_file():
        pixels.save(a.host_frame_token_out,{
            'schema':'dino-nexium-host-frame-token-v1',
            'status':'INCONCLUSIVE_NO_X11_FRAME_TOKEN',
            'token_u16':None,
            'token_same_x11_image_as_counter_pixels':False,
            'guest_submitted_frame_identity_verified':False,
            'exact_host_guest_frame_latency_verified':False,
            'physical_display_verified':False})
    if a.host_capture_window_out and not a.host_capture_window_out.is_file():
        pixels.save(a.host_capture_window_out,pixels.empty_capture_interval_result())
    if a.host_command_bracket_out and not a.host_command_bracket_out.is_file():
        pixels.save(a.host_command_bracket_out,pixels.empty_command_bracket_result())
    if a.host_transition_out and not a.host_transition_out.is_file():
        pixels.save(a.host_transition_out,pixels.empty_transition_bracket_result())
    report={'schema':'dino-nexium-host-live-counter-attempt-v1',**report}
    a.out.write_text(json.dumps(report,sort_keys=True)+'\n',encoding='ascii')
    print(json.dumps(report,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
