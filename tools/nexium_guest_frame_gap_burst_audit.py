#!/usr/bin/env python3
"""Describe only consecutive render-frame-ID batching bursts from guest ACKs.

A gap in observed frame IDs is NOT a set of invented game ticks. It can
contain zero-step render iterations and must break a contiguous-ID run,
even if both surrounding observed frames are multi-tick frames. An exact
900-tick real guest ACK trace and both mode-selected NROs are authenticated
before publication.

This reports simulated guest-frame topology, not elapsed host time, actual
audout ACK scheduling, speaker latency or causal audio improvements.
"""
import argparse
import hashlib
import json
from pathlib import Path

try:
    from tools import nexium_guest_frame_topology as topology
    from tools import verify_nexium_audio_ack_tick_trace as ack
    from tools import verify_nexium_audio_paired_artifacts as paired
except ImportError:
    import nexium_guest_frame_topology as topology
    import verify_nexium_audio_ack_tick_trace as ack
    import verify_nexium_audio_paired_artifacts as paired

SCHEMA="dino-nexium-bound-guest-consecutive-frame-bursts-v1"


def analyze_bursts(rows):
    """Consecutive *actual frame IDs*, never consecutive list entries alone."""
    verified=topology.scan_frames(rows)
    previous_frame=None
    previous_batch=0
    frames=[]
    for row in rows:
        frame_id=row["frame_id"]
        if previous_frame!=frame_id:
            frames.append({
                "frame_id":frame_id,
                "declared_batch_size":row["batch_size"],
                "first_observed_position":row["batch_position"],
                "last_observed_position":row["batch_position"],
                "observed_simulation_ticks":0,
                "skipped_pcm_ticks":0,
                "released_pcm_pages":0,
            })
            previous_frame=frame_id
        group=frames[-1]
        group["observed_simulation_ticks"]+=1
        group["skipped_pcm_ticks"]+=row["skipped"]
        group["released_pcm_pages"]+=row["released"]
        group["last_observed_position"]=row["batch_position"]
    segments=[]
    current=None
    total_gap=0
    max_gap=0
    missed_gaps_between_batched_frames=0
    for index,frame in enumerate(frames):
        ident=frame["frame_id"]
        batch=frame["declared_batch_size"]
        gap=0 if index==0 else ident-frames[index-1]["frame_id"]-1
        if gap<0:
            raise ValueError("nonmonotone guest render frame ID")
        total_gap+=gap
        max_gap=max(max_gap,gap)
        if (index>0 and gap>0 and batch>1 and
                frames[index-1]["declared_batch_size"]>1):
            missed_gaps_between_batched_frames+=1
        if batch==1:
            current=None
            continue
        if current is None or gap>0 or (
                index>0 and frames[index-1]["declared_batch_size"]==1):
            current={
                "start_frame_id":ident,
                "end_frame_id":ident,
                "render_frame_count":0,
                "observed_simulation_ticks":0,
                "skipped_pcm_ticks":0,
                "released_pcm_pages":0,
                "contains_left_window_censored_frame":False,
                "contains_right_window_censored_frame":False,
            }
            segments.append(current)
        current["end_frame_id"]=ident
        current["render_frame_count"]+=1
        current["observed_simulation_ticks"]+=frame["observed_simulation_ticks"]
        current["skipped_pcm_ticks"]+=frame["skipped_pcm_ticks"]
        current["released_pcm_pages"]+=frame["released_pcm_pages"]
        if index==0 and frame["first_observed_position"]!=0:
            current["contains_left_window_censored_frame"]=True
        if (index==len(frames)-1 and
            frame["last_observed_position"]!=batch-1):
            current["contains_right_window_censored_frame"]=True
    histogram={}
    for segment in segments:
        key=str(segment["render_frame_count"])
        histogram[key]=histogram.get(key,0)+1
        if (segment["end_frame_id"]-segment["start_frame_id"]+1!=
                segment["render_frame_count"]):
            raise ValueError("invented consecutive render-frame IDs")
    observed_batched=sum(f["declared_batch_size"]>1 for f in frames)
    observed_batched_ticks=sum(f["observed_simulation_ticks"] for f in frames
                               if f["declared_batch_size"]>1)
    skipped_batched=sum(f["skipped_pcm_ticks"] for f in frames
                        if f["declared_batch_size"]>1)
    if (sum(s["render_frame_count"] for s in segments)!=observed_batched or
        sum(s["observed_simulation_ticks"] for s in segments)!=
            observed_batched_ticks or
        sum(s["skipped_pcm_ticks"] for s in segments)!=skipped_batched or
        sum(s["released_pcm_pages"] for s in segments)!=
            sum(f["released_pcm_pages"] for f in frames
                if f["declared_batch_size"]>1) or
        total_gap!=verified["render_frame_ids_unobserved_in_interior_gaps"] or
        sum(int(key)*v for key,v in histogram.items())!=observed_batched or
        len(frames)!=verified[
            "observed_render_frames_with_at_least_one_game_tick"]):
        raise ValueError("guest render-burst frame or audio counters inconsistent")
    longest_observed=verified["max_consecutive_observed_batched_render_frames"]
    contiguous=max((seg["render_frame_count"] for seg in segments),default=0)
    if contiguous>longest_observed:
        raise ValueError("real adjacent-ID run exceeded observed run")
    longest=max(segments,key=lambda row:(
        row["render_frame_count"],row["observed_simulation_ticks"],
        -row["start_frame_id"])) if segments else None
    return {
        "observed_simulation_ticks":len(rows),
        "observed_render_frames_with_game_ticks":len(frames),
        "zero_simulation_tick_render_id_gaps_total":total_gap,
        "largest_unobserved_frame_id_gap":max_gap,
        "render_id_gaps_separating_observed_batched_frames":
            missed_gaps_between_batched_frames,
        "observed_batched_render_frames":observed_batched,
        "observed_batched_simulation_ticks":observed_batched_ticks,
        "skipped_pcm_ticks_in_observed_batched_frames":skipped_batched,
        "consecutive_render_id_batched_runs":len(segments),
        "consecutive_render_id_batch_run_length_histogram":histogram,
        "max_consecutive_observed_batched_frames_ignoring_id_gaps":
            longest_observed,
        "max_genuinely_adjacent_render_id_batched_frames":contiguous,
        "max_genuinely_adjacent_render_id_batched_run":longest,
        "pcm_skips_in_batched_runs_of_length_two_or_more":sum(
            s["skipped_pcm_ticks"] for s in segments
            if s["render_frame_count"]>=2),
        "pcm_skips_in_isolated_batched_render_frames":sum(
            s["skipped_pcm_ticks"] for s in segments
            if s["render_frame_count"]==1),
        "observed_skipped_pcm_ticks":sum(row["skipped"] for row in rows),
        "observed_released_pcm_pages":sum(row["released"] for row in rows),
        "boundary_partial_frames_are_not_imputed":True,
        "unobserved_render_frames_have_unknown_host_duration":True,
        "per_segment":segments,
    }


