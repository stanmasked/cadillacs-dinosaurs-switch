#!/usr/bin/env python3
"""Validate a separately collected guest ARM64 counter/PCM diagnostic CSV.

The validator works equally on host-created fixtures. It does NOT by itself
prove execution in NeXium: the workflow must collect the CSV from the
emulated SD after the real NRO runs and verify the existing replay witness.
"""
import argparse
import csv
import json
import re
from pathlib import Path

COLUMNS=['phase','tick','player_hp','enemy_hp','windup','stun',
         'cooldown','event_mask','pcm_nonzero','pcm_fnv64']
EXPECTED=[
    ['RESET',0,5,3,0,0,0,0,0,'CBF29CE484222325'],
    ['ARMED',1,5,3,12,0,0,1,0,'CBF29CE484222325'],
    ['COUNTER',2,5,3,0,9,48,2048,1,'1169E164EDF5FD7D'],
    ['RECOVERY',3,5,3,0,8,47,0,0,'CBF29CE484222325'],
    ['WRONG_FACING',2,4,3,0,0,48,384,0,'CBF29CE484222325'],
]


def verify(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('counter witness absent or symlink')
    if not 50 <= path.stat().st_size <= 1024:
        raise ValueError('counter witness length invalid')
    try:
        with path.open('r',encoding='ascii',newline='') as stream:
            reader=csv.DictReader(stream)
            if reader.fieldnames != COLUMNS:
                raise ValueError('unexpected guest counter columns')
            rows=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise ValueError('invalid counter witness format') from exc
    if len(rows)!=len(EXPECTED):
        raise ValueError('incomplete guest counter witness')
    for row, expected in zip(rows,EXPECTED):
        if None in row or any(v is None for v in row.values()):
            raise ValueError('ragged counter guest row')
        if row['phase']!=expected[0]:
            raise ValueError('out of order guest counter events')
        parsed=[]
        for field in COLUMNS[1:-1]:
            value=row[field]
            if not value or not value.isascii() or not value.isdecimal() or (
                    len(value)>1 and value.startswith('0')):
                raise ValueError('noncanonical counter integer')
            parsed.append(int(value))
        if parsed!=expected[1:-1]:
            raise ValueError('counter C state or PCM output incorrect')
        pcm_hash=row['pcm_fnv64']
        if not re.fullmatch(r'[0-9A-F]{16}',pcm_hash) or pcm_hash!=expected[-1]:
            raise ValueError('counter PCM differs from native golden samples')
    return {
        'schema':'dino-nexium-guest-counter-v1',
        'status':'ROM_FREE_COUNTER_TRACE_VALIDATED',
        'guest_ticks_for_positive_counter':2,
        'counter_event_bit':2048,
        'counter_pcm_nonzero':True,
        'counter_pcm_fnv64':'1169E164EDF5FD7D',
        'wrong_facing_counter_rejected':True,
        'requires_trusted_guest_file_extraction':True,
        'guest_hid_zr_verified':False,
        'physical_controller_verified':False,
        'physical_audio_verified':False,
        'original_arcade_mechanics_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        result=verify(args.report)
    except (OSError,ValueError,OverflowError):
        result={
            'schema':'dino-nexium-guest-counter-v1',
            'status':'INCONCLUSIVE_INVALID_COUNTER_GUEST_TRACE',
            'guest_hid_zr_verified':False,
            'physical_controller_verified':False,
            'physical_audio_verified':False,
        }
    args.out.write_text(json.dumps(result,sort_keys=True)+'\n',encoding='ascii')
    print(json.dumps(result,sort_keys=True))
    return 0 if result['status']=='ROM_FREE_COUNTER_TRACE_VALIDATED' else 1


if __name__=='__main__':
    raise SystemExit(main())
