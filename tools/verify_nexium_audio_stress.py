#!/usr/bin/env python3
"""Check real guest-owned 900-tick libnx audout queue diagnostics.

This file MUST be obtained from the separate NeXium ARM64 NRO execution.
Synthetic fixtures only test this parser and never prove an emulator run.
Queue accounting is not delivery to a human or physical speaker.
"""
import argparse
import csv
import json
from pathlib import Path
import re

if __package__:
    from tools import verify_nexium_hid_timeline as timeline
else:
    import verify_nexium_hid_timeline as timeline

COLUMNS = [
    'event','elapsed_ticks','arena_ticks','audio_ticks','pcm_ticks',
    'active','queue_valid','pending','submitted','released','skipped',
    'audio_errors','pcm_fnv64','full_queue_skips',
    'inactive_backend_skips','unexpected_slot_skips',
    'max_consecutive_skips',
    'single_frame_ticks','batched_frame_ticks',
    'single_frame_skips','batched_frame_skips',
    'batched_render_frames','max_ticks_per_render_frame',
    'pre_poll_full_steps','pre_poll_recovered_steps',
    'batched_first_tick_steps','batched_later_tick_steps',
    'batched_first_tick_skips','batched_later_tick_skips',
]
STAGE143_COLUMNS=COLUMNS[:-4]
LEGACY_COLUMNS=STAGE143_COLUMNS[:-2]
CHECKPOINTS = [0,150,300,450,600,750,900]
EVENTS = ['START'] + ['CHECKPOINT']*5 + ['STRESS_DONE']
HEX16 = re.compile(r'[0-9A-F]{16}\Z')


