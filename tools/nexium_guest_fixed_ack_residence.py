#!/usr/bin/env python3
"""Model FIFO enqueue-to-ACK ages under actual 900-tick guest credits.

Recorded guest ACK discoveries are SHA/NRO-bound, but replacing depth=2
with depth=3/4 is an exogenous-credit counterfactual, NOT an experiment.
Synthetic prefill generation indices -initial..-1 stand for pages queued
before the observation window; their ages are therefore model conventions.
Ages are measured in simulated GAME TICKS, not audio-service timestamps,
actual PCM sample latency, host time or audible output.
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path

try:
    from tools import nexium_guest_fixed_ack_capacity_replay as bound
    from tools import verify_nexium_audio_ack_tick_trace as ack
    from tools import verify_nexium_audio_paired_artifacts as paired
    from tools import compare_nexium_audio_stress_runs as cross
except ImportError:
    import nexium_guest_fixed_ack_capacity_replay as bound
    import verify_nexium_audio_ack_tick_trace as ack
    import verify_nexium_audio_paired_artifacts as paired
    import compare_nexium_audio_stress_runs as cross

SCHEMA="dino-guest-frozen-ack-fifo-residence-v1"


def fifo_residence(credits, capacity, initial, rows=None):
    """Deterministic FIFO ledger, independently consistent with exact DP."""
    bound.valid_inputs(credits,capacity,initial)
    if rows is not None and (type(rows) is not list or
                             len(rows)!=len(credits)):
        raise ValueError("invalid independent guest tick ledger")
    queue=deque(range(-initial,0))
    last_generation=-initial-1
    released=accepted=skipped=0
    sum_age=max_age=0
    per_window=[]
    current_ages=[]
    pending_age_ge_three=0
    maximum_oldest_pending_age=0
    for tick,credit in enumerate(credits):
        if credit>len(queue):
            raise ValueError("observed ACK credit exceeds queued ownership")
        for _ in range(credit):
            generated=queue.popleft()
            if generated<=last_generation:
                raise ValueError("duplicate or backward PCM FIFO generation")
            last_generation=generated
            age=tick-generated
            if age<0:
                raise ValueError("negative modeled ACK age")
            sum_age+=age
            max_age=max(max_age,age)
            released+=1
            current_ages.append(age)
        if len(queue)<capacity:
            queue.append(tick)
            accepted+=1
        else:
            skipped+=1
        if rows is not None and capacity==2:
            row=rows[tick]
            if (type(row) is not dict or
                (row["released"],row["submitted"],row["skipped"],
                 row["pending"])!=(credit,
                                  int(queue[-1]==tick) if queue else 0,
                                  int(not queue or queue[-1]!=tick),
                                  len(queue))):
                raise ValueError("guest depth-two ledger contradicts FIFO")
        if queue:
            oldest=tick-queue[0]
            maximum_oldest_pending_age=max(maximum_oldest_pending_age,oldest)
            pending_age_ge_three+=sum(tick-generation>=3
                                      for generation in queue)
        if (tick+1)%150==0 or tick+1==len(credits):
            per_window.append({
                "tick_start":tick+1-((tick%150)+1),
                "tick_end":tick+1,
                "released_pages":len(current_ages),
                "released_generation_age_sum_ticks":sum(current_ages),
                "max_released_generation_age_ticks":
                    max(current_ages) if current_ages else None,
            })
            current_ages=[]
    original=bound.replay_credits(credits,capacity,initial,rows)
    if ((accepted,skipped,released,len(queue))!=
        (original["submitted"],original["skipped"],
         original["ack_pages_consumed"],original["end_pending"]) or
        sum(w["released_pages"] for w in per_window)!=released or
        sum(w["released_generation_age_sum_ticks"]
            for w in per_window)!=sum_age):
        raise ValueError("independent FIFO age ledger contradicts guest replay")
    return {
        "capacity_pages":capacity,
        "initial_prefill_synthetic_generation_ids":list(range(-initial,0)),
        "simulated_ticks":len(credits),
        "released_pages":released,
        "accepted_new_pcm_pages":accepted,
        "skipped_pcm_pages_discarded":skipped,
        "max_enqueued_generation_to_observed_ack_age_ticks":
            max_age if released else None,
        "sum_enqueued_generation_to_observed_ack_age_ticks":sum_age,
        "mean_enqueued_age_fraction_ticks":{
            "numerator":sum_age,"denominator":released if released else 1},
        "sum_pending_page_ticks_at_age_at_least_three":
            pending_age_ge_three,
        "max_oldest_pending_generation_age_ticks":
            maximum_oldest_pending_age if queue or accepted else None,
        "end_pending_pages":len(queue),
        "fifo_release_generation_order_verified":True,
        "physical_audio_latency_verified":False,
        "service_timestamp_verified":False,
        "per_150tick_windows":per_window,
    }


def make_report(base_trace,base_report,base_binding,base_nro,
                extra_trace,extra_report,extra_binding,extra_nro):
    # Require the already successful NRO/mode/hardware-evidence binding
    # and EXACT guest depth-two trace reproduction before interpreting age.
    capacity=bound.make_report(
        base_trace,base_report,base_binding,base_nro,
        extra_trace,extra_report,extra_binding,extra_nro)
    verified=paired.compare(
        base_report,base_binding,extra_report,extra_binding,
        base_nro,extra_nro)
    profiles=[]
    for mode,raw_path,report_path,witness,expected in (
        ("baseline",base_trace,base_report,capacity["modes"][0],
         verified["baseline_report_sha256"]),
        ("extra-poll",extra_trace,extra_report,capacity["modes"][1],
         verified["experimental_report_sha256"]),
    ):
        evidence=ack.verify(raw_path,report_path,mode)
        raw,rows=ack.parse_csv(raw_path)
        if (hashlib.sha256(raw).hexdigest()!=
            witness["bound_raw_ack_csv_sha256"] or
            evidence["guest_stress_report_sha256"]!=expected):
            raise ValueError("guest residence ledger source not SHA-bound")
        _,source=cross.read_report(report_path)
        start=source["queue_pending_at_stress_start"]
        credits=[row["released"] for row in rows]
        outcomes=[fifo_residence(credits,depth,start,rows)
                  for depth in bound.DEPTHS]
        for original,age in zip(witness["projection"],outcomes):
            if (original["capacity_pages"]!=age["capacity_pages"] or
                original["submitted"]!=age["accepted_new_pcm_pages"] or
                original["skipped"]!=age["skipped_pcm_pages_discarded"] or
                original["ack_pages_consumed"]!=age["released_pages"] or
                original["end_pending"]!=age["end_pending_pages"]):
                raise ValueError("guest FIFO age projection does not reconcile")
        baseline=outcomes[0]
        for row in outcomes:
            row["hypothetical_skips_avoided_vs_real_depth_two"]=( 
                baseline["skipped_pcm_pages_discarded"]-
                row["skipped_pcm_pages_discarded"])
            if not 0<=row[
                "hypothetical_skips_avoided_vs_real_depth_two"
            ]<=row["capacity_pages"]-2:
                raise ValueError("extra fixed-credit admissions exceed slots")
        profiles.append({
            "mode":mode,
            "bound_guest_ack_csv_sha256":witness[
                "bound_raw_ack_csv_sha256"],
            "bound_guest_stress_report_sha256":expected,
            "real_guest_depth_two_accounting_reconciled":True,
            "three_four_page_age_is_only_hypothetical":True,
            "per_capacity":outcomes,
        })
    return {
        "schema":SCHEMA,
        "status":"NRO_BOUND_GUEST_FIFO_AGE_TRADEOFF_UNDER_FROZEN_ACK_ONLY",
        "profiles":profiles,
        "age_is_synthetic_queue_residence_not_audible_latency":True,
        "initial_prefill_generation_time_is_a_model_convention":True,
        "ack_credit_arrival_preserved_as_counterfactual_assumption":True,
        "real_host_ack_feedback_on_capacity_known":False,
        "guest_depth_three_or_four_executed":False,
        "different_mode_host_conditions_matched_verified":False,
        "original_game_audio_parity_verified":False,
        "physical_switch_audio_verified":False,
        "causal_audio_improvement_verified":False,
        "production_queue_depth_modified":False,
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
        obj=make_report(args.baseline_trace,args.baseline_report,
                        args.baseline_binding,args.baseline_nro,
                        args.experimental_trace,args.experimental_report,
                        args.experimental_binding,args.experimental_nro)
        with args.out.open("x",encoding="ascii") as f:
            f.write(json.dumps(obj,sort_keys=True)+"\n")
    except (OSError,ValueError,TypeError,KeyError,OverflowError,
            UnicodeError) as exc:
        print(json.dumps({
            "status":"INCONCLUSIVE_GUEST_FROZEN_FIFO_AGE_MODEL",
            "reason":type(exc).__name__,
            "physical_switch_audio_verified":False,
            "causal_audio_improvement_verified":False,
        },sort_keys=True))
        return 1
    print(json.dumps({
        "status":obj["status"],
        "baseline_guest_released_pages":
            obj["profiles"][0]["per_capacity"][0]["released_pages"],
        "extra_guest_released_pages":
            obj["profiles"][1]["per_capacity"][0]["released_pages"],
        "physical_switch_audio_verified":False,
        "causal_audio_improvement_verified":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
