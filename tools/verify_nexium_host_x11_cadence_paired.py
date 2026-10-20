#!/usr/bin/env python3
"""Stage 263: independently audit X11 *sampling coverage*, not input latency.

Revalidate Stage 262 paired real NRO-bound guest evidence and recompute
rounded XGetImage capture-call envelope widths and gaps from EVERY source
X11 sample. The gaps are periods with no XGetImage call in progress;
they are NOT bounds on first visual onset or physical LCD presentation.
"""
import argparse
import json
from pathlib import Path

if __package__:
    from tools import verify_nexium_host_x11_sample_sequence_paired as prior
    from tools import verify_nexium_host_frame_token as frame
else:
    import verify_nexium_host_x11_sample_sequence_paired as prior
    import verify_nexium_host_frame_token as frame

SCHEMA = 'dino-nexium-paired-x11-capture-cadence-v1'
STATUS = 'BOTH_REAL_NRO_BOUND_X11_CAPTURE_CADENCE_AUDITED'


def summarize(mode, guest_dir, nro):
    # This replays all real guest, audio-mode, whole NRO hash, host RGB,
    # sample sequence, ordering and saved attestation requirements.
    verified = prior.one(mode, guest_dir, nro)
    raw = frame.load_json(
        Path(guest_dir) / 'host-x11-sample-sequence-evidence.json')
    samples = raw['samples']
    if (len(samples) != verified['total_x11_images'] or
        len(samples) < 2 or len(samples) > 199 or
        len(samples) != verified['number_of_negative_images_after_host_command'] + 1):
        raise ValueError('sample count differs from mandatory paired source')

    widths = []
    gaps = []
    previous_end = None
    for entry in samples:
        start = entry['capture_begin_offset_us']
        end = entry['capture_end_offset_us']
        # Type, chronology and raw 4-RGB fields were independently
        # validated by prior.one; assert the arithmetic invariants too.
        if type(start) is not int or type(end) is not int or not 0 <= start <= end:
            raise ValueError('invalid XGetImage capture-call envelope')
        if previous_end is not None:
            if start < previous_end:
                raise ValueError('overlapping XGetImage capture-call envelopes')
            gaps.append(start - previous_end)
        widths.append(end - start)
        previous_end = end

    start = samples[0]['capture_begin_offset_us']
    end = samples[-1]['capture_end_offset_us']
    span = end - start
    if (sum(widths) + sum(gaps) != span or len(gaps) != len(samples) - 1 or
        samples[-2]['capture_end_offset_us'] !=
            verified['last_negative_host_x11_capture_us'][1] or
        samples[-1]['capture_begin_offset_us'] !=
            verified['first_positive_host_x11_capture_us'][0] or
        samples[-1]['capture_end_offset_us'] !=
            verified['first_positive_host_x11_capture_us'][1]):
        raise ValueError('capture coverage contradicts required Stage 262 proof')

    return {
        'mode': mode,
        'whole_nro_sha256': verified['nro_whole_sha256'],
        'guest_submitted_render_iteration': verified['guest_submitted_render_iteration'],
        'x11_sample_count': len(samples),
        'negative_before_counter_count': len(samples) - 1,
        'first_capture_begin_offset_us': start,
        'last_capture_end_offset_us': end,
        'total_rounded_capture_span_us': span,
        'sum_rounded_xgetimage_call_envelopes_us': sum(widths),
        'sum_between_capture_call_gaps_us': sum(gaps),
        'max_between_capture_call_gap_us': max(gaps),
        'last_negative_to_first_positive_capture_gap_us': gaps[-1],
        'all_captures_recalculated_from_raw_x11_evidence': True,
        'clock_domain': 'HOST_MONOTONIC_ONLY',
        'rounded_microsecond_envelopes_not_exact_durations': True,
        'first_visible_frame_onset_verified': False,
        'physical_controller_to_lcd_latency_verified': False,
        'cross_mode_causal_comparison_verified': False,
    }


def verify(baseline_dir, extra_dir, baseline_nro, extra_nro):
    baseline = summarize('baseline', baseline_dir, baseline_nro)
    extra = summarize('extra-poll', extra_dir, extra_nro)
    if baseline['whole_nro_sha256'] == extra['whole_nro_sha256']:
        raise ValueError('two independent NRO modes must remain distinct')
    return {
        'schema': SCHEMA, 'status': STATUS,
        'modes': {'baseline': baseline, 'extra-poll': extra},
        'both_real_guest_x11_capture_series_audited': True,
        'clock_domain': 'HOST_MONOTONIC_ONLY',
        'gaps_only_between_xgetimage_calls': True,
        'exact_first_visible_frame_onset_verified': False,
        'guest_input_delivery_timestamp_verified': False,
        'physical_controller_verified': False,
        'physical_display_verified': False,
        'gpu_scanout_timestamp_verified': False,
        'cross_mode_causal_comparison_verified': False,
        'audible_speaker_latency_verified': False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-dir', 'extra-dir', 'baseline-nro', 'extra-nro', 'out'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args(argv)
    result = verify(a.baseline_dir, a.extra_dir, a.baseline_nro, a.extra_nro)
    # Never create a fabricated success output on missing/bad evidence.
    with a.out.open('x', encoding='ascii') as output:
        output.write(json.dumps(result, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
