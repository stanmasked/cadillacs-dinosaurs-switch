#!/usr/bin/env python3
"""Fail-closed verifier of a ROM-free NRO-created NeXium guest replay report.

Does not run an emulator. PASS is valid only when CI independently
collected this specific file from the isolated emulated SD filesystem.
Never interpret a synthetic fixture as actual emulation evidence.
"""
import argparse
import csv
from pathlib import Path
import re

COLUMNS=['event','ticks','player_x','player_hp','hits',
         'state_fnv64','pcm_fnv64','pcm_blocks',
         'audio_ticks','audio_active','audio_queue_valid','audio_pending',
         'audio_submitted','audio_released','audio_skipped','audio_errors']
AUDIO_FIELDS=('audio_ticks','audio_active','audio_queue_valid',
              'audio_pending','audio_submitted','audio_released',
              'audio_skipped','audio_errors')
EXPECTED_STATE='5BCA2FF01FB244F6'
EXPECTED_PCM='D82C3B7960857B22'
HEX16=re.compile(r'[0-9A-F]{16}\Z')


def verify(path):
    """Return safe status plus the validated end state, no private paths."""
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('guest report absent or symlinked')
    if path.stat().st_size>4096:
        raise ValueError('guest report exceeds bounded record size')
    try:
        with path.open('r',newline='',encoding='ascii') as f:
            reader=csv.DictReader(f)
            if reader.fieldnames!=COLUMNS:
                raise ValueError('unknown or reordered guest fields')
            rows=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise ValueError('invalid guest report format') from exc
    if len(rows)!=3 or [r['event'] for r in rows]!=[
            'START','FRAME_SUBMITTED','REPLAY_DONE']:
        raise ValueError('missing actual guest execution checkpoints')
    values=[]
    audio_rows=[]
    for row in rows:
        if None in row or any(key is None for key in row):
            raise ValueError('ragged or unexpected guest columns')
        for key in ('state_fnv64','pcm_fnv64'):
            if not HEX16.fullmatch(row[key]):
                raise ValueError('malformed witness value')
        try:
            parsed=[int(row[key]) for key in
                    ('ticks','player_x','player_hp','hits','pcm_blocks')]
        except ValueError as exc:
            raise ValueError('invalid guest integer') from exc
        if any(value<0 or value>180 for value in
               (parsed[0],parsed[3],parsed[4])):
            raise ValueError('guest tick/counter out of bounds')
        values.append(parsed)
        # Queue status originates inside the running ARM64 guest;
        # generated PCM fingerprints alone say nothing about audout.
        try:
            a=[int(row[key]) for key in AUDIO_FIELDS]
        except ValueError as exc:
            raise ValueError('invalid guest audio integer') from exc
        tick, active, valid, pending, submitted, released, skipped, errors=a
        if (tick!=parsed[0] or active not in (0,1) or valid!=1 or
                pending>2 or min(a)<0 or submitted>tick or
                released>submitted or skipped>tick or
                submitted+skipped>tick or
                submitted-released!=pending or errors>tick+1 or
                (not active and pending)):
            raise ValueError('guest audio queue accounting inconsistent')
        audio_rows.append(a)
    start,frame,done=values
    if not (start[0]==0 and start[1]==90 and start[2]==5 and
            start[3]==0 and start[4]==0):
        raise ValueError('guest did not reset the training room')
    if not (1<=frame[0]<=180 and frame[4]<=frame[0]):
        raise ValueError('guest did not submit an advancing frame')
    if done!=[180,230,4,3,180]:
        raise ValueError('guest replay final state/ticks mismatch')
    if (rows[2]['state_fnv64']!=EXPECTED_STATE or
            rows[2]['pcm_fnv64']!=EXPECTED_PCM):
        raise ValueError('guest did not reproduce both golden hashes')
    if rows[0]['state_fnv64']!='CBF29CE484222325' or (
            rows[0]['pcm_fnv64']!='CBF29CE484222325'):
        raise ValueError('guest witness did not start from clean reset')
    return {
        'schema':'dino-nexium-guest-replay-v2',
        'status':'GUEST_REPLAY_WITNESSED',
        'guest_frame_submitted':True,
        'guest_controller_trace_steps':180,
        'player_x':230,
        'player_hp':4,
        'confirmed_hits':3,
        'state_fnv64':EXPECTED_STATE,
        'pcm_fnv64':EXPECTED_PCM,
        # Accepted guest submissions are NOT speaker output or sound.
        'guest_audio_queue_valid':bool(audio_rows[2][2]),
        'guest_audio_service_active_at_end':bool(audio_rows[2][1]),
        'guest_audio_submitted_at_end':audio_rows[2][4],
        'guest_audio_released_at_end':audio_rows[2][5],
        'guest_audio_skipped_at_end':audio_rows[2][6],
        'guest_audio_errors_at_end':audio_rows[2][7],
        'device_audio_audible_verified':False,
        'host_screen_pixels_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    opts=parser.parse_args(argv)
    import json
    try:
        result=verify(opts.report)
    except (ValueError,OSError):
        opts.out.write_text('INCONCLUSIVE: no valid NRO-produced guest '
                            'replay with two golden witnesses\n')
        return 1
    opts.out.write_text('PASS: guest-created 180-tick gameplay/PCM '
                        'witness; GPU pixels and audible sound '
                        'still NOT verified\n')
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
