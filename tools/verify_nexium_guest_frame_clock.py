#!/usr/bin/env python3
"""Audit ROM-free capped frame-loop clock intervals, bound to guest ACK ticks.

Intervals come from the *existing* armTicksToNs(now-last_tick) already
capped at 250ms by main.c. They are NOT precise untruncated elapsed host
time, visible-frame presentation times, or audio-service/speaker latency.
900 game ticks can span zero-tick render iterations and clipped first/last
frames. Fails closed if a frame's ticks disagree with the 900 authenticated
mode/NRO-bound guest ACK observation rows.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

try:
    from tools import verify_nexium_audio_ack_tick_trace as ack
    from tools import verify_nexium_audio_paired_artifacts as paired
except ImportError:
    import verify_nexium_audio_ack_tick_trace as ack
    import verify_nexium_audio_paired_artifacts as paired

SCHEMA="dino-guest-capped-render-loop-clock-v1"
COLS=("frame_id","elapsed_ns_capped","frame_game_ticks","stress_game_ticks")
MAX_ROWS=4096


def read_clock(path):
    file=Path(path)
    if file.is_symlink() or not file.is_file() or not 64<=file.stat().st_size<=250000:
        raise ValueError("missing/unbounded guest frame clock")
    data=file.read_bytes()
    if not 64<=len(data)<=250000 or len(data)!=file.stat().st_size:
        raise ValueError("guest clock bytes changed")
    try:
        rdr=csv.DictReader(data.decode("ascii").splitlines(),strict=True)
        if rdr.fieldnames!=list(COLS):
            raise ValueError("frame clock column mismatch")
        raw=list(rdr)
    except (UnicodeError,csv.Error) as exc:
        raise ValueError("invalid frame clock CSV") from exc
    if not 1<=len(raw)<=MAX_ROWS:
        raise ValueError("guest frame clock row count overflow/truncation")
    rows=[]
    for entry in raw:
        if None in entry or set(entry)!=set(COLS):
            raise ValueError("extra frame clock CSV columns")
        row={}
        for col in COLS:
            string=entry[col]
            if (type(string) is not str or not string.isascii() or
                not string.isdecimal() or len(string)>10 or
                (len(string)>1 and string[0]=="0")):
                raise ValueError("noncanonical guest frame clock counter")
            value=int(string)
            if not 0<=value<=0xffffffff:
                raise ValueError("frame clock counter outside uint32")
            row[col]=value
        rows.append(row)
    return data,rows


def witness_clock(rows,ack_rows):
    if (type(rows) is not list or not 1<=len(rows)<=MAX_ROWS or
        type(ack_rows) is not list or len(ack_rows)!=900):
        raise ValueError("invalid frame clock/guest ACK lengths")
    total=0
    previous_id=None
    intervals=[]
    zero=long_zero=run_zero=clamped=0
    first=None
    last=None
    for i,row in enumerate(rows):
        if type(row) is not dict or set(row)!=set(COLS) or any(
            type(value) is not int or value<0 for value in row.values()):
            raise ValueError("invalid frame clock row")
        fid=row["frame_id"]
        ns=row["elapsed_ns_capped"]
        ticks=row["frame_game_ticks"]
        sample=row["stress_game_ticks"]
        if (fid<1 or fid>0xffffffff or
            (previous_id is not None and fid!=previous_id+1) or
            not 0<=ns<=250000000 or not 0<=ticks<=15 or
            sample>ticks or sample>900-total):
            raise ValueError("invalid frame tick or existing scheduler clock")
        if 0<i<len(rows)-1 and sample!=ticks:
            raise ValueError("incomplete interior scheduler render iteration")
        if i==len(rows)-1 and sample==0:
            raise ValueError("final observed frame lacks final guest ACK tick")
        if i==0 and sample<ticks:
            first=True
        if i==len(rows)-1 and sample<ticks:
            last=True
        if ns==250000000:
            clamped+=1
        if ticks==0:
            zero+=1
            run_zero+=1
            long_zero=max(long_zero,run_zero)
        else:
            run_zero=0
        for a in ack_rows[total:total+sample]:
            if (type(a) is not dict or
                a["frame_id"]!=fid or a["batch_size"]!=ticks):
                raise ValueError("capped frame clock not aligned with real guest ACK")
        total+=sample
        previous_id=fid
        intervals.append(ns)
    if total!=900:
        raise ValueError("guest clock did not cover precisely 900 ACK ticks")
    sorted_intervals=sorted(intervals)
    # Fixed exact order statistics, no false claim of absolute wall time.
    quantile=lambda n,d:sorted_intervals[(n*len(intervals)+d-1)//d-1]
    return {
        "frame_rows":len(rows),
        "reconciled_actual_guest_audio_ticks":total,
        "zero_game_tick_render_iterations":zero,
        "maximum_consecutive_zero_tick_render_iterations":long_zero,
        "capped_250ms_interval_rows":clamped,
        "scheduler_interval_ns_sum_after_clamp":sum(intervals),
        "scheduler_interval_ns_min":sorted_intervals[0],
        "scheduler_interval_ns_median_upper":sorted_intervals[len(intervals)//2],
        "scheduler_interval_ns_p95_order_statistic":quantile(95,100),
        "scheduler_interval_ns_max":sorted_intervals[-1],
        "first_frame_left_clipped_possible":bool(first),
        "last_frame_right_clipped_possible":bool(last),
        "full_guest_frame_id_contiguity_verified":True,
        "per_frame_interval_capped_by_existing_scheduler":True,
        "uncapped_host_elapsed_time_verified":False,
        "speaker_audio_latency_verified":False,
    }


def make_report(base_clock,base_trace,base_report,base_binding,base_nro,
                extra_clock,extra_trace,extra_report,extra_binding,extra_nro):
    provenance=paired.compare(base_report,base_binding,extra_report,
                              extra_binding,base_nro,extra_nro)
    results=[]
    for mode,clock,trace,report,sha,nro_sha in (
        ("baseline",base_clock,base_trace,base_report,
         provenance["baseline_report_sha256"],
         provenance["baseline_guest_nro_sha256"]),
        ("extra-poll",extra_clock,extra_trace,extra_report,
         provenance["experimental_report_sha256"],
         provenance["experimental_guest_nro_sha256"]),
    ):
        verified=ack.verify(trace,report,mode)
        raw_ack,guest=ack.parse_csv(trace)
        raw_clock,frames=read_clock(clock)
        if (sha!=verified["guest_stress_report_sha256"] or
            hashlib.sha256(raw_ack).hexdigest()!=verified["guest_ack_csv_sha256"]):
            raise ValueError("real guest frame clock source not NRO-bound")
        summary=witness_clock(frames,guest)
        results.append({
            "mode":mode,
            "guest_clock_sha256":hashlib.sha256(raw_clock).hexdigest(),
            "guest_ack_csv_sha256":verified["guest_ack_csv_sha256"],
            "bound_guest_nro_sha256":nro_sha,
            "guest_stress_report_sha256":sha,
            **summary,
        })
    return {
        "schema":SCHEMA,
        "status":"NRO_BOUND_EXISTING_CAPPED_GUEST_FRAME_INTERVALS_RECONCILED",
        "profiles":results,
        "capped_clocks_are_not_audout_release_times":True,
        "guest_frame_times_causally_matched":False,
        "physical_switch_speaker_timing_verified":False,
        "production_frame_scheduler_changed":False,
        "production_pcm_queue_changed":False,
        "causal_audio_improvement_verified":False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("baseline-clock","baseline-trace","baseline-report",
                "baseline-binding","baseline-nro","experimental-clock",
                "experimental-trace","experimental-report",
                "experimental-binding","experimental-nro"):
        parser.add_argument("--"+key,type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=make_report(
            args.baseline_clock,args.baseline_trace,args.baseline_report,
            args.baseline_binding,args.baseline_nro,args.experimental_clock,
            args.experimental_trace,args.experimental_report,
            args.experimental_binding,args.experimental_nro)
        with args.out.open("x",encoding="ascii") as stream:
            stream.write(json.dumps(result,sort_keys=True)+"\n")
    except (OSError,ValueError,KeyError,TypeError,OverflowError,UnicodeError,
            csv.Error) as exc:
        print(json.dumps({
            "status":"INCONCLUSIVE_GUEST_CAPPED_FRAME_CLOCK",
            "reason":type(exc).__name__,
            "physical_switch_speaker_timing_verified":False,
            "causal_audio_improvement_verified":False,
        },sort_keys=True))
        return 1
    print(json.dumps({
        "status":result["status"],
        "baseline_frame_intervals":result["profiles"][0]["frame_rows"],
        "extra_frame_intervals":result["profiles"][1]["frame_rows"],
        "causal_audio_improvement_verified":False},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
