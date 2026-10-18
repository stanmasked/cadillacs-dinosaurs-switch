#!/usr/bin/env python3
"""Validate linked guest ELF A/B audio function identities, ROM-free.

A symbol-table attestation proves only which functions were linked.
It does not prove the guest called them, speaker output, or latency.
"""
import argparse
from pathlib import Path
import re

CORE={
    'dino_switch_sound_guest_mid_batch_enabled',
    'dino_switch_sound_guest_mid_batch_calls',
    'dino_switch_sound_guest_mid_batch_releases',
}
EXPERIMENT='dino_switch_sound_guest_mid_batch_poll'
PATTERN=re.compile(r'\A[0-9a-fA-F]{1,16} ([TtWw]) '
                   r'(dino_switch_sound_guest_mid_batch_[a-z_]+)\Z')


def verify(symbol_table, variant):
    if variant not in ('baseline','extra'):
        raise ValueError('unrecognized A/B build variant')
    if not isinstance(symbol_table,str) or len(symbol_table)>5000000:
        raise ValueError('invalid bounded nm output')
    matches={}
    for line in symbol_table.splitlines():
        # Reject duplicate protected names even when the second line
        # has an unexpected/undefined type or an invalid address.
        for name in CORE | {EXPERIMENT}:
            if not line.endswith(' '+name):
                continue
            if name in matches:
                raise ValueError('duplicate protected symbol')
            m=PATTERN.fullmatch(line.strip())
            if not m or m.group(2)!=name:
                raise ValueError('protected symbol not executable')
            matches[name]=m.group(1)
    if not CORE.issubset(matches):
        raise ValueError('guest diagnostic function missing')
    if (EXPERIMENT in matches)!=(variant=='extra'):
        raise ValueError('guest linked experiment variant mismatch')
    return {
        'schema':'dino-audout-elf-mid-batch-linkage-v1',
        'status':'LINKED_SYMBOL_VARIANT_VERIFIED_ONLY',
        'variant':variant,
        'experiment_poll_symbol_linked':EXPERIMENT in matches,
        'guest_probe_symbols_linked':len(CORE),
        'guest_poll_actually_executed':False,
        'physical_switch_audio_verified':False,
        'audio_latency_verified':False,
        'causal_audio_improvement_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbols',required=True,type=Path)
    p.add_argument('--variant',required=True,choices=['baseline','extra'])
    args=p.parse_args(argv)
    if args.symbols.is_symlink() or not args.symbols.is_file():
        raise SystemExit('INCONCLUSIVE: symbol table file missing')
    data=args.symbols.read_text(encoding='ascii')
    try:
        r=verify(data,args.variant)
    except ValueError as exc:
        raise SystemExit('INCONCLUSIVE: '+str(exc))
    print(r['status'],r['variant'])
    return 0


if __name__=='__main__':
    raise SystemExit(main())
