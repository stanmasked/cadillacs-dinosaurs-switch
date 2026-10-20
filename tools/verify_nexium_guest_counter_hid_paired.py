#!/usr/bin/env python3
"""Revalidate independent ZR/counter PCM evidence from both real NRO modes.

Run only on files downloaded from completed NeXium CI guest jobs.
The JSON produced by each guest job must exactly match a fresh verifier
run on its two-row guest-owned CSV. Independently revalidate the
900-tick audio-mode binding against the matching compiled NRO.

Synthetic unit fixtures test the parser but are not real guest evidence.
No causal audio, physical Joy-Con, natural combat timing or speaker claims.
"""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_audio_paired_artifacts as paired_audio
    from tools import verify_nexium_guest_counter_hid as guest_counter
else:
    import verify_nexium_audio_paired_artifacts as paired_audio
    import verify_nexium_guest_counter_hid as guest_counter

STATUS='BOTH_NRO_MODES_GUEST_ZR_COUNTER_PCM_REVALIDATED'


def strict_pairs(pairs):
    result={}
    for name,value in pairs:
        if name in result:
            raise ValueError('duplicate attestation JSON key')
        result[name]=value
    return result


def read_recorded_attestation(path):
    path=Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('missing or linked counter guest attestation')
    if not 128<=path.stat().st_size<=2048:
        raise ValueError('unbounded guest counter attestation')
    raw=path.read_bytes()
    if not 128<=len(raw)<=2048:
        raise ValueError('guest counter attestation size changed')
    try:
        obj=json.loads(raw.decode('ascii'),object_pairs_hook=strict_pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(
                           ValueError('nonfinite counter attestation')))
    except (UnicodeError,json.JSONDecodeError) as exc:
        raise ValueError('malformed guest counter attestation') from exc
    if type(obj) is not dict:
        raise ValueError('counter attestation must be an object')
    return obj


def inspect_one(mode,guest_csv,recorded_json,stress_report,mode_binding,nro):
    bound=paired_audio.validate_binding(stress_report,mode_binding,mode,nro)
    # The guest NRO is selected by independent audio-report and byte hashes,
    # not by trusting the declared mode label in the counter CSV.
    expected=guest_counter.verify(guest_csv)
    recorded=read_recorded_attestation(recorded_json)
    if recorded!=expected:
        raise ValueError('counter guest attestation differs from raw PCM proof')
    if (expected['status']!=
            'GUEST_LIBNX_ZR_EDGE_AND_COUNTER_EFFECT_WITNESSED' or
            expected['counter_pcm_fnv64']!='1169E164EDF5FD7D' or
            expected['audio_output_verified'] is not False or
            expected['physical_controller_hardware_verified'] is not False):
        raise ValueError('unsupported or misleading guest counter claim')
    # Bound the second read, and reject symlinks before computing audit SHA.
    csv_path=Path(guest_csv)
    if csv_path.is_symlink() or not csv_path.is_file():
        raise ValueError('guest CSV missing after revalidation')
    raw=csv_path.read_bytes()
    if not 55<=len(raw)<=512:
        raise ValueError('guest CSV changed during revalidation')
    # The verifier must continue to accept those exact bytes.
    if guest_counter.verify(csv_path)!=expected:
        raise ValueError('guest counter CSV changed during audit')
    return {
        'audio_mode':mode,
        'nro_sha256':bound['guest_nro_sha256'],
        'guest_audio_stress_sha256':bound['guest_report_sha256'],
        'guest_counter_csv_sha256':hashlib.sha256(raw).hexdigest(),
        'recorded_counter_json_matches_fresh_verifier':True,
        'libnx_zr_counter_effect_witnessed':True,
        'synthetic_counter_pcm_fnv64':expected['counter_pcm_fnv64'],
        'software_generated_pcm_only':True,
    }


def compare(baseline_csv,baseline_json,baseline_report,baseline_binding,
            baseline_nro,extra_csv,extra_json,extra_report,extra_binding,
            extra_nro):
    baseline=inspect_one('baseline',baseline_csv,baseline_json,
                         baseline_report,baseline_binding,baseline_nro)
    extra=inspect_one('extra-poll',extra_csv,extra_json,
                      extra_report,extra_binding,extra_nro)
    if baseline['nro_sha256']==extra['nro_sha256']:
        raise ValueError('both guest-mode builds unexpectedly identical')
    if (baseline['synthetic_counter_pcm_fnv64']!=
            extra['synthetic_counter_pcm_fnv64']):
        raise ValueError('guest-mode PCM counter fingerprints differ')
    return {
        'schema':'dino-nexium-paired-real-hid-counter-v1',
        'status':STATUS,
        'baseline':baseline,
        'extra_poll':extra,
        'identical_counter_pcm_across_modes':True,
        'guest_counter_proof_reverified_in_both_modes':True,
        'matched_emulator_frame_pacing_verified':False,
        'physical_controller_verified':False,
        'natural_combat_counter_window_verified':False,
        'speaker_audio_verified':False,
        'audio_mode_causal_improvement_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for prefix in ('baseline','extra'):
        for name in ('csv','json','report','binding','nro'):
            p.add_argument('--'+prefix+'-'+name,type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(argv)
    try:
        obj=compare(a.baseline_csv,a.baseline_json,a.baseline_report,
                    a.baseline_binding,a.baseline_nro,
                    a.extra_csv,a.extra_json,a.extra_report,
                    a.extra_binding,a.extra_nro)
        with a.out.open('x',encoding='ascii') as result:
            json.dump(obj,result,sort_keys=True)
            result.write('\n')
    except (ValueError,OSError,UnicodeError,TypeError,OverflowError,
            KeyError) as exc:
        print(json.dumps({
            'schema':'dino-nexium-paired-real-hid-counter-v1',
            'status':'INCONCLUSIVE_PAIRED_GUEST_ZR_PCM_PROOF',
            'reason':type(exc).__name__,
        },sort_keys=True))
        return 1
    print(json.dumps(obj,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
