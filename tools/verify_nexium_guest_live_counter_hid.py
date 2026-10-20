#!/usr/bin/env python3
"""Optional fail-closed verifier of real NeXium input in the *visible* arena.

Only guest-written one-row evidence from the actual `DinoArena arena`
which is passed to `arena_frame`, following real Y reset, X spar input,
116 naturally simulated pursuit ticks and an actual ZR counter event.

Does not demonstrate physical controllers, user-visible photon changes,
host input latency, original Capcom mechanics or actual audible sound.
"""
import argparse
import csv
import json
from pathlib import Path
import re

FIELDS=('event','tick','player_x','enemy_x','pre_windup',
        'player_hp','enemy_hp','post_windup','stun','cooldown','event_mask',
        'hid_edge','pcm_nonzero','pcm_fnv64')
FNV64='1169E164EDF5FD7D'
HEX=re.compile(r'[0-9A-F]{16}\Z')
STATUS='GUEST_VISIBLE_ARENA_NATURAL_AI_LIBNX_ZR_COUNTER_WITNESSED'


def verify(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing genuine guest visible-arena ZR CSV')
    if not 110<=path.stat().st_size<=512:
        raise ValueError('unexpected visible-arena ZR trace length')
    try:
        with path.open(encoding='ascii',newline='') as stream:
            rows=csv.DictReader(stream)
            if tuple(rows.fieldnames or ())!=FIELDS:
                raise ValueError('noncanonical visible-arena CSV fields')
            records=list(rows)
    except (UnicodeError,csv.Error) as exc:
        raise ValueError('malformed guest visible-arena CSV') from exc
    if len(records)!=1 or None in records[0]:
        raise ValueError('expected one complete live counter')
    row=records[0]
    if any(value is None for value in row.values()):
        raise ValueError('ragged live arena evidence')
    if row['event']!='LIVE_HID_COUNTER':
        raise ValueError('only real visible-arena counter accepted')
    values={}
    for field in FIELDS[1:-1]:
        val=row[field]
        if (not val or not val.isascii() or not val.isdecimal() or
                (len(val)>1 and val.startswith('0')) or
                len(val)>10 or int(val)>0xffffffff):
            raise ValueError('noncanonical natural live integer')
        values[field]=int(val)
    tick=values['tick']
    expected={
        'player_x':90,'enemy_x':134,
        'pre_windup':129-tick,
        'player_hp':5,'enemy_hp':3,
        'post_windup':0,'stun':9,'cooldown':48,
        'event_mask':2048,'hid_edge':1,'pcm_nonzero':1,
    }
    if tick<117 or tick>128 or any(values[k]!=v
                                   for k,v in expected.items()):
        raise ValueError('live arena scene action not naturally valid')
    if not HEX.fullmatch(row['pcm_fnv64']) or row['pcm_fnv64']!=FNV64:
        raise ValueError('wrong computed counter PCM')
    return {
        'schema':'dino-nexium-live-natural-counter-v1',
        'status':STATUS,
        'live_rendered_arena_game_state_verified':True,
        'real_guest_y_reset_required':True,
        'real_guest_x_spar_toggle_required':True,
        'natural_ai_pursuit_required':True,
        'guest_libnx_zr_edge_bound_to_counter':True,
        'counter_impact_relative_tick':tick,
        'counter_pre_windup':values['pre_windup'],
        'software_pcm_fnv64':row['pcm_fnv64'],
        'physical_joycon_verified':False,
        'hardware_display_pixels_at_counter_verified':False,
        'audible_speaker_sound_verified':False,
        'original_arcade_mechanics_verified':False,
        'input_latency_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        report=verify(args.report)
    except (ValueError,OSError,UnicodeError,OverflowError):
        report={
            'schema':'dino-nexium-live-natural-counter-v1',
            'status':'INCONCLUSIVE_NO_LIVE_GUEST_NATURAL_ZR_COUNTER',
            'live_rendered_arena_game_state_verified':False,
            'physical_joycon_verified':False,
            'hardware_display_pixels_at_counter_verified':False,
            'audible_speaker_sound_verified':False,
        }
    args.out.write_text(json.dumps(report,sort_keys=True)+'\n',
                        encoding='ascii')
    print(json.dumps(report,sort_keys=True))
    # This first live-scene trial is optional, not the Stage 245 gate.
    return 0


if __name__=='__main__':
    raise SystemExit(main())
