#!/usr/bin/env python3
"""Bind a selected ROM-free Switch NRO mode to actual 900-tick guest evidence.

A build manifest alone cannot verify which guest code ran. After NeXium
execution, validate the full stress report and read the guest-emitted
optional-poll flag/call counters. No original arcade assets are needed.
"""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from tools import compare_nexium_audio_stress_runs as cross
    from tools import verify_nexium_audio_mid_batch_ab as ab
else:
    import compare_nexium_audio_stress_runs as cross
    import verify_nexium_audio_mid_batch_ab as ab

MODES=('baseline','extra-poll')


def attest(selected_mode, report_path):
    if selected_mode not in MODES:
        raise ValueError('unsupported requested NRO audio mode')
    raw,report=cross.read_report(Path(report_path))
    cross.validate(report)
    witness=ab.verify_mode(report,selected_mode=='extra-poll')
    return {
        'schema':'dino-nexium-guest-audio-mode-binding-v1',
        'status':'SELECTED_AUDIO_MODE_WITNESSED_BY_GUEST',
        'selected_mode':selected_mode,
        'guest_report_sha256':hashlib.sha256(raw).hexdigest(),
        'guest_poll_enabled':selected_mode=='extra-poll',
        'guest_poll_calls':witness['additional_nonblocking_poll_calls'],
        'guest_poll_released_pages':witness['pages_released_by_additional_polls'],
        'guest_later_batch_steps':witness['later_batch_ticks'],
        'guest_simulation_ticks':witness['total_guest_ticks'],
        'audio_latency_verified':False,
        'causal_audio_improvement_verified':False,
        'physical_switch_audio_verified':False,
        'original_arcade_audio_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selected-mode',required=True,choices=MODES)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args(argv)
    try:
        result=attest(args.selected_mode,args.report)
        line=json.dumps(result,sort_keys=True)+'\n'
        if args.out is not None:
            # Exclusive creation protects the original guest evidence and
            # earlier attestations even if --out is a symlink to either.
            with args.out.open('x',encoding='ascii') as stream:
                stream.write(line)
    except (OSError,ValueError,KeyError,TypeError,OverflowError,
            UnicodeError) as exc:
        result={
            'schema':'dino-nexium-guest-audio-mode-binding-v1',
            'status':'INCONCLUSIVE_AUDIO_MODE_NOT_GUEST_BOUND',
            'reason':type(exc).__name__,
            'audio_latency_verified':False,
            'causal_audio_improvement_verified':False,
            'physical_switch_audio_verified':False,
            'original_arcade_audio_verified':False,
        }
        code=1
        line=json.dumps(result,sort_keys=True)+'\n'
    else:
        code=0
    print(line,end='')
    return code


if __name__=='__main__':
    raise SystemExit(main())
