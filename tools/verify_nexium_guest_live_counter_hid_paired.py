#!/usr/bin/env python3
"""Required A/B attestation for actual *rendered-arena* guest libnx Y/X/ZR.

This replays the previous required Stage 245 paired natural/staged
counter + PCM + per-mode audout + distinct full compiled NRO bindings
and additionally revalidates the genuine Stage 246 LIVE_HID_COUNTER
guest CSVs against their guest-recorded JSON in BOTH guest modes.

The live arena IS the same C gameplay object passed to arena_frame;
no real display pixel, Joy-Con hardware, audio speaker, original arcade
mechanics, end-to-end timing, or audio-mode causal improvement is proven.
Fixtures in unit tests are synthetic and never constitute guest evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_guest_natural_counter_hid_paired as prior
    from tools import verify_nexium_guest_counter_hid_paired as staged
    from tools import verify_nexium_guest_live_counter_hid as live
else:
    import verify_nexium_guest_natural_counter_hid_paired as prior
    import verify_nexium_guest_counter_hid_paired as staged
    import verify_nexium_guest_live_counter_hid as live

SCHEMA='dino-nexium-paired-live-arena-counter-v1'
STATUS='BOTH_NRO_MODES_VISIBLE_ARENA_LIBNX_ZR_PCM_REVALIDATED'


def inspect_one(mode,guest_csv,recorded_json,previous):
    # Treat either recorded JSON or CSV missing as a hard error, never a
    # silently successful "optional" input or trusted host key attempt.
    fresh=live.verify(guest_csv)
    recorded=staged.read_recorded_attestation(recorded_json)
    if recorded!=fresh:
        raise ValueError('recorded live guest attestation differs from CSV')
    if (fresh['status']!=live.STATUS or
            fresh['live_rendered_arena_game_state_verified'] is not True or
            fresh['real_guest_y_reset_required'] is not True or
            fresh['real_guest_x_spar_toggle_required'] is not True or
            fresh['natural_ai_pursuit_required'] is not True or
            fresh['guest_libnx_zr_edge_bound_to_counter'] is not True or
            fresh['physical_joycon_verified'] is not False or
            fresh['hardware_display_pixels_at_counter_verified'] is not False or
            fresh['audible_speaker_sound_verified'] is not False or
            fresh['input_latency_verified'] is not False or
            fresh['original_arcade_mechanics_verified'] is not False or
            fresh['software_pcm_fnv64']!=
            previous['counter_software_pcm_fnv64']):
        raise ValueError('unsupported recorded live scene ZR assertions')
    file=Path(guest_csv)
    if file.is_symlink() or not file.is_file():
        raise ValueError('live CSV disappeared during attestation')
    raw=file.read_bytes()
    if not 110<=len(raw)<=512 or live.verify(file)!=fresh:
        raise ValueError('live game-state CSV changed during validation')
    return {
        'audio_mode':mode,
        'guest_nro_sha256':previous['guest_nro_sha256'],
        'audout_report_sha256':previous['audout_report_sha256'],
        'guest_live_counter_csv_sha256':hashlib.sha256(raw).hexdigest(),
        'recorded_live_json_matches_independent_verifier':True,
        'relative_counter_tick':fresh['counter_impact_relative_tick'],
        'pre_counter_enemy_windup':fresh['counter_pre_windup'],
        'real_guest_y_x_zr_edges_required':True,
        'same_rendered_arena_state_used_for_counter':True,
        'counter_software_pcm_fnv64':fresh['software_pcm_fnv64'],
    }


def compare(baseline_live_csv,baseline_live_json,
            baseline_natural_csv,baseline_natural_json,
            baseline_staged_csv,baseline_staged_json,
            baseline_report,baseline_binding,baseline_nro,
            extra_live_csv,extra_live_json,
            extra_natural_csv,extra_natural_json,
            extra_staged_csv,extra_staged_json,
            extra_report,extra_binding,extra_nro):
    # Do not trust a new live CSV without independently rechecking the
    # upstream required guest natural/staged proofs and two NRO hashes.
    original=prior.compare(
        baseline_natural_csv,baseline_natural_json,
        baseline_staged_csv,baseline_staged_json,
        baseline_report,baseline_binding,baseline_nro,
        extra_natural_csv,extra_natural_json,
        extra_staged_csv,extra_staged_json,
        extra_report,extra_binding,extra_nro)
    if original['status']!=prior.STATUS:
        raise ValueError('missing prior required natural guest proof')
    baseline=inspect_one('baseline',baseline_live_csv,baseline_live_json,
                         original['baseline'])
    extra=inspect_one('extra-poll',extra_live_csv,extra_live_json,
                      original['extra_poll'])
    if baseline['guest_nro_sha256']==extra['guest_nro_sha256']:
        raise ValueError('identical baseline/extra-poll compiled NRO')
    if baseline['counter_software_pcm_fnv64']!=extra['counter_software_pcm_fnv64']:
        raise ValueError('rendered arena counter PCM differs across guest modes')
    return {
        'schema':SCHEMA,
        'status':STATUS,
        'baseline':baseline,
        'extra_poll':extra,
        'both_modes_rendered_arena_counter_reverified':True,
        'both_modes_real_y_x_zr_guest_effects_required':True,
        'prior_natural_staged_pcm_guest_and_nro_bindings_rechecked':True,
        'matching_emulator_host_conditions_verified':False,
        'audio_mode_causal_improvement_verified':False,
        'physical_joycon_verified':False,
        'display_pixels_during_counter_verified':False,
        'speaker_audio_verified':False,
        'original_arcade_mechanics_verified':False,
        'input_latency_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for mode in ('baseline','extra'):
        for field in ('live-csv','live-json','natural-csv','natural-json',
                      'staged-csv','staged-json','report','binding','nro'):
            p.add_argument('--'+mode+'-'+field,type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        result=compare(
            args.baseline_live_csv,args.baseline_live_json,
            args.baseline_natural_csv,args.baseline_natural_json,
            args.baseline_staged_csv,args.baseline_staged_json,
            args.baseline_report,args.baseline_binding,args.baseline_nro,
            args.extra_live_csv,args.extra_live_json,
            args.extra_natural_csv,args.extra_natural_json,
            args.extra_staged_csv,args.extra_staged_json,
            args.extra_report,args.extra_binding,args.extra_nro)
        with args.out.open('x',encoding='ascii') as out:
            json.dump(result,out,sort_keys=True)
            out.write('\n')
    except (ValueError,OSError,UnicodeError,KeyError,TypeError,
            OverflowError) as exc:
        print(json.dumps({
            'schema':SCHEMA,
            'status':'INCONCLUSIVE_PAIRED_VISIBLE_ARENA_ZR_PCM_PROOF',
            'reason':type(exc).__name__,
        },sort_keys=True))
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
