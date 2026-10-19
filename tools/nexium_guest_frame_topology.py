#!/usr/bin/env python3
"""Verify topology of ACTUAL 900-tick ROM-free guest frame-batch witnesses.

Frame IDs name *render iterations*; a render frame may contain 0, 1, or
multiple simulated game ticks. The exact 900-tick observation window can
begin/end inside a frame, so only the first and last *observed* frames
may be partial. No sampling-frame boundary or 150-tick checkpoint splits
a render frame into invented extra frames.

All conclusions are about the guest's SIMULATION tick topology, not host
elapsed time, actual audio-service ACK times, speakers or causal A/B gains.
"""
import argparse
import hashlib
import json
from pathlib import Path

try:
    from tools import verify_nexium_audio_ack_tick_trace as ack
    from tools import verify_nexium_audio_paired_artifacts as paired
except ImportError:
    import verify_nexium_audio_ack_tick_trace as ack
    import verify_nexium_audio_paired_artifacts as paired

SCHEMA="dino-nexium-bound-guest-frame-topology-v1"
FIELDS=("released","skipped","submitted","mid_calls","mid_released")
SINGLE="single"
FIRST="first"
LATER="later"


def scan_frames(rows):
    """Exact frame grouping; allows observed start/end to be censored.

    The input normally comes from ack.verify(), which already authenticates
    every row, guest queue conservation, mode and six 150-tick checkpoints.
    A direct call still rejects malformed topology independently.
    """
    if type(rows) is not list or not 1<=len(rows)<=900:
        raise ValueError("bounded per-tick frame topology required")
    groups=[]
    current=None
    seen=0
    for index,row in enumerate(rows):
        if type(row) is not dict:
            raise ValueError("malformed guest frame row")
        for key in ("frame_id","batch_size","batch_position",*FIELDS):
            if key not in row or type(row[key]) is not int or row[key]<0:
                raise ValueError("missing/invalid frame topology counter")
        frame=row["frame_id"]
        batch=row["batch_size"]
        position=row["batch_position"]
        if not 1<=frame<=0xffffffff or not 1<=batch<=15 or position>=batch:
            raise ValueError("invalid frame ID or batch position")
        if row["skipped"] not in (0,1) or row["submitted"] not in (0,1):
            raise ValueError("invalid guest frame audio admissions")
        if row["submitted"]+row["skipped"]!=1 or (
                row["released"]>2 or row["mid_released"]>2 or
                row["mid_released"]>row["released"]):
            raise ValueError("impossible frame audio counters")
        if current is None or frame!=current["frame_id"]:
            if current is not None and frame<=current["frame_id"]:
                raise ValueError("render frame ID reversed or duplicated")
            current={
                "frame_id":frame,
                "batch_size":batch,
                "first_observed_position":position,
                "last_observed_position":position,
                "tick_start":index+1,
                "tick_end":index+1,
                "observed_ticks":0,
                **{key:0 for key in FIELDS},
            }
            groups.append(current)
        elif batch!=current["batch_size"] or (
                position!=current["last_observed_position"]+1):
            raise ValueError("noncontiguous positions in one render frame")
        current["last_observed_position"]=position
        current["observed_ticks"]+=1
        current["tick_end"]=index+1
        for key in FIELDS:
            current[key]+=row[key]
        seen+=1

    # Missing positions are allowed ONLY across the observation's external
    # boundaries, not after the first row or before the final row.
    for i,g in enumerate(groups):
        left=g["first_observed_position"]!=0
        right=g["last_observed_position"]!=g["batch_size"]-1
        if (left and i!=0) or (right and i!=len(groups)-1):
            raise ValueError("incomplete interior render frame")
        if g["observed_ticks"]!=(
                g["last_observed_position"]-
                g["first_observed_position"]+1):
            raise ValueError("missing guest simulation ticks within frame")
        g["left_censored_by_window"]=left
        g["right_censored_by_window"]=right
        g["complete_in_observation"]=not (left or right)

    frames_by_declared_batch={}
    skips_by_position={"single":0,"first":0,"later":0}
    tick_counts_by_position={"single":0,"first":0,"later":0}
    batches_with_skips=0
    complete_batched=partial_batched=0
    zero_tick_render_frame_gaps=0
    max_contiguous_batch_frame_run=run=0
    for i,g in enumerate(groups):
        batch=g["batch_size"]
        key=str(batch)
        bucket=frames_by_declared_batch.setdefault(key,{
            "observed_frames":0,"complete_frames":0,
            "observed_game_ticks":0,"skipped_pcm_ticks":0,
            "released_pcm_pages":0,
        })
        bucket["observed_frames"]+=1
        bucket["complete_frames"]+=int(g["complete_in_observation"])
        bucket["observed_game_ticks"]+=g["observed_ticks"]
        bucket["skipped_pcm_ticks"]+=g["skipped"]
        bucket["released_pcm_pages"]+=g["released"]
        if batch>1:
            complete_batched+=int(g["complete_in_observation"])
            partial_batched+=int(not g["complete_in_observation"])
            batches_with_skips+=int(g["skipped"]>0)
            run+=1
            max_contiguous_batch_frame_run=max(
                max_contiguous_batch_frame_run,run)
        else:
            run=0
        if i>0:
            zero_tick_render_frame_gaps+=(
                g["frame_id"]-groups[i-1]["frame_id"]-1)
    for row in rows:
        p=(SINGLE if row["batch_size"]==1 else
           FIRST if row["batch_position"]==0 else LATER)
        skips_by_position[p]+=row["skipped"]
        tick_counts_by_position[p]+=1
    if (sum(g["observed_ticks"] for g in groups)!=seen or
        sum(g["skipped"] for g in groups)!=sum(r["skipped"] for r in rows) or
        sum(g["released"] for g in groups)!=sum(r["released"] for r in rows) or
        sum(x["observed_game_ticks"]
            for x in frames_by_declared_batch.values())!=seen or
        sum(tick_counts_by_position.values())!=seen or
        sum(skips_by_position.values())!=sum(r["skipped"] for r in rows)):
        raise ValueError("frame topology observation conservation failed")
    left_clipped=groups[0]["left_censored_by_window"]
    right_clipped=groups[-1]["right_censored_by_window"]
    return {
        "observed_simulation_ticks":seen,
        "observed_render_frames_with_at_least_one_game_tick":len(groups),
        "render_frame_ids_unobserved_in_interior_gaps":
            zero_tick_render_frame_gaps,
        "observed_complete_render_frames":sum(
            g["complete_in_observation"] for g in groups),
        "observed_partial_boundary_frames":sum(
            not g["complete_in_observation"] for g in groups),
        "first_observed_render_frame_left_censored":left_clipped,
        "last_observed_render_frame_right_censored":right_clipped,
        "complete_batched_render_frames":complete_batched,
        "boundary_partial_batched_render_frames":partial_batched,
        "observed_batched_frames_with_any_pcm_skip":batches_with_skips,
        "max_consecutive_observed_batched_render_frames":
            max_contiguous_batch_frame_run,
        "observed_frame_size_histogram":frames_by_declared_batch,
        "simulation_ticks_by_frame_position":tick_counts_by_position,
        "skipped_pcm_by_frame_position":skips_by_position,
        "observed_pcm_skips":sum(r["skipped"] for r in rows),
        "observed_pcm_released_pages":sum(r["released"] for r in rows),
        "first_observed_frame":{
            k:groups[0][k] for k in (
                "frame_id","batch_size","first_observed_position",
                "last_observed_position","observed_ticks")},
        "last_observed_frame":{
            k:groups[-1][k] for k in (
                "frame_id","batch_size","first_observed_position",
                "last_observed_position","observed_ticks")},
        "frame_counts_are_render_iterations_not_elapsed_time":True,
        "unknown_unobserved_simulation_frames_not_imputed":True,
    }


