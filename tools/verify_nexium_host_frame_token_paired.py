#!/usr/bin/env python3
"""Stage 254: mandatory paired REAL NeXium X11↔guest submitted-frame identity.

Reverify native guest framebuffer, host X11 pixels, exact NRO and 900-tick
runtime AUDIO MODE before binding any observed 16-bit frame token to a
submitted render iteration. No physical LCD/scanout/input latency claim.
"""
import argparse
import json
from pathlib import Path

from tools import verify_nexium_host_counter_window_paired as window
from tools import verify_nexium_host_frame_token as frame

SCHEMA='dino-nexium-paired-host-guest-frame-token-v1'
STATUS='BOTH_REAL_NEXIUM_HOST_FRAMES_MATCH_GUEST_SUBMITTED_TOKENS'


def check_mode(mode,guest,nro):
    guest=Path(guest)
    # Pre-existing required Stage 252 check also validates libnx Y/X/T,
    # actual counter CSV, native pixel colors, raw stress report and
    # audio-mode-to-NRO SHA-256 binding (including swapped full A/B sets).
    prior=window.check_mode(mode,guest,nro)
    fresh=frame.verify(
        guest/'host-frame-token-evidence.json',
        guest/'host-counter-window-evidence.json',
        guest/'guest-live-counter-frame-tokens.csv',
        guest/'guest-live-counter-framebuffer.csv',
        guest/'metadata.txt',nro)
    # The independently guest-run optional diagnostic must agree EXACTLY
    # with our fresh recalculation, rather than supplying an invented PASS.
    stored=frame.load_json(guest/'host-guest-frame-token-evidence.json')
    if stored!=fresh:
        raise ValueError('stored cross-domain token proof does not match raw evidence')
    if (fresh.get('status')!=frame.SUCCESS or
        fresh.get('host_x11_guest_submitted_frame_identity_verified') is not True or
        fresh.get('nro_sha256')!=prior['nro_sha256'] or
        fresh.get('physical_switch_display_verified') is not False or
        fresh.get('precise_input_to_display_latency_verified') is not False or
        fresh.get('exact_display_scanout_timing_verified') is not False):
        raise ValueError('real X11 frame token not bound to selected NRO mode')
    if (type(fresh['matched_native_arena_tick']) is not int or
        fresh['matched_native_arena_tick']<prior['counter_tick'] or
        fresh['matched_native_arena_tick']>prior['counter_tick']+120):
        raise ValueError('observed guest render iteration not after real ZR counter')
    return {
        'mode':mode,
        'host_x11_guest_submitted_frame_identity_verified':True,
        'matched_native_render_iteration':fresh['matched_native_render_iteration'],
        'matched_native_arena_tick':fresh['matched_native_arena_tick'],
        'x11_token_u16':fresh['host_frame_token_u16'],
        'host_window_samples':prior['x11_samples'],
        'guest_counter_tick':prior['counter_tick'],
        'submitted_token_trace_rows':fresh['guest_trace_frame_count'],
        'nro_sha256':prior['nro_sha256'],
        'physical_switch_display_verified':False,
        'exact_host_input_to_display_latency_verified':False,
        'physical_controller_verified':False,
    }


def verify(baseline_dir,extra_dir,baseline_nro,extra_nro):
    baseline=check_mode('baseline',baseline_dir,baseline_nro)
    extra=check_mode('extra-poll',extra_dir,extra_nro)
    if baseline['nro_sha256']==extra['nro_sha256']:
        raise ValueError('independent NRO modes must have distinct binaries')
    return {
        'schema':SCHEMA,
        'status':STATUS,
        'both_real_nexium_host_frames_match_guest_submitted_tokens':True,
        'modes':{'baseline':baseline,'extra-poll':extra},
        'physical_switch_display_verified':False,
        'exact_input_to_display_latency_verified':False,
        'physical_joycon_verified':False,
        'speaker_audio_verified':False,
        'original_arcade_graphics_verified':False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-dir','extra-dir','baseline-nro','extra-nro','out'):
        parser.add_argument('--'+name,required=True,type=Path)
    opt=parser.parse_args(argv)
    result=verify(opt.baseline_dir,opt.extra_dir,
                  opt.baseline_nro,opt.extra_nro)
    # No overwrites of previous real CI evidence or user-supplied paths.
    with opt.out.open('x',encoding='ascii') as output:
        output.write(json.dumps(result,sort_keys=True)+'\n')
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
