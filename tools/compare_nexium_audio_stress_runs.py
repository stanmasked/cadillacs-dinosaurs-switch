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
POLL_PROBE_KEYS = (
    'pre_poll_capacity_probe_present',
    'full_before_release_poll_ticks',
    'full_recovered_before_admission_ticks',
    'checkpoint_release_poll_intervals',
)
POLL_WINDOW_KEYS = {
    'tick_start', 'tick_end', 'full_before_poll',
    'recovered_before_admission', 'still_full_after_poll',
}
POSITION_FIELDS = (
    'batch_tick_position_probe_present',
    'batched_first_tick_steps', 'batched_later_tick_steps',
    'batched_first_tick_skips', 'batched_later_tick_skips',
    'checkpoint_batch_position_intervals',
)
POSITION_WINDOW_KEYS = {
    'tick_start', 'tick_end', 'first_tick_steps', 'later_tick_steps',
    'first_tick_skips', 'later_tick_skips',
    'first_skip_percent_rounded', 'later_skip_percent_rounded',
}
POSITION_POLL_FIELDS = (
    'batch_position_poll_probe_present',
    'batched_first_full_before_poll',
    'batched_first_recovered_after_poll',
    'batched_later_full_before_poll',
    'batched_later_recovered_after_poll',
    'checkpoint_batch_position_poll_intervals',
)
POSITION_POLL_WINDOW_KEYS = {
    'tick_start', 'tick_end',
    'first_full_before_poll', 'first_recovered_after_poll',
    'later_full_before_poll', 'later_recovered_after_poll',
    'single_full_before_poll', 'single_recovered_after_poll',
}
RELEASE_POSITION_FIELDS = (
    'release_tick_position_probe_present',
    'single_frame_released_pages',
    'batched_first_released_pages',
    'batched_later_released_pages',
    'checkpoint_release_position_intervals',
)
RELEASE_POSITION_WINDOW_KEYS = {
    'tick_start', 'tick_end', 'single_frame_released_pages',
    'batched_first_released_pages', 'batched_later_released_pages',
}
RELEASE_POSITION_COUNTS = RELEASE_POSITION_FIELDS[1:4]


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



def validate_release_poll_probe(report, totals, mode_windows):
    """Read Stage 143 provenance-free release-poll counters fail closed."""
    supplied=set(POLL_PROBE_KEYS).intersection(report)
    if not supplied:
        return None  # A real legacy Stage 141/142 report, not zero recovery.
    if supplied!=set(POLL_PROBE_KEYS):
        raise ValueError('partial release-poll evidence')
    declared=report['pre_poll_capacity_probe_present']
    if declared is False:
        if any(report[key] is not None for key in POLL_PROBE_KEYS[1:]):
            raise ValueError('absent release-poll probe claimed counts')
        return None
    if declared is not True:
        raise ValueError('invalid release-poll presence flag')
    before=nonnegative(report['full_before_release_poll_ticks'])
    recovered=nonnegative(report['full_recovered_before_admission_ticks'])
    still=totals['full_queue_skips']
    if before>900 or recovered>before or before-recovered!=still:
        raise ValueError('release-poll totals contradict skipped admissions')
    windows=report['checkpoint_release_poll_intervals']
    if not isinstance(windows,list) or len(windows)!=6:
        raise ValueError('missing release-poll interval sequence')
    sums_before=sums_recovered=sums_still=0
    for i,w in enumerate(windows):
        if not isinstance(w,dict) or set(w)!=POLL_WINDOW_KEYS:
            raise ValueError('invalid release-poll window fields')
        sample={k:nonnegative(v) for k,v in w.items()}
        a=sample['full_before_poll']
        b=sample['recovered_before_admission']
        c=sample['still_full_after_poll']
        if (sample['tick_start']!=i*150 or
                sample['tick_end']!=(i+1)*150 or
                a>150 or b>a or a-b!=c or
                c!=mode_windows[i]['full_queue_skips']):
            raise ValueError('release-poll window disagrees with guest skips')
        sums_before+=a
        sums_recovered+=b
        sums_still+=c
    if sums_before!=before or sums_recovered!=recovered or sums_still!=still:
        raise ValueError('release-poll window totals do not reconcile')
    return (before,recovered)



