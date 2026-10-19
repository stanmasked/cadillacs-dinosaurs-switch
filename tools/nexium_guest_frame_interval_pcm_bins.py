#!/usr/bin/env python3
"""ROM-free descriptive relationship: capped render intervals vs PCM skips.

Stage 216's frame-clock rows have one already-clamped elapsed interval per
render iteration. Join only authenticated simulation ticks in the same frame;
frames with zero game ticks never become extra PCM attempts. An interval is
between guest scheduler-clock reads, NOT presentation time, audio-service
release time, host A/B matching or physical speaker latency.
"""
import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = 'dino-guest-capped-frame-interval-pcm-exposure-v1'
THRESHOLD_NS = 20_000_000
BINS = ('below_15ms', '15_to_below_20ms', '20_to_below_25ms', '25ms_and_above')
STEP_GROUPS = ('zero', 'one', 'multiple')
MAX_ROWS = 4096


def interval_bin(ns):
    if type(ns) is not int or not 0 <= ns <= 250_000_000:
        raise ValueError('invalid capped render-loop interval')
    if ns < 15_000_000:
        return BINS[0]
    if ns < 20_000_000:
        return BINS[1]
    if ns < 25_000_000:
        return BINS[2]
    return BINS[3]


def new_cell():
    return {'render_iterations': 0, 'full_game_ticks': 0,
            'measured_game_ticks': 0, 'pcm_skipped': 0,
            'pcm_submitted': 0, 'ack_discovery_ticks': 0,
            'ack_pages': 0}


def add(cell, frame, samples):
    cell['render_iterations'] += 1
    cell['full_game_ticks'] += frame['frame_game_ticks']
    cell['measured_game_ticks'] += len(samples)
    cell['pcm_skipped'] += sum(x['skipped'] for x in samples)
    cell['pcm_submitted'] += sum(x['submitted'] for x in samples)
    cell['ack_discovery_ticks'] += sum(x['released'] > 0 for x in samples)
    cell['ack_pages'] += sum(x['released'] for x in samples)


def with_fraction(cell):
    result = dict(cell)
    n = cell['measured_game_ticks']
    result['pcm_skip_rate_per_measured_game_tick'] = (
        {'numerator': cell['pcm_skipped'], 'denominator': n} if n else None)
    return result


def summarize(frames, guest):
    """Strict 900-guest-tick data join. No statistical/causal imputation."""
    if (type(frames) is not list or not 1 <= len(frames) <= MAX_ROWS or
            type(guest) is not list or len(guest) != 900):
        raise ValueError('require exact guest tick trace and bounded frames')
    by_interval = {b: new_cell() for b in BINS}
    by_step_class = {s: new_cell() for s in STEP_GROUPS}
    crossed = {b: {s: new_cell() for s in STEP_GROUPS} for b in BINS}
    long_runs = 0
    max_long_run = 0
    running_long = 0
    total = 0
    previous_id = None
    partial = 0
    clamped = 0
    for i, frame in enumerate(frames):
        if (type(frame) is not dict or set(frame) != {
                'frame_id', 'elapsed_ns_capped', 'frame_game_ticks',
                'stress_game_ticks'} or
            any(type(value) is not int for value in frame.values())):
            raise ValueError('malformed frame clock evidence')
        ident, ns, steps, count = (
            frame['frame_id'], frame['elapsed_ns_capped'],
            frame['frame_game_ticks'], frame['stress_game_ticks'])
        if (not 1 <= ident <= 0xffffffff or
            (previous_id is not None and ident != previous_id + 1) or
            not 0 <= steps <= 15 or not 0 <= count <= steps or
            count > 900 - total):
            raise ValueError('invalid scheduler frame/tick conservation')
        previous_id = ident
        if i not in (0, len(frames) - 1) and count != steps:
            raise ValueError('unobserved interior simulation ticks')
        if count < steps:
            partial += 1
        if ns == 250_000_000:
            clamped += 1
        b = interval_bin(ns)
        s = 'zero' if steps == 0 else ('one' if steps == 1 else 'multiple')
        sample = guest[total:total + count]
        first_position = steps - count if i == 0 else 0
        for index, a in enumerate(sample):
            if (type(a) is not dict or
                any(type(a.get(key)) is not int for key in
                    ('frame_id', 'batch_size', 'batch_position',
                     'released', 'submitted', 'skipped')) or
                (a['frame_id'], a['batch_size'], a['batch_position']) !=
                    (ident, steps, first_position + index) or
                not 0 <= a['released'] <= 2 or
                a['submitted'] not in (0, 1) or
                a['skipped'] not in (0, 1) or
                a['submitted'] + a['skipped'] != 1):
                raise ValueError('guest ACK ticks do not belong to frame')
        total += count
        for cell in (by_interval[b], by_step_class[s], crossed[b][s]):
            add(cell, frame, sample)
        if ns >= THRESHOLD_NS:
            if running_long == 0:
                long_runs += 1
            running_long += 1
            max_long_run = max(max_long_run, running_long)
        else:
            running_long = 0
    if total != 900:
        raise ValueError('guest frame clock not covering 900 ticks')
    aggregated = new_cell()
    for cell in by_interval.values():
        for key in aggregated:
            aggregated[key] += cell[key]
    if (aggregated['measured_game_ticks'] != 900 or
        aggregated['pcm_submitted'] + aggregated['pcm_skipped'] != 900 or
        aggregated['render_iterations'] != len(frames)):
        raise ValueError('guest PCM render exposures did not conserve')
    for key in aggregated:
        if sum(cell[key] for cell in by_step_class.values()) != aggregated[key]:
            raise ValueError('frame-batch stratum exposure mismatch')
    for b in BINS:
        for key in aggregated:
            if sum(crossed[b][s][key] for s in STEP_GROUPS) != by_interval[b][key]:
                raise ValueError('frame duration and batching cross-tab mismatch')
    ge20 = new_cell()
    lt20 = new_cell()
    for b in BINS:
        target = lt20 if b in BINS[:2] else ge20
        for key, value in by_interval[b].items():
            target[key] += value
    return {
        'schema': SCHEMA,
        'status': 'GUEST_FRAME_INTERVAL_PCM_EXPOSURES_RECONCILED_NONCAUSAL',
        'measured_900_game_ticks': total,
        'total': with_fraction(aggregated),
        'by_existing_capped_frame_interval': {b: with_fraction(by_interval[b])
                                               for b in BINS},
        'by_declared_game_steps_per_render_iteration': {
            s: with_fraction(by_step_class[s]) for s in STEP_GROUPS},
        'by_interval_and_game_steps': {
            b: {s: with_fraction(crossed[b][s]) for s in STEP_GROUPS}
            for b in BINS},
        'below_20ms': with_fraction(lt20),
        'at_least_20ms': with_fraction(ge20),
        'render_intervals_at_existing_250ms_cap': clamped,
        'render_interval_runs_at_least_20ms': long_runs,
        'longest_render_interval_run_at_least_20ms': max_long_run,
        'boundary_frames_with_unobserved_game_steps': partial,
        'zero_game_step_frames_not_converted_into_pcm_events': True,
        'rates_have_null_denominator_on_empty_exposure': True,
        'within_batch_comparison_causal': False,
        'frame_interval_is_between_guest_loop_clock_reads': True,
        'physical_switch_speaker_latency_verified': False,
    }


