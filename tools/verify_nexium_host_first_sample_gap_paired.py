#!/usr/bin/env python3
"""Stage 264: bound the initial unsampled host X11 interval.

This is a HOST-only, conservative rounded-time diagnostic from the
completion of an xdotool keydown subprocess to the *start* of the first
post-command XGetImage call. It is not first visual onset, guest HID
delivery or controller-to-display latency.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_host_x11_cadence_paired as cadence
    from tools import verify_nexium_host_keydown_bracket_paired as keydown
else:
    import verify_nexium_host_x11_cadence_paired as cadence
    import verify_nexium_host_keydown_bracket_paired as keydown

SCHEMA = 'dino-nexium-paired-host-initial-x11-blind-interval-v1'
STATUS = 'BOTH_REAL_NRO_BOUND_INITIAL_X11_UNSAMPLED_INTERVALS_AUDITED'


def one(mode, guest_dir, nro):
    # Revalidate two existing independent source chains:
    # all Stage 263 raw X11 samples and the saved Stage 258 xdotool bracket.
    observed = cadence.summarize(mode, guest_dir, nro)
    command = keydown.one(mode, guest_dir, nro)
    if (observed['whole_nro_sha256'] != command['whole_nro_sha256'] or
        observed['guest_submitted_render_iteration'] !=
            command['native_render_iteration'] or
        observed['guest_submitted_render_iteration'] !=
            command['host_frame_token_u16'] or
        observed['clock_domain'] != 'HOST_MONOTONIC_ONLY' or
        command['clock_domain'] != 'HOST_MONOTONIC_ONLY'):
        raise ValueError('NRO/frame/mode clock mismatch')

    start = observed['first_capture_begin_offset_us']
    last_end = observed['last_capture_end_offset_us']
    cmd_low = command['keydown_call_duration_floor_us']
    cmd_high = command['keydown_call_duration_ceil_us']
    # The original X11 log and independent keydown call bracket must
    # describe the exact same *final* positive XGetImage capture.
    sample_raw = cadence.frame.load_json(
        Path(guest_dir) / 'host-x11-sample-sequence-evidence.json')
    observed_positive_begin = sample_raw['samples'][-1]['capture_begin_offset_us']
    # Stage 258 must attest exactly the same final XGetImage call:
    # its offset is relative to the xdotool invocation, like Stage 263.
    if (last_end != command['keydown_invocation_to_x11_capture_end_us'] or
        observed_positive_begin !=
            command['keydown_invocation_to_x11_capture_start_us'] or
        not 0 <= cmd_low <= cmd_high <= 2_500_001 or
        cmd_high - cmd_low > 1 or start < cmd_low or
        observed_positive_begin > last_end):
        raise ValueError('host command and full X11 sampling disagree')

    # All saved microseconds are floor/ceil rounded from host monotonic ns.
    # start is floor(sample_start-command_start); cmd_low is floor(
    # command_complete-command_start), cmd_high is its ceil. Therefore the
    # true preceding no-XGetImage-call interval is conservatively within:
    #   [max(0, start-cmd_high), start+1-cmd_low] microseconds.
    # Do NOT call that physical input latency or first-frame onset.
    lower = max(0, start - cmd_high)
    upper = start + 1 - cmd_low
    if upper < lower:
        raise ValueError('impossible first X11 capture interval')
    return {
        'mode': mode,
        'whole_nro_sha256': observed['whole_nro_sha256'],
        'guest_submitted_render_iteration':
            observed['guest_submitted_render_iteration'],
        'x11_sample_count': observed['x11_sample_count'],
        'host_xdotool_command_duration_floor_us': cmd_low,
        'host_xdotool_command_duration_ceil_us': cmd_high,
        'first_post_command_capture_begin_offset_floor_us': start,
        'initial_unsampled_interval_conservative_lower_us': lower,
        'initial_unsampled_interval_conservative_upper_us': upper,
        'inter_call_gap_sum_rounded_us':
            observed['sum_between_capture_call_gaps_us'],
        'last_capture_end_offset_ceil_us': last_end,
        'host_first_sample_blind_interval_audited': True,
        'host_clock_domain': 'HOST_MONOTONIC_ONLY',
        'physical_input_to_first_display_latency_verified': False,
        'first_visible_frame_onset_verified': False,
        'guest_hid_delivery_timestamp_verified': False,
        'cross_mode_causal_performance_verified': False,
    }


def verify(baseline_dir, extra_dir, baseline_nro, extra_nro):
    baseline = one('baseline', baseline_dir, baseline_nro)
    extra = one('extra-poll', extra_dir, extra_nro)
    if baseline['whole_nro_sha256'] == extra['whole_nro_sha256']:
        raise ValueError('two distinct real NRO binaries required')
    return {
        'schema': SCHEMA, 'status': STATUS,
        'modes': {'baseline': baseline, 'extra-poll': extra},
        'both_nro_bound_first_sample_gaps_verified': True,
        'rounded_host_time_only': True,
        'exact_first_visible_frame_onset_verified': False,
        'physical_controller_verified': False,
        'physical_display_verified': False,
        'gpu_scanout_timestamp_verified': False,
        'actual_guest_input_delivery_timestamp_verified': False,
        'cross_mode_causal_performance_verified': False,
        'audible_speaker_latency_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-dir', 'extra-dir', 'baseline-nro', 'extra-nro', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    a = parser.parse_args(argv)
    result = verify(a.baseline_dir, a.extra_dir, a.baseline_nro, a.extra_nro)
    # A malformed/replayed/missing input never leaves a success attestation.
    with a.out.open('x', encoding='ascii') as f:
        f.write(json.dumps(result, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