def optional_probe_state(report, keys, name):
    supplied=set(keys).intersection(report)
    if not supplied:
        return False
    if supplied!=set(keys):
        raise ValueError('partial '+name+' evidence')
    enabled=report[keys[0]]
    if enabled is False:
        if any(report[key] is not None for key in keys[1:]):
            raise ValueError('absent '+name+' claimed non-null counters')
        return False
    if enabled is not True:
        raise ValueError('invalid '+name+' presence')
    return True


def validate_batch_position_probes(report, totals, modes, release):
    """Fail closed on Stage 145/146 counters, never infer provenance."""
    has_position=optional_probe_state(
        report,POSITION_FIELDS,'batched-tick position')
    has_poll=optional_probe_state(
        report,POSITION_POLL_FIELDS,'position release poll')
    if has_poll and (not has_position or release is None):
        raise ValueError('position release poll lacks prerequisite evidence')
    if not has_position:
        return None,None
    totals_by_position={
        'first_tick_steps':nonnegative(report['batched_first_tick_steps']),
        'later_tick_steps':nonnegative(report['batched_later_tick_steps']),
        'first_tick_skips':nonnegative(report['batched_first_tick_skips']),
        'later_tick_skips':nonnegative(report['batched_later_tick_skips']),
    }
    a=totals_by_position
    if (a['first_tick_steps']+a['later_tick_steps']!=
            totals['batched_render_steps'] or
            a['first_tick_skips']+a['later_tick_skips']!=
            totals['skips_in_batched_render_frames'] or
            a['first_tick_skips']>a['first_tick_steps'] or
            a['later_tick_skips']>a['later_tick_steps'] or
            abs(a['first_tick_steps']-
                totals['render_frames_with_batched_steps'])>1):
        raise ValueError('batched-tick position totals inconsistent')
    pos_windows=report['checkpoint_batch_position_intervals']
    if not isinstance(pos_windows,list) or len(pos_windows)!=6:
        raise ValueError('incomplete batch-position windows')
    sums=dict.fromkeys(a,0)
    for i,(w,mode) in enumerate(zip(pos_windows,modes)):
        if not isinstance(w,dict) or set(w)!=POSITION_WINDOW_KEYS:
            raise ValueError('invalid batch-position window fields')
        sample={key:nonnegative(w[key]) for key in sums}
        first=sample['first_tick_steps']
        later=sample['later_tick_steps']
        first_drop=sample['first_tick_skips']
        later_drop=sample['later_tick_skips']
        if (nonnegative(w['tick_start'])!=i*150 or
                nonnegative(w['tick_end'])!=(i+1)*150 or
                first+later!=mode['batched_render_steps'] or
                first_drop+later_drop!=
                    mode['skips_in_batched_render_frames'] or
                first_drop>first or later_drop>later or
                abs(first-mode['render_frames_with_batched_steps'])>1 or
                w['first_skip_percent_rounded']!=
                    rounded(first_drop,first) or
                w['later_skip_percent_rounded']!=
                    rounded(later_drop,later)):
            raise ValueError('batch-position window contradicts mode')
        for key in sums:
            sums[key]+=sample[key]
    if sums!=a:
        raise ValueError('batch-position windows do not sum to totals')
    if not has_poll:
        return a,None

    poll_windows=report['checkpoint_batch_position_poll_intervals']
    if not isinstance(poll_windows,list) or len(poll_windows)!=6:
        raise ValueError('incomplete position release-poll windows')
    fields=(
        'batched_first_full_before_poll',
        'batched_first_recovered_after_poll',
        'batched_later_full_before_poll',
        'batched_later_recovered_after_poll',
    )
    b={key:nonnegative(report[key]) for key in fields}
    if (b[fields[0]]-b[fields[1]]!=a['first_tick_skips'] or
            b[fields[2]]-b[fields[3]]!=a['later_tick_skips'] or
            b[fields[0]]>a['first_tick_steps'] or
            b[fields[2]]>a['later_tick_steps'] or
            b[fields[1]]>b[fields[0]] or
            b[fields[3]]>b[fields[2]]):
        raise ValueError('batch-position release-poll totals invalid')
    sums_poll=dict.fromkeys(fields,0)
    for i,(w,mode,pos) in enumerate(zip(poll_windows,modes,pos_windows)):
        if not isinstance(w,dict) or set(w)!=POSITION_POLL_WINDOW_KEYS:
            raise ValueError('invalid position release-poll window fields')
        values={key:nonnegative(v) for key,v in w.items()}
        ff=values['first_full_before_poll']
        fr=values['first_recovered_after_poll']
        lf=values['later_full_before_poll']
        lr=values['later_recovered_after_poll']
        sf=values['single_full_before_poll']
        sr=values['single_recovered_after_poll']
        if (values['tick_start']!=i*150 or
                values['tick_end']!=(i+1)*150 or
                ff>pos['first_tick_steps'] or
                lf>pos['later_tick_steps'] or
                sf>mode['single_tick_render_steps'] or
                ff-fr!=pos['first_tick_skips'] or
                lf-lr!=pos['later_tick_skips'] or
                sf-sr!=mode['skips_in_single_tick_render_frames'] or
                (ff+lf+sf)!=
                    report['checkpoint_release_poll_intervals'][i]
                          ['full_before_poll'] or
                (fr+lr+sr)!=
                    report['checkpoint_release_poll_intervals'][i]
                          ['recovered_before_admission']):
            raise ValueError('release-poll subgroups contradict window')
        for key,subgroup in zip(
                fields,
                ('first_full_before_poll',
                 'first_recovered_after_poll',
                 'later_full_before_poll',
                 'later_recovered_after_poll')):
            sums_poll[key]+=values[subgroup]
    if sums_poll!=b:
        raise ValueError('position release-poll window totals mismatch')
    if (b[fields[0]]+b[fields[2]]>release[0] or
            b[fields[1]]+b[fields[3]]>release[1]):
        raise ValueError('position recovery exceeds total release polling')
    return a,b



