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


def validate_binding(report_path, binding_path, mode, nro_path):
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
    expected=binding.attest(mode,report_path,nro_path)
    if type(actual) is not dict or actual!=expected:
        raise ValueError('mode attestation does not match guest evidence')
    return expected


def window_skip_diagnostics(comparison):
    """Locate concentrated cross-run skip differences, without causal claims.

    A guest-only audit: six exact, consecutive 150-tick windows and both
    aggregate guest skip totals must reconcile before any data are output.
    """
    baseline=comparison['baseline_150tick_batch_exposure']
    experimental=comparison['experimental_150tick_batch_exposure']
    if len(baseline)!=6 or len(experimental)!=6:
        raise ValueError('six 150-tick guest windows required')
    rows=[]
    for index,(a,b) in enumerate(zip(baseline,experimental)):
        start=index*150
        end=start+150
        if (a['tick_start']!=start or a['tick_end']!=end or
                b['tick_start']!=start or b['tick_end']!=end):
            raise ValueError('misaligned guest skip window')
        def skipped(row):
            values=[row[key] for key in
                    ('single_skips','first_batch_skips','later_batch_skips')]
            if any(type(v) is not int or not 0<=v<=150 for v in values):
                raise ValueError('invalid guest skip counts')
            return sum(values)
        left=skipped(a)
        right=skipped(b)
        if left>150 or right>150:
            raise ValueError('guest skips exceed window duration')
        rows.append({
            'tick_start':start,'tick_end':end,
            'baseline_skips':left,
            'experimental_skips':right,
            'experimental_minus_baseline_skips':right-left,
        })
    if (sum(row['baseline_skips'] for row in rows)!=
            comparison['baseline']['audio_blocks_skipped'] or
            sum(row['experimental_skips'] for row in rows)!=
            comparison['experimental']['audio_blocks_skipped']):
        raise ValueError('per-window guest skips do not reconcile')
    positive=sum(max(row['experimental_minus_baseline_skips'],0)
                 for row in rows)
    largest=max(rows,key=lambda row:row['experimental_minus_baseline_skips'])
    return {
        'per_150tick_skip_deltas':rows,
        'total_positive_skip_excess':positive,
        'largest_positive_skip_excess_window':(
            {
                'tick_start':largest['tick_start'],
                'tick_end':largest['tick_end'],
                'excess':largest['experimental_minus_baseline_skips'],
                'share_numerator':largest['experimental_minus_baseline_skips'],
                'share_denominator':positive,
            } if positive>0 and largest['experimental_minus_baseline_skips']>0
            else None),
        'matched_six_window_batch_exposure':(
            comparison['per_150tick_batch_exposure_matched'] is True),
        'causal_audio_improvement_verified':False,
        'matched_host_conditions_verified':False,
    }


def compare(base_report,base_binding,extra_report,extra_binding,
            base_nro,extra_nro):
    base=validate_binding(base_report,base_binding,'baseline',base_nro)
    extra=validate_binding(extra_report,extra_binding,'extra-poll',extra_nro)
    if base['guest_nro_sha256']==extra['guest_nro_sha256']:
        raise ValueError('baseline and experimental NRO binaries are identical')
    result=ab.compare(base_report,extra_report)
    diagnostic=window_skip_diagnostics(result)
    return {
        'schema':'dino-nexium-bound-audio-ab-v1',
        'status':'UNCONTROLLED_BOUND_GUEST_AUDIO_COMPARISON_DESCRIPTIVE_ONLY',
        'baseline_report_sha256':base['guest_report_sha256'],
        'baseline_guest_nro_sha256':base['guest_nro_sha256'],
        'experimental_guest_nro_sha256':extra['guest_nro_sha256'],
        'experimental_report_sha256':extra['guest_report_sha256'],
        'baseline_guest_poll_calls':base['guest_poll_calls'],
        'experimental_guest_poll_calls':extra['guest_poll_calls'],
        'descriptive_comparison':result,
        'window_skip_diagnostics':diagnostic,
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
    p.add_argument('--baseline-nro',type=Path,required=True)
    p.add_argument('--experimental-nro',type=Path,required=True)
    p.add_argument('--out',type=Path)
    a=p.parse_args(argv)
    try:
        result=compare(a.baseline_report,a.baseline_binding,
                       a.experimental_report,a.experimental_binding,
                       a.baseline_nro,a.experimental_nro)
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
