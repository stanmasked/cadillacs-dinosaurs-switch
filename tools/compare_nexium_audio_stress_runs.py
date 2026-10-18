#!/usr/bin/env python3
"""Compare already-produced, ROM-free NeXium audio metadata across guest trials.

These JSON files are NOT authenticated. This code does not run an emulator,
read game ROMs, inspect guest PCM, or establish scheduling causality.
"""
import argparse
import hashlib
import json
from pathlib import Path

STATUS = 'GUEST_900TICK_AUDOUT_FRAME_BATCH_CORRELATION_WITNESSED'
SCHEMA = 'dino-nexium-audout-900tick-v3'
WINDOW_KEYS = {
    'tick_start', 'tick_end', 'single_tick_render_steps',
    'batched_render_steps', 'skips_in_single_tick_render_frames',
    'skips_in_batched_render_frames', 'render_frames_with_batched_steps',
    'full_queue_skips', 'single_skip_percent_rounded',
    'batched_skip_percent_rounded',
}
FALSE_FLAGS = (
    'catchup_causality_verified', 'host_wall_clock_real_time_verified',
    'sound_device_audible_verified', 'physical_switch_audio_verified',
    'audio_latency_verified', 'original_arcade_audio_verified',
)
GLOBAL_COUNTS = (
    'simulation_ticks', 'checkpoints', 'pcm_generated_ticks',
    'audout_blocks_submitted', 'audout_blocks_released',
    'audout_blocks_skipped', 'full_queue_skips',
    'inactive_backend_skips', 'unexpected_slot_skips',
    'single_tick_render_steps', 'batched_render_steps',
    'skips_in_single_tick_render_frames',
    'skips_in_batched_render_frames',
    'render_frames_with_batched_steps',
    'largest_scheduled_tick_batch', 'peak_observed_pending',
    'audio_errors_added', 'windows_with_both_render_modes',
    'windows_with_higher_batched_skip_rate',
)
WINDOW_COUNTS = tuple(sorted(WINDOW_KEYS - {
    'single_skip_percent_rounded', 'batched_skip_percent_rounded',
}))


def nonnegative(value):
    if type(value) is not int or not 0 <= value <= 2**32 - 1:
        raise ValueError('invalid nonnegative counter')
    return value