def make_report(base_clock, base_trace, base_report, base_binding, base_nro,
                extra_clock, extra_trace, extra_report, extra_binding,
                extra_nro):
    if any(not Path(path).is_file() for path in (
        base_clock, base_trace, base_report, base_binding, base_nro,
        extra_clock, extra_trace, extra_report, extra_binding, extra_nro,
    )):
        raise ValueError('missing source files for bound real-guest PCM bins')
    try:
        from tools import verify_nexium_guest_frame_clock as witness
        from tools import verify_nexium_audio_ack_tick_trace as ack
        from tools import nexium_guest_clock_phase_invariant as phase
    except ImportError:
        import verify_nexium_guest_frame_clock as witness
        import verify_nexium_audio_ack_tick_trace as ack
        import nexium_guest_clock_phase_invariant as phase
    attested = witness.make_report(
        base_clock, base_trace, base_report, base_binding, base_nro,
        extra_clock, extra_trace, extra_report, extra_binding, extra_nro)
    profiles = []
    for mode, clock, trace, original in (
        ('baseline', base_clock, base_trace, attested['profiles'][0]),
        ('extra-poll', extra_clock, extra_trace, attested['profiles'][1]),
    ):
        raw_clock, frames = witness.read_clock(clock)
        raw_guest, guests = ack.parse_csv(trace)
        if (hashlib.sha256(raw_clock).hexdigest() !=
                original['guest_clock_sha256'] or
            hashlib.sha256(raw_guest).hexdigest() !=
                original['guest_ack_csv_sha256']):
            raise ValueError('guest CSV digest changed since NRO attestation')
        phase_result = phase.verify_phase(frames)
        if phase_result['observed_stress_game_ticks'] != 900:
            raise ValueError('guest clock has no valid 900-tick 60Hz phase')
        data = summarize(frames, guests)
        if (data['total']['pcm_skipped'] + data['total']['pcm_submitted'] != 900 or
            data['total']['ack_pages'] != sum(r['released'] for r in guests) or
            data['total']['render_iterations'] != original['frame_rows']):
            raise ValueError('interval/skip profile contradicted guest attestation')
        profiles.append({
            'mode': mode,
            'guest_clock_sha256': original['guest_clock_sha256'],
            'guest_ack_csv_sha256': original['guest_ack_csv_sha256'],
            'guest_nro_sha256': original['bound_guest_nro_sha256'],
            **data,
        })
    return {
        'schema': SCHEMA,
        'status': 'BOTH_NRO_BOUND_RENDER_INTERVAL_PCM_BINS_NONCAUSAL',
        'profiles': profiles,
        'causal_audio_mode_effect_verified': False,
        'identical_host_conditions_verified': False,
        'physical_switch_audio_latency_verified': False,
        'production_frame_scheduler_modified': False,
        'production_audio_queue_modified': False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('baseline-clock', 'baseline-trace', 'baseline-report',
                'baseline-binding', 'baseline-nro', 'experimental-clock',
                'experimental-trace', 'experimental-report',
                'experimental-binding', 'experimental-nro'):
        p.add_argument('--' + key, required=True, type=Path)
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args(argv)
    try:
        result = make_report(
            a.baseline_clock, a.baseline_trace, a.baseline_report,
            a.baseline_binding, a.baseline_nro, a.experimental_clock,
            a.experimental_trace, a.experimental_report,
            a.experimental_binding, a.experimental_nro)
        with a.out.open('x', encoding='ascii') as stream:
            stream.write(json.dumps(result, sort_keys=True) + '\n')
    except (OSError, ValueError, KeyError, TypeError, OverflowError,
            UnicodeError) as exc:
        print(json.dumps({
            'status': 'INCONCLUSIVE_GUEST_INTERVAL_PCM_BINS',
            'reason': type(exc).__name__,
            'causal_audio_mode_effect_verified': False,
        }, sort_keys=True))
        return 1
    print(json.dumps({
        'status': result['status'],
        'baseline_pcm_skips': result['profiles'][0]['total']['pcm_skipped'],
        'extra_pcm_skips': result['profiles'][1]['total']['pcm_skipped'],
        'causal_audio_mode_effect_verified': False,
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
