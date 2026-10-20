#!/usr/bin/env python3
"""Optional *unstaged* NeXium guest ZR counter trace verifier.

The separate CI-only DinoArena resets normally and advances one 60-Hz
step per actual guest game tick. Its AI must first pursue from x=250
to x=134 and naturally produce the 12-tick windup at tick 116.
A *second* real libnx ZR edge can trigger a counter only at ticks
117..128. Host keyboard attempts alone do not provide this proof.

This does not claim a physical Joy-Con, real game/ROM AI, live player
arena interaction, audible hardware output or input latency.
"""
import argparse
import csv
import json
import re
from pathlib import Path

COLUMNS=['event','tick','player_x','enemy_x','pre_windup',
         'player_hp','enemy_hp','post_windup','stun','cooldown',
         'event_mask','hid_edge','pcm_nonzero','pcm_fnv64']
HEX=re.compile(r'[0-9A-F]{16}\Z')


def verify(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing genuine guest natural ZR CSV')
    if not 110 <= path.stat().st_size <= 512:
        raise ValueError('invalid natural ZR file size')
    try:
        with path.open(encoding='ascii',newline='') as stream:
            reader=csv.DictReader(stream)
            if reader.fieldnames!=COLUMNS:
                raise ValueError('invalid guest natural counter header')
            rows=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise ValueError('invalid natural counter encoding') from exc
    if len(rows)!=1:
        raise ValueError('one natural ZR impact required')
    row=rows[0]
    if None in row or any(value is None for value in row.values()):
        raise ValueError('ragged natural ZR row')
    if row['event']!='NATURAL_HID_COUNTER':
        raise ValueError('wrong natural ZR phase')
    values={}
    for key in COLUMNS[1:-1]:
        token=row[key]
        if (not token or not token.isascii() or not token.isdecimal()
                or (len(token)>1 and token.startswith('0'))
                or len(token)>10 or int(token)>0xffffffff):
            raise ValueError('noncanonical guest natural counter integer')
        values[key]=int(token)
    tick=values['tick']
    expected={
        'player_x':90,'enemy_x':134,'pre_windup':129-tick,
        'player_hp':5,'enemy_hp':3,
        'post_windup':0,'stun':9,'cooldown':48,
        'event_mask':2048,'hid_edge':1,'pcm_nonzero':1,
    }
    if tick<117 or tick>128 or any(values[k]!=v
                                   for k,v in expected.items()):
        raise ValueError('natural AI state / libnx ZR impact mismatch')
    if not HEX.fullmatch(row['pcm_fnv64']) or (
            row['pcm_fnv64']!='1169E164EDF5FD7D'):
        raise ValueError('natural counter PCM not identical to golden')
    return {
        'schema':'dino-nexium-natural-hid-counter-v1',
        'status':'GUEST_UNSTAGED_AI_WINDUP_LIBNX_ZR_COUNTER_WITNESSED',
        'counter_impact_tick':tick,
        'counter_pre_windup':values['pre_windup'],
        'natural_ai_pursuit_required':True,
        'one_guest_simulation_step_per_tick':True,
        'guest_libnx_zr_edge_bound_to_counter_event':True,
        'counter_pcm_fnv64':row['pcm_fnv64'],
        'staged_telegraph_or_manual_coordinates_used':False,
        'independent_training_arena_only':True,
        'live_player_arena_input_verified':False,
        'physical_joycon_verified':False,
        'hardware_audio_output_verified':False,
        'original_arcade_mechanics_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        output=verify(args.report)
    except (ValueError,OSError,UnicodeError,OverflowError):
        output={
            'schema':'dino-nexium-natural-hid-counter-v1',
            'status':'INCONCLUSIVE_NO_GENUINE_UNSTAGED_GUEST_ZR_COUNTER',
            'live_player_arena_input_verified':False,
            'physical_joycon_verified':False,
            'hardware_audio_output_verified':False,
        }
    args.out.write_text(json.dumps(output,sort_keys=True)+'\n',encoding='ascii')
    print(json.dumps(output,sort_keys=True))
    # Initial guest-timing experiment is optional; missing X11 edge
    # must NOT make the historical full 900-tick A/B proof appear false.
    return 0


if __name__=='__main__':
    raise SystemExit(main())