def make_report(base_trace,base_report,base_binding,base_nro,
                extra_trace,extra_report,extra_binding,extra_nro):
    witness=paired.compare(base_report,base_binding,extra_report,
                           extra_binding,base_nro,extra_nro)
    reports=[]
    for mode,trace,report,sha,nro_sha in (
        ("baseline",base_trace,base_report,
         witness["baseline_report_sha256"],
         witness["baseline_guest_nro_sha256"]),
        ("extra-poll",extra_trace,extra_report,
         witness["experimental_report_sha256"],
         witness["experimental_guest_nro_sha256"]),
    ):
        verified=ack.verify(trace,report,mode)
        raw,rows=ack.parse_csv(trace)
        if (verified["guest_stress_report_sha256"]!=sha or
            hashlib.sha256(raw).hexdigest()!=verified["guest_ack_csv_sha256"]
            or len(rows)!=900):
            raise ValueError("frame-burst data not bound to actual guest NRO")
        result=analyze_bursts(rows)
        if (result["observed_skipped_pcm_ticks"]!=
            witness["descriptive_comparison"][
                "baseline" if mode=="baseline" else "experimental"][
                "audio_blocks_skipped"] or
            result["observed_released_pcm_pages"]!=
                verified["ack_pages_observed"]):
            raise ValueError("guest burst skip/release totals do not reconcile")
        reports.append({
            "mode":mode,
            "guest_ack_csv_sha256":verified["guest_ack_csv_sha256"],
            "guest_stress_report_sha256":sha,
            "guest_nro_sha256":nro_sha,
            **result,
        })
    return {
        "schema":SCHEMA,
        "status":"NRO_BOUND_ADJACENT_RENDER_FRAME_BURSTS_DESCRIPTIVE_ONLY",
        "guest_profiles":reports,
        "guest_observation_tick_count_per_mode":900,
        "frame_id_gaps_are_not_audio_timestamps":True,
        "physical_host_frame_duration_verified":False,
        "frame_pacing_caused_pcm_skips_verified":False,
        "causal_audio_improvement_verified":False,
        "production_scheduler_modified":False,
        "production_audio_queue_modified":False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("baseline-trace","baseline-report","baseline-binding",
                 "baseline-nro","experimental-trace","experimental-report",
                 "experimental-binding","experimental-nro"):
        p.add_argument("--"+name,required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args(argv)
    try:
        result=make_report(a.baseline_trace,a.baseline_report,
                           a.baseline_binding,a.baseline_nro,
                           a.experimental_trace,a.experimental_report,
                           a.experimental_binding,a.experimental_nro)
        with a.out.open("x",encoding="ascii") as out:
            out.write(json.dumps(result,sort_keys=True)+"\n")
    except (OSError,ValueError,TypeError,KeyError,OverflowError,
            UnicodeError) as exc:
        print(json.dumps({
            "status":"INCONCLUSIVE_GUEST_RENDER_FRAME_BURST_AUDIT",
            "reason":type(exc).__name__,
            "frame_pacing_caused_pcm_skips_verified":False,
        },sort_keys=True))
        return 1
    print(json.dumps({
        "status":result["status"],
        "baseline_max_adjacent_render_id_burst":result[
            "guest_profiles"][0]["max_genuinely_adjacent_render_id_batched_frames"],
        "extra_max_adjacent_render_id_burst":result[
            "guest_profiles"][1]["max_genuinely_adjacent_render_id_batched_frames"],
        "frame_pacing_caused_pcm_skips_verified":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
