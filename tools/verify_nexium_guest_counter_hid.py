#!/usr/bin/env python3
"""Optional, fail-closed NeXium evidence for a REAL guest libnx ZR edge.

The source NRO writes the file only after its 900-tick guest stress
finishes, and only after padGetButtonsDown(ZR) feeds an actual 60-Hz
pressed action. The guest's trial arena is specially staged to a
counter-ready state; this is NOT natural-play readiness, Joy-Con
hardware latency, or a measurement of actual speaker output.

Validation of a fabricated fixture alone is NOT NeXium evidence.
"""
import argparse
import csv
import json
import re
from pathlib import Path

FIELDS=['phase','tick','player_hp','enemy_hp','windup','stun',
        'cooldown','event_mask','hid_edge','pcm_nonzero','pcm_fnv64']
EXPECTED=[
    ['READY',1,5,3,12,0,0,1,0,0,'CBF29CE484222325'],
    ['HID_COUNTER',2,5,3,0,9,48,2048,1,1,'1169E164EDF5FD7D'],
]


def verify(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError('no genuine guest counter HID file')
    if not 55 <= path.stat().st_size <= 512:
        raise ValueError('invalid guest counter HID file size')
    try:
        with path.open(encoding='ascii',newline='') as handle:
            reader=csv.DictReader(handle)
            if reader.fieldnames!=FIELDS:
                raise ValueError('invalid guest HID counter schema')
            rows=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise ValueError('invalid guest HID counter encoding') from exc
    if len(rows)!=2:
        raise ValueError('counter HID evidence incomplete')
    for row,expected in zip(rows,EXPECTED):
        if None in row or any(value is None for value in row.values()):
            raise ValueError('malformed guest counter HID row')
        if row['phase']!=expected[0]:
            raise ValueError('counter HID phases out of order')
        parsed=[]
        for field in FIELDS[1:-1]:
            v=row[field]
            if not v or not v.isascii() or not v.isdecimal() or (
                    len(v)>1 and v.startswith('0')):
                raise ValueError('noncanonical counter HID integer')
            parsed.append(int(v))
        if parsed!=expected[1:-1]:
            raise ValueError('counter HID gameplay, key edge or PCM presence mismatch')
        hash_text=row['pcm_fnv64']
        if (not re.fullmatch(r'[0-9A-F]{16}',hash_text) or
                hash_text!=expected[-1]):
            raise ValueError('counter HID PCM differs from native C golden')
    return {
        'schema':'dino-nexium-counter-real-hid-v1',
        'status':'GUEST_LIBNX_ZR_EDGE_AND_COUNTER_EFFECT_WITNESSED',
        'recorded_after_guest_audio_stress':True,
        'guest_zr_edge_in_normal_60hz_step':True,
        'synthetic_pcm_verified':True,
        'counter_pcm_fnv64':'1169E164EDF5FD7D',
        'controlled_ready_training_arena_only':True,
        'physical_controller_hardware_verified':False,
        'natural_combat_counter_window_verified':False,
        'host_to_guest_latency_verified':False,
        'audio_output_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=verify(args.report)
    except (ValueError,OverflowError,OSError):
        result={
            'schema':'dino-nexium-counter-real-hid-v1',
            'status':'INCONCLUSIVE_NO_VALID_GUEST_ZR_COUNTER_EVIDENCE',
            'physical_controller_hardware_verified':False,
            'host_to_guest_latency_verified':False,
            'audio_output_verified':False,
        }
    args.out.write_text(json.dumps(result,sort_keys=True)+'\n',encoding='ascii')
    print(json.dumps(result,sort_keys=True))
    # Optional independent diagnostic: never replace a valid 180-tick
    # guest replay result with a missing/emulator-incompatible ZR mapping.
    return 0


if __name__=='__main__':
    raise SystemExit(main())
