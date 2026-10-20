#!/usr/bin/env python3
"""Required paired ROM-free *natural* AI ZR witness gate for real NeXium NROs.

The independent Stage 244 guest emits an unstaged natural AI windup
counter CSV only after actual libnx ZR presses. Both modes must now
supply matching recorded verifier JSON and counter PCM fingerprints.
The prerequisite Stage 241 staged counter witnesses are also freshly
reverified against each guest's audout report/mode binding/full NRO hash.

Never assert natural visible-player inputs, original ROM mechanics,
physical hardware sound, controller latency or causality between modes.
"""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_guest_counter_hid_paired as staged
    from tools import verify_nexium_guest_natural_counter_hid as natural
else:
    import verify_nexium_guest_counter_hid_paired as staged
    import verify_nexium_guest_natural_counter_hid as natural

SCHEMA='dino-nexium-paired-natural-hid-counter-v1'
STATUS='BOTH_NRO_MODES_NATURAL_AI_LIBNX_ZR_PCM_REVALIDATED'


def inspect_one(mode,guest_csv,recorded_json,stage):
    # The recorder only claims genuine natural guest mode if the CSV
    # independently yields its strict 117..128 tick and PCM verdict.
    expected=natural.verify(guest_csv)
    actual=staged.read_recorded_attestation(recorded_json)
    if actual!=expected:
        raise ValueError('recorded natural guest JSON differs from guest CSV')
    if (expected['status']!=
            'GUEST_UNSTAGED_AI_WINDUP_LIBNX_ZR_COUNTER_WITNESSED' or
            expected['independent_training_arena_only'] is not True or
            expected['guest_libnx_zr_edge_bound_to_counter_event'] is not True or
            expected['staged_telegraph_or_manual_coordinates_used'] is not False or
            expected['live_player_arena_input_verified'] is not False or
            expected['physical_joycon_verified'] is not False or
            expected['hardware_audio_output_verified'] is not False or
            expected['counter_pcm_fnv64']!=
            stage['synthetic_counter_pcm_fnv64']):
        raise ValueError('unsupported natural ZR/PCM assertion')
    path=Path(guest_csv)
    if path.is_symlink() or not path.is_file():
        raise ValueError('natural counter CSV disappeared')
    raw=path.read_bytes()
    if not 110<=len(raw)<=512 or natural.verify(path)!=expected:
        raise ValueError('natural guest CSV changed during verification')
    return {
        'audio_mode':mode,
        'guest_nro_sha256':stage['nro_sha256'],
        'audout_report_sha256':stage['guest_audio_stress_sha256'],
        'guest_natural_counter_csv_sha256':hashlib.sha256(raw).hexdigest(),
        'recorded_natural_json_matches_fresh_csv_validation':True,
        'counter_impact_tick':expected['counter_impact_tick'],
        'pre_windup':expected['counter_pre_windup'],
        'natural_ai_pursuit_required':True,
        'libnx_zr_edge_verified':True,
        'counter_software_pcm_fnv64':expected['counter_pcm_fnv64'],
    }


def compare(baseline_natural_csv,baseline_natural_json,
            baseline_staged_csv,baseline_staged_json,
            baseline_report,baseline_binding,baseline_nro,
            extra_natural_csv,extra_natural_json,
            extra_staged_csv,extra_staged_json,
            extra_report,extra_binding,extra_nro):
    # Stage 241 already checks identical recorded/independent staged
    # counter verdicts and binds each 900-tick audout report to the
    # selected mode and to the entire real built NRO. Repeat here to
    # ensure NATURAL guest records are paired to the exact same builds.
    prior=staged.compare(
        baseline_staged_csv,baseline_staged_json,
        baseline_report,baseline_binding,baseline_nro,
        extra_staged_csv,extra_staged_json,
        extra_report,extra_binding,extra_nro)
    if prior['status']!=staged.STATUS:
        raise ValueError('required staged guest ZR/NRO binding incomplete')
    baseline=inspect_one('baseline',baseline_natural_csv,
                         baseline_natural_json,prior['baseline'])
    extra=inspect_one('extra-poll',extra_natural_csv,
                      extra_natural_json,prior['extra_poll'])
    if baseline['guest_nro_sha256']==extra['guest_nro_sha256']:
        raise ValueError('paired natural witness requires two NRO builds')
    if (baseline['counter_software_pcm_fnv64']!=
            extra['counter_software_pcm_fnv64']):
        raise ValueError('natural counter PCM mismatch across guest modes')
    return {
        'schema':SCHEMA,
        'status':STATUS,
        'baseline':baseline,
        'extra_poll':extra,
        'both_guest_modes_naturally_telegraphed':True,
        'both_guest_modes_consumed_real_libnx_zr_edges':True,
        'both_guest_modes_match_staged_pcm_fingerprint':True,
        'matched_host_conditions_verified':False,
        'causal_audio_improvement_verified':False,
        'physical_joycon_verified':False,
        'live_player_arena_input_verified':False,
        'actual_speaker_audio_verified':False,
        'original_arcade_mechanics_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for mode in ('baseline','extra'):
        for field in ('natural-csv','natural-json','staged-csv',
                      'staged-json','report','binding','nro'):
            p.add_argument('--'+mode+'-'+field,required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    a=p.parse_args(argv)
    try:
        verdict=compare(a.baseline_natural_csv,a.baseline_natural_json,
                        a.baseline_staged_csv,a.baseline_staged_json,
                        a.baseline_report,a.baseline_binding,a.baseline_nro,
                        a.extra_natural_csv,a.extra_natural_json,
                        a.extra_staged_csv,a.extra_staged_json,
                        a.extra_report,a.extra_binding,a.extra_nro)
        with a.out.open('x',encoding='ascii') as dst:
            json.dump(verdict,dst,sort_keys=True)
            dst.write('\n')
    except (ValueError,OSError,UnicodeError,KeyError,TypeError,
            OverflowError) as exc:
        print(json.dumps({
            'schema':SCHEMA,
            'status':'INCONCLUSIVE_PAIRED_NATURAL_ZR_PCM_PROOF',
            'reason':type(exc).__name__,
        },sort_keys=True))
        return 1
    print(json.dumps(verdict,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