def rounded(skipped, ticks):
    return (100 * skipped + ticks // 2) // ticks if ticks else None


def parse_pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError('duplicate JSON field')
        out[key] = value
    return out


def read_report(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 128 <= path.stat().st_size <= 32768:
        raise ValueError('unavailable or invalid report')
    with path.open('rb') as stream:
        raw = stream.read(32769)
    if not 128 <= len(raw) <= 32768:
        raise ValueError('invalid bounded report')
    try:
        report = json.loads(raw.decode('ascii'), object_pairs_hook=parse_pairs)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('invalid report JSON') from exc
    return raw, report


def validate(report):
    if not isinstance(report, dict) or report.get('schema') != SCHEMA or \
            report.get('status') != STATUS:
        raise ValueError('unsupported or unverified guest report')
    if report.get('native_guest_hid_bound') is not True or \
            report.get('queued_buffers_never_above_two') is not True or \
            any(report.get(flag) is not False for flag in FALSE_FLAGS):
        raise ValueError('unsupported authenticity or audibility assertions')
    totals = {key: nonnegative(report.get(key)) for key in GLOBAL_COUNTS}
    if (totals['simulation_ticks'] != 900 or totals['pcm_generated_ticks'] != 900 or
            totals['checkpoints'] != 7 or totals['audio_errors_added'] != 0 or
            totals['inactive_backend_skips'] != 0 or
            totals['unexpected_slot_skips'] != 0 or
            totals['peak_observed_pending'] > 2 or
            not 1 <= totals['largest_scheduled_tick_batch'] <= 15):
        raise ValueError('unexpected native guest audio contract')
    single = totals['single_tick_render_steps']
    batch = totals['batched_render_steps']
    single_skips = totals['skips_in_single_tick_render_frames']
    batch_skips = totals['skips_in_batched_render_frames']
    skips = totals['audout_blocks_skipped']
    submitted = totals['audout_blocks_submitted']
    released = totals['audout_blocks_released']
    if (single + batch != 900 or single_skips > single or batch_skips > batch or
            single_skips + batch_skips != skips or
            totals['full_queue_skips'] != skips or
            submitted + skips != 900 or
            released > submitted or submitted - released > 2 or
            batch > totals['render_frames_with_batched_steps'] *
                    totals['largest_scheduled_tick_batch'] or
            2 * totals['render_frames_with_batched_steps'] > batch + 2 or
            (batch > 0 and totals['largest_scheduled_tick_batch'] < 2) or
            (batch == 0 and totals['render_frames_with_batched_steps'] != 0) or
            report.get('single_skip_percent_rounded') != rounded(single_skips, single) or
            report.get('batched_skip_percent_rounded') != rounded(batch_skips, batch)):
        raise ValueError('unbalanced audio accounting')
    windows = report.get('checkpoint_mode_intervals')
    deltas = report.get('checkpoint_skipped_deltas')
    if not isinstance(windows, list) or len(windows) != 6 or \
            not isinstance(deltas, list) or len(deltas) != 6:
        raise ValueError('missing interval breakdown')
    sums = dict.fromkeys((
        'single_tick_render_steps', 'batched_render_steps',
        'skips_in_single_tick_render_frames',
        'skips_in_batched_render_frames', 'render_frames_with_batched_steps',
        'full_queue_skips',
    ), 0)
    both = higher = 0
    for idx, window in enumerate(windows):
        if not isinstance(window, dict) or set(window) != WINDOW_KEYS:
            raise ValueError('invalid window shape')
        w = {key: nonnegative(window[key]) for key in WINDOW_COUNTS}
        s, b = w['single_tick_render_steps'], w['batched_render_steps']
        ss, bs = (w['skips_in_single_tick_render_frames'],
                  w['skips_in_batched_render_frames'])
        f = w['render_frames_with_batched_steps']
        if (w['tick_start'] != idx * 150 or w['tick_end'] != (idx + 1) * 150 or
                s + b != 150 or ss > s or bs > b or
                ss + bs != w['full_queue_skips'] or
                f > b or (b > 0 and f == 0) or
                2 * f > b + (2 if idx == 0 else 1) or
                b > (f + 1) * totals['largest_scheduled_tick_batch'] or
                window['single_skip_percent_rounded'] != rounded(ss, s) or
                window['batched_skip_percent_rounded'] != rounded(bs, b) or
                nonnegative(deltas[idx]) != ss + bs):
            raise ValueError('interval counters contradict guest totals')
        for key in sums:
            sums[key] += w[key]
        if s and b:
            both += 1
            if bs * s > ss * b:
                higher += 1
    for key, actual in sums.items():
        global_key = 'full_queue_skips' if key == 'full_queue_skips' else key
        if actual != totals[global_key]:
            raise ValueError('window and global counters differ')
    if (both != totals['windows_with_both_render_modes'] or
            higher != totals['windows_with_higher_batched_skip_rate']):
        raise ValueError('window rate comparison contradicted')
    return totals, windows


def compare(paths):
    if not 2 <= len(paths) <= 8:
        raise ValueError('require two to eight individual run reports')
    seen = set()
    pool = {
        'single_steps': 0, 'batched_steps': 0,
        'single_skips': 0, 'batched_skips': 0,
        'full_queue_skips': 0,
    }
    higher = lower = tied = eligible = 0
    per_run_higher = []
    for path in paths:
        raw, report = read_report(path)
        digest = hashlib.sha256(raw).digest()
        if digest in seen:
            raise ValueError('reused identical guest report')
        seen.add(digest)
        totals, windows = validate(report)
        pool['single_steps'] += totals['single_tick_render_steps']
        pool['batched_steps'] += totals['batched_render_steps']
        pool['single_skips'] += totals['skips_in_single_tick_render_frames']
        pool['batched_skips'] += totals['skips_in_batched_render_frames']
        pool['full_queue_skips'] += totals['full_queue_skips']
        run_higher = 0
        for w in windows:
            s, b = w['single_tick_render_steps'], w['batched_render_steps']
            if not s or not b:
                continue
            eligible += 1
            diff = (w['skips_in_batched_render_frames'] * s -
                    w['skips_in_single_tick_render_frames'] * b)
            if diff > 0:
                higher += 1
                run_higher += 1
            elif diff < 0:
                lower += 1
            else:
                tied += 1
        per_run_higher.append(run_higher)
    return {
        'schema': 'dino-nexium-audout-cross-run-metadata-v1',
        'status': 'UNAUTHENTICATED_ROM_FREE_CROSS_RUN_COMPARISON',
        'reports_compared': len(paths),
        'total_guest_simulation_ticks': 900 * len(paths),
        'combined_full_queue_skips': pool['full_queue_skips'],
        'single_tick_render_steps': pool['single_steps'],
        'batched_render_steps': pool['batched_steps'],
        'single_tick_render_skips': pool['single_skips'],
        'batched_render_skips': pool['batched_skips'],
        'single_skip_percent_rounded': rounded(
            pool['single_skips'], pool['single_steps']),
        'batched_skip_percent_rounded': rounded(
            pool['batched_skips'], pool['batched_steps']),
        'eligible_150tick_mode_comparisons': eligible,
        'windows_with_higher_batched_skip_fraction': higher,
        'windows_with_lower_batched_skip_fraction': lower,
        'windows_with_equal_skip_fraction': tied,
        'runs_with_batched_higher_in_all_six_windows':
            sum(v == 6 for v in per_run_higher),
        'independent_guest_execution_authenticated': False,
        'catchup_causality_verified': False,
        'physical_switch_audio_verified': False,
        'original_arcade_audio_verified': False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, action='append', required=True)
    parser.add_argument('--out', type=Path)
    opts = parser.parse_args(argv)
    try:
        result = compare(opts.report)
    except (OSError, ValueError, OverflowError, UnicodeError, TypeError):
        result = {
            'schema': 'dino-nexium-audout-cross-run-metadata-v1',
            'status': 'INCONCLUSIVE_UNVERIFIED_CROSS_RUN_AUDIO_EVIDENCE',
            'independent_guest_execution_authenticated': False,
            'catchup_causality_verified': False,
            'physical_switch_audio_verified': False,
            'original_arcade_audio_verified': False,
        }
    line = json.dumps(result, sort_keys=True) + '\n'
    if opts.out is not None:
        opts.out.write_text(line, encoding='ascii')
    print(line, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