def verify(path, guest_timeline, guest_controller):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('guest stress trace unavailable')
    if not 128 <= path.stat().st_size <= 4096:
        raise ValueError('invalid guest stress report length')
    try:
        with path.open('r',encoding='ascii',newline='') as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames not in (COLUMNS,STAGE143_COLUMNS,
                                            LEGACY_COLUMNS):
                raise ValueError('guest stress field schema mismatch')
            has_pre_poll_probe=reader.fieldnames!=LEGACY_COLUMNS
            has_batch_position_probe=reader.fieldnames==COLUMNS
            active_columns=reader.fieldnames
            rows=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise ValueError('bad guest stress CSV') from exc
    if len(rows)!=7 or [r['event'] for r in rows]!=EVENTS:
        raise ValueError('guest stress checkpoints incomplete')
    measurements=[]
    for row in rows:
        if None in row or any(key is None or value is None
                              for key,value in row.items()):
            raise ValueError('unexpected guest stress column')
        if not HEX16.fullmatch(row['pcm_fnv64']):
            raise ValueError('guest stress PCM witness malformed')
        # The PCM hex digest separates standard counters from classified
        # skip reasons. Keep both sets strictly decimal/canonical.
        values=[row[key] for key in active_columns[1:12]+active_columns[13:]]
        if any(not v.isascii() or not v.isdecimal() or
               (len(v)>1 and v.startswith('0')) for v in values):
            raise ValueError('noncanonical stress counter')
        fields=[int(v) for v in values]
        if any(n<0 or n>2**32-1 for n in fields):
            raise ValueError('out of range guest stress counter')
        measurements.append(fields)
    start=measurements[0]
    # elapsed, arena, audio ticks, PCM ticks, active, valid, pending,
    # submitted, released, skipped, errors, full, inactive, unexpected,
    # max_streak, single_ticks, batched_ticks, single_skips,
    # batched_skips, batched_frames, max_scheduled_tick_batch,
    # optional pre_poll_full_steps, pre_poll_recovered_steps
    if start[0]!=0 or start[4:6]!=[1,1] or start[6]>2 or (
            start[7]-start[8]!=start[6]) or start[10]!=0:
        raise ValueError('native audout baseline not healthy')
    if sum(start[11:14])!=start[9] or start[14]>start[9]:
        raise ValueError('starting skip classification not balanced')
    if start[15:21]!=[0]*6:
        raise ValueError('render batch correlation must start at zero')
    if has_pre_poll_probe and (
            start[22]>start[21] or
            start[21]-start[22]!=start[11]):
        raise ValueError('starting release-poll counters inconsistent')
    if has_batch_position_probe and start[23:]!=[0]*4:
        raise ValueError('batch position witness starts nonzero')
    if start[1]<1 or start[2]<1 or start[3]<1:
        raise ValueError('guest never advanced before stress started')
    prev=start
    for idx,row in enumerate(measurements):
        elapsed=CHECKPOINTS[idx]
        if (row[0]!=elapsed or row[1]!=start[1]+elapsed or
                row[2]!=start[2]+elapsed or row[3]!=start[3]+elapsed):
            raise ValueError('simulation / PCM clock divergence')
        if row[4:6]!=[1,1] or row[6]>2 or row[10]!=start[10]:
            raise ValueError('audio service error or invalid queue')
        if (row[7]<prev[7] or row[8]<prev[8] or row[9]<prev[9] or
                row[8]>row[7] or row[7]-row[8]!=row[6]):
            raise ValueError('released buffers or queue counters inconsistent')
        if (row[7]-start[7])+(row[9]-start[9])!=elapsed:
            raise ValueError('missing synthetic audio tick admission')
        if (sum(row[11:14])!=row[9] or
                any(row[j]<prev[j] for j in (11,12,13,14)) or
                row[14]>row[9] or
                (row[9] and row[14]==0)):
            raise ValueError('skip reason or streak accounting mismatch')
        if has_pre_poll_probe and (
                row[21]<prev[21] or row[22]<prev[22] or
                row[22]>row[21] or row[21]-row[22]!=row[11] or
                row[21]-start[21]>elapsed or
                row[22]-start[22]>elapsed):
            raise ValueError('release polling / full queue count mismatch')
        if has_batch_position_probe and (
                any(row[k]<prev[k] for k in range(23,27)) or
                row[23]+row[24]!=row[16] or
                row[25]+row[26]!=row[18] or
                row[25]>row[23] or row[26]>row[24] or
                row[23]>row[19] or row[19]-row[23]>1):
            raise ValueError('batched tick position attribution mismatch')
        if idx>0 and row[14]<prev[14]:
            raise ValueError('maximum consecutive skip streak decreased')
        # Backend remained active at all checkpoints. A transient
        # inactive/unexpected-slot skip remains a failed stress run.
        if row[12]!=start[12] or row[13]!=start[13]:
            raise ValueError('stopped backend or unexpected page starvation')
        if (row[15]+row[16]!=elapsed or
                row[17]+row[18]!=row[9]-start[9] or
                row[17]>row[15] or row[18]>row[16] or
                row[19]>row[16] or row[20]>15 or
                (row[16]>0 and (row[20]<2 or row[19]==0)) or
                (row[16]==0 and row[19]!=0) or
                # Only the START and current checkpoint can cut a
                # scheduled >=2-tick render batch in half. Therefore
                # at most two measured frames may contribute one
                # batched tick each; all other frames contribute >=2.
                (row[19]*2>row[16]+2) or
                # Conversely no measured frame can contribute more
                # ticks than the largest guest-scheduled render batch.
                (row[16]>row[19]*row[20]) or
                (elapsed>0 and row[20]==0) or
                any(row[j]<prev[j] for j in range(15,21))):
            raise ValueError('render scheduling / skipped admission mismatch')
        if idx>0:
            if row[7]<=prev[7]:
                raise ValueError('guest audout queue completely stalled')
            if rows[idx]['pcm_fnv64']==rows[idx-1]['pcm_fnv64']:
                raise ValueError('guest PCM synthesis witness was frozen')
        prev=row
    # Check each 150-tick interval separately. A plausible cumulative
    # partition can conceal an impossible single-interval admission.
    # A batched render frame may straddle a checkpoint: at most one
    # already-counted frame contributes steps without incrementing F.
    # At START, a frame may already be in progress, so both edges of the
    # first interval allow one incomplete frame each.
    intervals=[]
    poll_windows=[]
    position_windows=[]
    for idx in range(1,len(measurements)):
        before=measurements[idx-1]
        after=measurements[idx]
        single_ticks=after[15]-before[15]
        batched_ticks=after[16]-before[16]
        single_skips=after[17]-before[17]
        batched_skips=after[18]-before[18]
        batched_frames=after[19]-before[19]
        max_batch=after[20]
        interval_skips=after[9]-before[9]
        if (single_ticks+batched_ticks!=150 or
                single_skips+batched_skips!=interval_skips or
                single_skips>single_ticks or
                batched_skips>batched_ticks or
                batched_frames>batched_ticks or
                batched_ticks>(batched_frames+1)*max_batch or
                2*batched_frames>batched_ticks+(2 if idx==1 else 1)):
            raise ValueError('guest audout interval attribution inconsistent')
        if has_pre_poll_probe:
            polled_full=after[21]-before[21]
            recovered=after[22]-before[22]
            full_skips=after[11]-before[11]
            if recovered>polled_full or polled_full-recovered!=full_skips:
                raise ValueError('interval release poll accounting mismatch')
            poll_windows.append({
                'tick_start':CHECKPOINTS[idx-1],
                'tick_end':CHECKPOINTS[idx],
                'full_before_poll':polled_full,
                'recovered_before_admission':recovered,
                'still_full_after_poll':full_skips,
            })
        if has_batch_position_probe:
            first=after[23]-before[23]
            later=after[24]-before[24]
            first_skips=after[25]-before[25]
            later_skips=after[26]-before[26]
            if (first+later!=batched_ticks or
                    first_skips+later_skips!=batched_skips or
                    first_skips>first or later_skips>later or
                    abs(first-batched_frames)>1):
                raise ValueError('batched position interval mismatch')
            position_windows.append({
                'tick_start':CHECKPOINTS[idx-1],
                'tick_end':CHECKPOINTS[idx],
                'first_tick_steps':first,'later_tick_steps':later,
                'first_tick_skips':first_skips,'later_tick_skips':later_skips,
                'first_skip_percent_rounded':(
                    (100*first_skips+first//2)//first if first else None),
                'later_skip_percent_rounded':(
                    (100*later_skips+later//2)//later if later else None),
            })
        intervals.append({
            'tick_start':CHECKPOINTS[idx-1],
            'tick_end':CHECKPOINTS[idx],
            'single_tick_render_steps':single_ticks,
            'batched_render_steps':batched_ticks,
            'skips_in_single_tick_render_frames':single_skips,
            'skips_in_batched_render_frames':batched_skips,
            'render_frames_with_batched_steps':batched_frames,
            'full_queue_skips':after[11]-before[11],
            'single_skip_percent_rounded':(
                (100*single_skips+single_ticks//2)//single_ticks
                if single_ticks else None),
            'batched_skip_percent_rounded':(
                (100*batched_skips+batched_ticks//2)//batched_ticks
                if batched_ticks else None),
        })
    guest=timeline.verify(guest_timeline,guest_controller)
    if guest['status']!='GUEST_HID_ORDER_WITNESSED':
        raise ValueError('native HID spar sequence not witnessed')
    submitted=measurements[-1][7]-start[7]
    released=measurements[-1][8]-start[8]
    skipped=measurements[-1][9]-start[9]
    full=measurements[-1][11]-start[11]
    inactive=measurements[-1][12]-start[12]
    unexpected=measurements[-1][13]-start[13]
    if full+inactive+unexpected!=skipped:
        raise ValueError('stress skip reason totals inconsistent')
    single_ticks=measurements[-1][15]
    batched_ticks=measurements[-1][16]
    single_skips=measurements[-1][17]
    batched_skips=measurements[-1][18]
    if single_ticks+batched_ticks!=900 or single_skips+batched_skips!=skipped:
        raise ValueError('unattributed guest audio ticks or skips')
    return {
        'schema':'dino-nexium-audout-900tick-v3',
        'status':'GUEST_900TICK_AUDOUT_FRAME_BATCH_CORRELATION_WITNESSED',
        'simulation_ticks':900,
        'checkpoints':7,
        'native_guest_hid_bound':True,
        'pcm_generated_ticks':900,
        'audout_blocks_submitted':submitted,
        'audout_blocks_released':released,
        'audout_blocks_skipped':skipped,
        'full_queue_skips':full,
        'inactive_backend_skips':inactive,
        'unexpected_slot_skips':unexpected,
        'max_skip_streak_since_audio_open':measurements[-1][14],
        'single_tick_render_steps':single_ticks,
        'batched_render_steps':batched_ticks,
        'skips_in_single_tick_render_frames':single_skips,
        'skips_in_batched_render_frames':batched_skips,
        'render_frames_with_batched_steps':measurements[-1][19],
        'largest_scheduled_tick_batch':measurements[-1][20],
        'batched_skip_percent_rounded':(
            (100*batched_skips+batched_ticks//2)//batched_ticks
            if batched_ticks else None),
        'single_skip_percent_rounded':(
            (100*single_skips+single_ticks//2)//single_ticks
            if single_ticks else None),
        'catchup_causality_verified':False,
        'host_wall_clock_real_time_verified':False,
        'checkpoint_skipped_deltas':[
            measurements[i][9]-measurements[i-1][9]
            for i in range(1,len(measurements))
        ],
        'checkpoint_mode_intervals':intervals,
        'pre_poll_capacity_probe_present':has_pre_poll_probe,
        'full_before_release_poll_ticks':(
            measurements[-1][21]-start[21] if has_pre_poll_probe else None),
        'full_recovered_before_admission_ticks':(
            measurements[-1][22]-start[22] if has_pre_poll_probe else None),
        'checkpoint_release_poll_intervals':(
            poll_windows if has_pre_poll_probe else None),
        'batch_tick_position_probe_present':has_batch_position_probe,
        'batched_first_tick_steps':(
            measurements[-1][23] if has_batch_position_probe else None),
        'batched_later_tick_steps':(
            measurements[-1][24] if has_batch_position_probe else None),
        'batched_first_tick_skips':(
            measurements[-1][25] if has_batch_position_probe else None),
        'batched_later_tick_skips':(
            measurements[-1][26] if has_batch_position_probe else None),
        'checkpoint_batch_position_intervals':(
            position_windows if has_batch_position_probe else None),
        'windows_with_both_render_modes':sum(
            w['single_tick_render_steps']>0 and w['batched_render_steps']>0
            for w in intervals),
        'windows_with_higher_batched_skip_rate':sum(
            w['single_tick_render_steps']>0 and w['batched_render_steps']>0 and
            w['skips_in_batched_render_frames']*w['single_tick_render_steps']>
            w['skips_in_single_tick_render_frames']*w['batched_render_steps']
            for w in intervals),
        'peak_observed_pending':max(row[6] for row in measurements),
        'audio_errors_added':0,
        'queued_buffers_never_above_two':True,
        'sound_device_audible_verified':False,
        'physical_switch_audio_verified':False,
        'audio_latency_verified':False,
        'original_arcade_audio_verified':False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--timeline',type=Path,required=True)
    p.add_argument('--controller',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    opts=p.parse_args(argv)
    try:
        result=verify(opts.report,opts.timeline,opts.controller)
    except (OSError,ValueError,OverflowError,UnicodeError):
        result={
            'schema':'dino-nexium-audout-900tick-v3',
            'status':'INCONCLUSIVE_NO_GUEST_AUDIO_RENDER_BATCH_EVIDENCE',
            'sound_device_audible_verified':False,
            'physical_switch_audio_verified':False,
            'audio_latency_verified':False,
            'original_arcade_audio_verified':False,
        }
    opts.out.write_text(json.dumps(result,sort_keys=True)+'\n',encoding='ascii')
    print(json.dumps(result,sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