def validate_released_page_positions(report, totals, modes,
                                     release_probe, positions, position_poll):
    """Bound and reconcile Stage 151 release ACKs; no timing inference."""
    enabled=optional_probe_state(
        report, RELEASE_POSITION_FIELDS, 'release-position')
    if not enabled:
        return None
    if release_probe is None or positions is None or position_poll is None:
        raise ValueError('release-position witness lacks prior accounting')
    result={key:nonnegative(report[key]) for key in RELEASE_POSITION_COUNTS}
    if (sum(result.values())!=totals['audout_blocks_released'] or
            result['single_frame_released_pages']>
                2*totals['single_tick_render_steps'] or
            result['batched_first_released_pages']>
                2*positions['first_tick_steps'] or
            result['batched_later_released_pages']>
                2*positions['later_tick_steps'] or
            result['batched_first_released_pages']<
                position_poll['batched_first_recovered_after_poll'] or
            result['batched_later_released_pages']<
                position_poll['batched_later_recovered_after_poll'] or
            result['single_frame_released_pages']<
                release_probe[1]-
                position_poll['batched_first_recovered_after_poll']-
                position_poll['batched_later_recovered_after_poll']):
        raise ValueError('released page position counts impossible')
    windows=report['checkpoint_release_position_intervals']
    if not isinstance(windows,list) or len(windows)!=6:
        raise ValueError('incomplete released-page position intervals')
    sums=dict.fromkeys(RELEASE_POSITION_COUNTS,0)
    for idx,(w,mode) in enumerate(zip(windows,modes)):
        if not isinstance(w,dict) or set(w)!=RELEASE_POSITION_WINDOW_KEYS:
            raise ValueError('malformed released-page position window')
        values={key:nonnegative(value) for key,value in w.items()}
        single=values['single_frame_released_pages']
        first=values['batched_first_released_pages']
        later=values['batched_later_released_pages']
        previous=report['checkpoint_batch_position_intervals'][idx]
        poll=report['checkpoint_batch_position_poll_intervals'][idx]
        total_poll=report['checkpoint_release_poll_intervals'][idx]
        minimum_single=(total_poll['recovered_before_admission']-
                        poll['first_recovered_after_poll']-
                        poll['later_recovered_after_poll'])
        if (values['tick_start']!=150*idx or
                values['tick_end']!=150*(idx+1) or
                single>2*mode['single_tick_render_steps'] or
                first>2*previous['first_tick_steps'] or
                later>2*previous['later_tick_steps'] or
                single<minimum_single or
                first<poll['first_recovered_after_poll'] or
                later<poll['later_recovered_after_poll'] or
                single+first+later>150+2):
            # At most two pages were pending at the beginning of a
            # 150-tick interval; at most one fresh page per tick.
            raise ValueError('release-position window contradicts queue')
        for key in sums:
            sums[key]+=values[key]
    if sums!=result:
        raise ValueError('released-page windows disagree with totals')
    return result


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
    probe=validate_release_poll_probe(report,totals,windows)
    positions,position_poll=validate_batch_position_probes(
        report,totals,windows,probe)
    released_by_tick=validate_released_page_positions(
        report,totals,windows,probe,positions,position_poll)
    return totals,windows,probe,positions,position_poll,released_by_tick


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
    probed_runs=0
    probed_full=probed_recovered=0
    positioned=position_polled=0
    p_first=p_later=p_first_skips=p_later_skips=0
    pp_first_full=pp_first_recovered=0
    pp_later_full=pp_later_recovered=0
    release_positioned=0
    released_sums=dict.fromkeys(RELEASE_POSITION_COUNTS,0)
    for path in paths:
        raw, report = read_report(path)
        digest = hashlib.sha256(raw).digest()
        if digest in seen:
            raise ValueError('reused identical guest report')
        seen.add(digest)
        totals, windows, probe, positions, position_poll, released_by_tick = (
            validate(report))
        if released_by_tick is not None:
            release_positioned+=1
            for key in released_sums:
                released_sums[key]+=released_by_tick[key]
        if positions is not None:
            positioned+=1
            p_first+=positions['first_tick_steps']
            p_later+=positions['later_tick_steps']
            p_first_skips+=positions['first_tick_skips']
            p_later_skips+=positions['later_tick_skips']
        if position_poll is not None:
            position_polled+=1
            pp_first_full+=position_poll['batched_first_full_before_poll']
            pp_first_recovered+=position_poll[
                'batched_first_recovered_after_poll']
            pp_later_full+=position_poll['batched_later_full_before_poll']
            pp_later_recovered+=position_poll[
                'batched_later_recovered_after_poll']
        if probe is not None:
            probed_runs+=1
            probed_full+=probe[0]
            probed_recovered+=probe[1]
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
        'reports_with_release_tick_position_probe':release_positioned,
        'all_reports_have_release_tick_position_probe':
            release_positioned==len(paths),
        'pooled_single_frame_released_pages':(
            released_sums['single_frame_released_pages']
            if release_positioned==len(paths) else None),
        'pooled_batched_first_released_pages':(
            released_sums['batched_first_released_pages']
            if release_positioned==len(paths) else None),
        'pooled_batched_later_released_pages':(
            released_sums['batched_later_released_pages']
            if release_positioned==len(paths) else None),
        'batched_later_release_pages_per_100_ticks_rounded':(
            rounded(released_sums['batched_later_released_pages'],p_later)
            if release_positioned==len(paths) else None),
        'reports_with_batch_position_probe':positioned,
        'all_reports_have_batch_position_probe':positioned==len(paths),
        'pooled_batched_first_tick_steps':(
            p_first if positioned==len(paths) else None),
        'pooled_batched_later_tick_steps':(
            p_later if positioned==len(paths) else None),
        'pooled_batched_first_tick_skips':(
            p_first_skips if positioned==len(paths) else None),
        'pooled_batched_later_tick_skips':(
            p_later_skips if positioned==len(paths) else None),
        'batched_first_skip_percent_rounded':(
            rounded(p_first_skips,p_first)
            if positioned==len(paths) else None),
        'batched_later_skip_percent_rounded':(
            rounded(p_later_skips,p_later)
            if positioned==len(paths) else None),
        'reports_with_batch_position_poll_probe':position_polled,
        'all_reports_have_batch_position_poll_probe':
            position_polled==len(paths),
        'pooled_batched_first_full_before_poll':(
            pp_first_full if position_polled==len(paths) else None),
        'pooled_batched_first_recovered_after_poll':(
            pp_first_recovered if position_polled==len(paths) else None),
        'pooled_batched_later_full_before_poll':(
            pp_later_full if position_polled==len(paths) else None),
        'pooled_batched_later_recovered_after_poll':(
            pp_later_recovered if position_polled==len(paths) else None),
        'reports_with_release_poll_probe':probed_runs,
        'all_reports_have_release_poll_probe':probed_runs==len(paths),
        # Mixed or legacy inputs get NULL rather than misleading partial
        # recovery rates; their per-run reports remain valid as legacy.
        'pooled_full_before_release_poll_ticks':(
            probed_full if probed_runs==len(paths) else None),
        'pooled_recovered_before_admission_ticks':(
            probed_recovered if probed_runs==len(paths) else None),
        'pooled_still_full_after_poll_ticks':(
            pool['full_queue_skips'] if probed_runs==len(paths) else None),
        'release_poll_recovery_percent_rounded':(
            rounded(probed_recovered,probed_full)
            if probed_runs==len(paths) else None),
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
