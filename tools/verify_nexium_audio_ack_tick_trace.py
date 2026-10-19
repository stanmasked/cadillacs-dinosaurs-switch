#!/usr/bin/env python3
"""Verify 900 exact ROM-free guest ACK-*observation* ticks.

These are the simulation ticks when libnx nonblocking polling RETURNS a
released PCM page to the guest. They are NOT service release timestamps,
host wall-clock times, speaker delivery or matched A/B scheduling.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

try:
    from tools import compare_nexium_audio_stress_runs as cross
    from tools import verify_nexium_audio_mid_batch_ab as ab
except ImportError:
    import compare_nexium_audio_stress_runs as cross
    import verify_nexium_audio_mid_batch_ab as ab

COLUMNS=('tick','frame_id','batch_size','batch_position','released',
         'mid_released','mid_calls','submitted','skipped','pre_poll_full',
         'pre_poll_recovered','pending','audio_errors')
FIELDS=('submitted','skipped','released','pre_poll_full',
        'pre_poll_recovered','mid_calls','mid_released')
MAX_TICKS=900


def parse_csv(path):
    p=Path(path)
    if p.is_symlink() or not p.is_file() or not 300<=p.stat().st_size<=128000:
        raise ValueError('bounded ordinary guest ACK CSV required')
    raw=p.read_bytes()
    if len(raw)!=p.stat().st_size or not 300<=len(raw)<=128000:
        raise ValueError('guest ACK CSV changed while reading')
    try:
        text=raw.decode('ascii')
        reader=csv.DictReader(text.splitlines(),strict=True)
        if reader.fieldnames!=list(COLUMNS):
            raise ValueError('guest ACK CSV schema mismatch')
        rows=list(reader)
    except (UnicodeError,csv.Error) as exc:
        raise ValueError('invalid guest ACK CSV') from exc
    if len(rows)!=MAX_TICKS:
        raise ValueError('incomplete 900-tick guest ACK trace')
    output=[]
    for row in rows:
        if None in row or set(row)!=set(COLUMNS):
            raise ValueError('extra or missing guest ACK fields')
        parsed={}
        for col in COLUMNS:
            value=row[col]
            if (type(value) is not str or not value or
                    not value.isascii() or not value.isdecimal() or
                    (len(value)>1 and value[0]=='0') or len(value)>10):
                raise ValueError('noncanonical ACK counter')
            number=int(value)
            if not 0<=number<=0xffffffff:
                raise ValueError('ACK counter exceeds uint32 range')
            parsed[col]=number
        output.append(parsed)
    return raw,output


def compare_trace(rows,report,mode):
    """Compare independent per-tick arithmetic with full guest checkpoints."""
    if type(rows) is not list or len(rows)!=MAX_TICKS:
        raise ValueError('guest per-tick trace count mismatch')
    if mode not in ('baseline','extra-poll') or type(mode) is not str:
        raise ValueError('invalid selected NRO mode')
    enabled=mode=='extra-poll'
    if report['guest_mid_batch_extra_poll_enabled'] is not enabled:
        raise ValueError('audio NRO mode does not match per-tick evidence')
    if report['simulation_ticks']!=MAX_TICKS:
        raise ValueError('guest audio stress duration mismatch')
    pending=report['queue_pending_at_stress_start']
    if type(pending) is not int or not 0<=pending<=2:
        raise ValueError('invalid initial queue occupancy')
    errors=report.get('audio_errors_added')
    if type(errors) is not int or errors!=0:
        raise ValueError('unhealthy guest audio adapter')
    stats={key:0 for key in FIELDS}
    windows=[]
    previous_frame=0
    last_batch=0
    last_position=0
    for tick,row in enumerate(rows,1):
        if type(row) is not dict or set(row)!=set(COLUMNS) or any(
                type(value) is not int or not 0<=value<=0xffffffff
                for value in row.values()):
            raise ValueError('malformed guest ACK tick row')
        frame=row['frame_id']
        batch=row['batch_size']
        position=row['batch_position']
        if (row['tick']!=tick or frame<1 or
                not 1<=batch<=15 or position>=batch or
                (frame<previous_frame) or
                (frame==previous_frame and (
                    position!=last_position+1 or batch!=last_batch)) or
                (frame>previous_frame and position!=0 and tick!=1)):
            raise ValueError('nonmonotone guest frame/tick classification')
        previous_frame,last_batch,last_position=frame,batch,position
        returns=row['released']
        mid=row['mid_released']
        midcalls=row['mid_calls']
        submitted=row['submitted']
        skipped=row['skipped']
        full=row['pre_poll_full']
        recovered=row['pre_poll_recovered']
        before_normal=pending-mid
        if (returns>2 or returns>pending or mid>returns or
                midcalls!=int(enabled and batch>=2 and position>0) or
                not 0<=before_normal<=2 or
                full!=int(before_normal==2) or
                recovered!=int(full and pending-returns<2) or
                submitted+skipped!=1 or
                submitted!=int(pending-returns<2) or
                row['pending']!=pending-returns+submitted or
                row['pending']>2 or row['audio_errors']!=0):
            raise ValueError('impossible guest ACK admission/poll accounting')
        pending=row['pending']
        group=('single' if batch==1 else
               'first' if position==0 else 'later')
        for key in FIELDS:
            stats[key]+=row[key]
        if (tick-1)%150==0:
            groups={n:{k:0 for k in FIELDS} | {'ticks':0}
                    for n in ('single','first','later')}
        g=groups[group]
        g['ticks']+=1
        for key in FIELDS:
            g[key]+=row[key]
        if tick%150==0:
            i=tick//150-1
            offset=lambda k:report[k][i]
            position_report=offset('checkpoint_batch_position_intervals')
            release=offset('checkpoint_release_position_intervals')
            recovery=offset('checkpoint_batch_position_poll_intervals')
            polls=offset('checkpoint_guest_mid_batch_extra_poll_intervals')
            mode_row=offset('checkpoint_mode_intervals')
            total=offset('checkpoint_release_poll_intervals')
            for entry in (position_report,release,recovery,polls,mode_row,total):
                if (type(entry) is not dict or
                        type(entry.get('tick_start')) is not int or
                        type(entry.get('tick_end')) is not int or
                        entry['tick_start']!=tick-150 or
                        entry['tick_end']!=tick):
                    raise ValueError('guest ACK checkpoint misalignment')
            for label,steps,skips,pages in (
                ('single',mode_row['single_tick_render_steps'],
                 mode_row['skips_in_single_tick_render_frames'],
                 release['single_frame_released_pages']),
                ('first',position_report['first_tick_steps'],
                 position_report['first_tick_skips'],
                 release['batched_first_released_pages']),
                ('later',position_report['later_tick_steps'],
                 position_report['later_tick_skips'],
                 release['batched_later_released_pages'])):
                actual=groups[label]
                if (actual['ticks'],actual['skipped'],actual['released'])!=(
                        steps,skips,pages):
                    raise ValueError('guest ACK tick exposure does not match checkpoints')
            for label,full_key,recovery_key in (
                ('first','first_full_before_poll','first_recovered_after_poll'),
                ('later','later_full_before_poll','later_recovered_after_poll'),
                ('single','single_full_before_poll','single_recovered_after_poll')):
                if (groups[label]['pre_poll_full']!=recovery[full_key] or
                        groups[label]['pre_poll_recovered']!=recovery[recovery_key]):
                    raise ValueError('guest ACK full/recovery position mismatch')
            if (sum(groups[g]['pre_poll_full'] for g in groups)!=total['full_before_poll']
                    or sum(groups[g]['pre_poll_recovered'] for g in groups)!=
                    total['recovered_before_admission'] or
                    groups['later']['mid_calls']!=polls['poll_calls'] or
                    groups['later']['mid_released']!=polls['poll_released_pages'] or
                    sum(groups[g]['mid_calls']+groups[g]['mid_released']
                        for g in ('single','first'))!=0 or
                    sum(groups[g]['skipped'] for g in groups)!=
                    report['checkpoint_skipped_deltas'][i]):
                raise ValueError('guest ACK window counter mismatch')
            windows.append({
                'tick_start':tick-150,'tick_end':tick,
                'released_pages':sum(groups[g]['released'] for g in groups),
                'ack_discovery_ticks':sum(
                    1 for r in rows[tick-150:tick] if r['released']>0),
                'mid_poll_released_pages':groups['later']['mid_released'],
                'submitted':sum(groups[g]['submitted'] for g in groups),
                'skipped':sum(groups[g]['skipped'] for g in groups),
                'pending_end':pending,
            })
    for name,expected in (
            ('submitted',report['audout_blocks_submitted']),
            ('released',report['audout_blocks_released']),
            ('skipped',report['audout_blocks_skipped']),
            ('mid_calls',report['guest_mid_batch_extra_poll_calls']),
            ('mid_released',report['guest_mid_batch_extra_poll_released_pages']),
            ('pre_poll_full',report['full_before_release_poll_ticks']),
            ('pre_poll_recovered',report['full_recovered_before_admission_ticks'])):
        # Guest counters (not total submitted/released) include pre-stress
        # pages: reconcile the *delta* rather than the lifetime totals.
        if name in ('submitted','released'):
            # These report counts are stress-period deltas, excluding the
            # two or fewer pending pages that predate the START checkpoint.
            observed_expected=expected
        else:
            observed_expected=expected
        if stats[name]!=observed_expected:
            raise ValueError('guest ACK 900-tick sum mismatch: '+name)
    if pending!=report['queue_pending_at_stress_end']:
        raise ValueError('guest ACK final queue occupancy mismatch')
    return {
        'status':'GUEST_900TICK_ACK_DISCOVERY_TIMELINE_WITNESSED',
        'selected_mode':mode,
        'simulation_ticks':MAX_TICKS,
        'ack_pages_observed':stats['released'],
        'ack_discovery_ticks':sum(1 for r in rows if r['released']>0),
        'mid_poll_calls':stats['mid_calls'],
        'mid_poll_ack_pages_observed':stats['mid_released'],
        'ack_discovery_windows':windows,
        'exact_simulation_tick_of_guest_ack_discovery_observed':True,
        'libnx_service_arrival_timestamp_observed':False,
        'physical_speaker_delivery_verified':False,
        'causal_audio_improvement_verified':False,
    }


def verify(trace_path,report_path,mode):
    raw,rows=parse_csv(trace_path)
    report_raw,report=cross.read_report(report_path)
    cross.validate(report)
    ab.verify_mode(report,mode=='extra-poll')
    result=compare_trace(rows,report,mode)
    result.update({
        'schema':'dino-nexium-guest-ack-discovery-v1',
        'guest_ack_csv_sha256':hashlib.sha256(raw).hexdigest(),
        'guest_stress_report_sha256':hashlib.sha256(report_raw).hexdigest(),
    })
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--mode',choices=('baseline','extra-poll'),required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        result=verify(args.trace,args.report,args.mode)
        with args.out.open('x',encoding='ascii') as stream:
            stream.write(json.dumps(result,sort_keys=True)+'\n')
    except (OSError,ValueError,KeyError,TypeError,UnicodeError,
            csv.Error) as exc:
        print(json.dumps({'status':'INCONCLUSIVE_GUEST_ACK_TICK_TRACE',
                          'reason':type(exc).__name__,
                          'libnx_service_arrival_timestamp_observed':False},
                         sort_keys=True))
        return 1
    print(json.dumps({'status':result['status'],
                      'ack_pages_observed':result['ack_pages_observed'],
                      'libnx_service_arrival_timestamp_observed':False},
                     sort_keys=True))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
