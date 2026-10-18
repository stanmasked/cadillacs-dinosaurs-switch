#!/usr/bin/env python3
"""Safely pair two ROM-free NeXium guest audio reports and their mode bindings.

A successful comparison establishes descriptive accounting, never causal
audio benefit, physical device playback or identical host conditions.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import compare_nexium_audio_stress_runs as cross
    from tools import verify_nexium_audio_mid_batch_ab as ab
    from tools import verify_nexium_audio_mode_binding as binding
else:
    import compare_nexium_audio_stress_runs as cross
    import verify_nexium_audio_mid_batch_ab as ab
    import verify_nexium_audio_mode_binding as binding


def validate_binding(report_path, binding_path, mode):
    # Read only a bounded ordinary file; do not follow symlinks.
    path=Path(binding_path)
    if path.is_symlink() or not path.is_file() or not 64<=path.stat().st_size<=8192:
        raise ValueError('invalid mode attestation file')
    raw=path.read_bytes()
    if not 64<=len(raw)<=8192:
        raise ValueError('unbounded mode attestation')
    try:
        actual=json.loads(raw.decode('ascii'),object_pairs_hook=cross.parse_pairs)
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError('invalid mode attestation JSON') from exc
    # This recomputes raw SHA-256 and validates the entire 900-tick guest
    # record and selected mode, including actual guest extra-poll counts.
    expected=binding.attest(mode,report_path)
    if type(actual) is not dict or actual!=expected:
        raise ValueError('mode attestation does not match guest evidence')
    return expected


def compare(base_report,base_binding,extra_report,extra_binding):
    base=validate_binding(base_report,base_binding,'baseline')
    extra=validate_binding(extra_report,extra_binding,'extra-poll')
    result=ab.compare(base_report,extra_report)
    return {
        'schema':'dino-nexium-bound-audio-ab-v1',
        'status':'UNCONTROLLED_BOUND_GUEST_AUDIO_COMPARISON_DESCRIPTIVE_ONLY',
        'baseline_report_sha256':base['guest_report_sha256'],
        'experimental_report_sha256':extra['guest_report_sha256'],
        'baseline_guest_poll_calls':base['guest_poll_calls'],
        'experimental_guest_poll_calls':extra['guest_poll_calls'],
        'descriptive_comparison':result,
        'host_conditions_matched_verified':False,
        'causal_audio_improvement_verified':False,
        'physical_switch_audio_verified':False,
        'audio_latency_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-report','baseline-binding',
                 'experimental-report','experimental-binding'):
        p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--out',type=Path)
    a=p.parse_args(argv)
    try:
        result=compare(a.baseline_report,a.baseline_binding,
                       a.experimental_report,a.experimental_binding)
        line=json.dumps(result,sort_keys=True)+'\n'
        if a.out is not None:
            with a.out.open('x',encoding='ascii') as f:
                f.write(line)
        code=0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,OverflowError) as exc:
        result={
            'schema':'dino-nexium-bound-audio-ab-v1',
            'status':'INCONCLUSIVE_UNVERIFIED_BOUND_GUEST_AUDIO_COMPARISON',
            'reason':type(exc).__name__,
            'host_conditions_matched_verified':False,
            'causal_audio_improvement_verified':False,
            'physical_switch_audio_verified':False,
            'audio_latency_verified':False,
        }
        line=json.dumps(result,sort_keys=True)+'\n'
        if a.out is not None:
            try:
                with a.out.open('x',encoding='ascii') as f:
                    f.write(line)
            except OSError:
                pass
        code=1
    print(line,end='')
    return code


if __name__=='__main__':
    raise SystemExit(main())