def make_report(base_trace,base_report,base_binding,base_nro,
                extra_trace,extra_report,extra_binding,extra_nro):
    # Both real reports and NROs must be independently verified first.
    binding=paired.compare(base_report,base_binding,extra_report,
                           extra_binding,base_nro,extra_nro)
    profiles=[]
    for mode,trace,report,digest,nro_digest in (
        ("baseline",base_trace,base_report,
         binding["baseline_report_sha256"],
         binding["baseline_guest_nro_sha256"]),
        ("extra-poll",extra_trace,extra_report,
         binding["experimental_report_sha256"],
         binding["experimental_guest_nro_sha256"]),
    ):
        witness=ack.verify(trace,report,mode)
        raw,rows=ack.parse_csv(trace)
        if (witness["guest_stress_report_sha256"]!=digest or
                hashlib.sha256(raw).hexdigest()!=witness["guest_ack_csv_sha256"]):
            raise ValueError("guest raw frame topology changed after attestation")
        if len(rows)!=900:
            raise ValueError("full NRO-bound guest frame topology required")
        scan=scan_frames(rows)
        if (scan["observed_pcm_skips"]!=
            binding["descriptive_comparison"][
                "baseline" if mode=="baseline" else "experimental"][
                "audio_blocks_skipped"] or
            scan["observed_pcm_released_pages"]!=
                witness["ack_pages_observed"]):
            raise ValueError("guest frame topology does not reconcile audio")
        profiles.append({
            "selected_mode":mode,
            "guest_ack_csv_sha256":witness["guest_ack_csv_sha256"],
            "guest_nro_sha256":nro_digest,
            "guest_report_sha256":digest,
            **scan,
        })
    return {
        "schema":SCHEMA,
        "status":"NRO_BOUND_GUEST_RENDER_FRAME_TOPOLOGY_WITNESSED",
        "profiles":profiles,
        "observation_boundary_clipping_reported":True,
        "identical_host_frame_pacing_verified":False,
        "causal_pcm_skip_explanation_verified":False,
        "physical_switch_audio_verified":False,
        "speaker_latency_verified":False,
        "production_game_frame_scheduler_modified":False,
        "production_audio_queue_modified":False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ("baseline-trace","baseline-report","baseline-binding",
                "baseline-nro","experimental-trace","experimental-report",
                "experimental-binding","experimental-nro"):
        parser.add_argument("--"+key,required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        result=make_report(
            args.baseline_trace,args.baseline_report,args.baseline_binding,
            args.baseline_nro,args.experimental_trace,args.experimental_report,
            args.experimental_binding,args.experimental_nro)
        with args.out.open("x",encoding="ascii") as out:
            out.write(json.dumps(result,sort_keys=True)+"\n")
    except (OSError,ValueError,TypeError,KeyError,OverflowError,
            UnicodeError) as exc:
        print(json.dumps({
            "status":"INCONCLUSIVE_GUEST_FRAME_TOPOLOGY",
            "reason":type(exc).__name__,
            "causal_pcm_skip_explanation_verified":False,
        },sort_keys=True))
        return 1
    print(json.dumps({
        "status":result["status"],
        "baseline_partial_frames":result["profiles"][0][
            "observed_partial_boundary_frames"],
        "extra_partial_frames":result["profiles"][1][
            "observed_partial_boundary_frames"],
        "physical_switch_audio_verified":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
