#!/usr/bin/env python3
"""Replay REAL guest ACK-discovery counts as FROZEN credits: ROM-free model.

The guest can observe a buffer return because of queue occupancy and timing,
so using that SAME recorded ACK stream for any other queue depth is a
counterfactual *assumption*, NOT hardware behavior or a causal audio benefit.
Each real 900-tick trace is authenticated by the existing guest/NRO auditors.
Original production remains depth=2. One PCM page attempted each tick, no
deferred playback of dropped pages, return then admit, FIFO ownership.
"""
import argparse
import hashlib
import json
from pathlib import Path

try:
    from tools import verify_nexium_audio_ack_tick_trace as ack
    from tools import verify_nexium_audio_paired_artifacts as paired
    from tools import compare_nexium_audio_stress_runs as cross
except ImportError:
    import verify_nexium_audio_ack_tick_trace as ack
    import verify_nexium_audio_paired_artifacts as paired
    import compare_nexium_audio_stress_runs as cross

SCHEMA="dino-guest-fixed-ack-counterfactual-depth-v1"
DEPTHS=(2,3,4)
HORIZON=900


def valid_inputs(credits,capacity,initial):
    if type(capacity) is not int or capacity not in DEPTHS:
        raise ValueError("capacity must be 2, 3 or 4")
    if type(initial) is not int or not 0<=initial<=2:
        raise ValueError("invalid actual starting occupancy")
    if type(credits) not in (list,tuple) or not 1<=len(credits)<=HORIZON:
        raise ValueError("invalid recorded credit sequence")
    if any(type(c) is not int or c not in (0,1,2) for c in credits):
        raise ValueError("release count per guest simulation tick must be 0..2")


def exact_best_admissions(credits,capacity,initial):
    """Independent finite-state exhaustive DP of all accept/skip decisions.

    Under frozen credits, we allow voluntary drops. It proves the greedy
    admission count is maximal even if a policy could withhold audio.
    """
    valid_inputs(credits,capacity,initial)
    state={initial:0}
    for credit in credits:
        nxt={}
        for before,count in state.items():
            after=before-min(credit,before)
            for add in (0,1) if after<capacity else (0,):
                nxt[after+add]=max(nxt.get(after+add,-1),count+add)
        state=nxt
    return max(state.values())


def replay_credits(credits,capacity,initial,observed_rows=None):
    valid_inputs(credits,capacity,initial)
    if observed_rows is not None and (type(observed_rows) is not list or
            len(observed_rows)!=len(credits)):
        raise ValueError("observed guest row count mismatch")
    pending=initial
    accepted=skipped=released=0
    peak=pending
    windows=[]
    current={"submitted":0,"skipped":0,"released":0}
    for index,credit in enumerate(credits):
        actual=min(pending,credit)
        if actual!=credit:
            raise ValueError("frozen ACK references a nonexistent queued page")
        pending-=actual
        released+=actual
        current["released"]+=actual
        admit=int(pending<capacity)
        pending+=admit
        accepted+=admit
        skipped+=1-admit
        current["submitted"]+=admit
        current["skipped"]+=1-admit
        peak=max(peak,pending)
        if pending!=initial+accepted-released or pending>capacity:
            raise ValueError("frozen ACK replay lost queue ownership")
        if observed_rows is not None and capacity==2:
            row=observed_rows[index]
            if (type(row) is not dict or
                (row["released"],row["submitted"],row["skipped"],
                 row["pending"])!=(actual,admit,1-admit,pending)):
                raise ValueError("recorded two-page guest admission disagrees")
        if (index+1)%150==0 or index+1==len(credits):
            windows.append({"tick_start":index+1-(index%150+1),
                            "tick_end":index+1,"pending_end":pending,
                            **current})
            current={"submitted":0,"skipped":0,"released":0}
    optimum=exact_best_admissions(credits,capacity,initial)
    if accepted!=optimum:
        raise ValueError("greedy did not reach the frozen-ACK exact optimum")
    return {
        "capacity_pages":capacity,
        "initial_guest_pending_pages":initial,
        "ticks":len(credits),
        "frozen_ack_pages":sum(credits),
        "ack_pages_consumed":released,
        "submitted":accepted,
        "skipped":skipped,
        "end_pending":pending,
        "peak_pending":peak,
        "exact_max_admissions_under_frozen_ack":optimum,
        "unavoidable_skips_under_frozen_ack":len(credits)-optimum,
        "guest_device_ack_schedule_preserved_counterfactually":False,
        "rejected_pcm_replayed":False,
        "windows":windows,
    }


def make_report(base_trace,base_report,base_binding,base_nro,
                extra_trace,extra_report,extra_binding,extra_nro):
    binding=paired.compare(base_report,base_binding,extra_report,
                           extra_binding,base_nro,extra_nro)
    modes=[]
    for mode,trace,report_path,digest,nro_digest in (
        ("baseline",base_trace,base_report,
         binding["baseline_report_sha256"],
         binding["baseline_guest_nro_sha256"]),
        ("extra-poll",extra_trace,extra_report,
         binding["experimental_report_sha256"],
         binding["experimental_guest_nro_sha256"]),
    ):
        witness=ack.verify(trace,report_path,mode)
        if witness["guest_stress_report_sha256"]!=digest:
            raise ValueError("guest frozen credits not bound to NRO witness")
        raw,rows=ack.parse_csv(trace)
        if hashlib.sha256(raw).hexdigest()!=witness["guest_ack_csv_sha256"]:
            raise ValueError("raw guest ACK changed since attestation")
        _,report=cross.read_report(report_path)
        credits=[row["released"] for row in rows]
        if sum(credits)!=witness["ack_pages_observed"]:
            raise ValueError("guest ACK pages mismatch")
        start=report["queue_pending_at_stress_start"]
        projections=[replay_credits(credits,capacity,start,rows)
                     for capacity in DEPTHS]
        recorded=projections[0]
        if (recorded["submitted"]!=report["audout_blocks_submitted"] or
            recorded["skipped"]!=report["audout_blocks_skipped"] or
            recorded["ack_pages_consumed"]!=report["audout_blocks_released"] or
            recorded["end_pending"]!=report["queue_pending_at_stress_end"]):
            raise ValueError("actual guest two-page replay failed reconciliation")
        modes.append({
            "mode":mode,
            "bound_nro_sha256":nro_digest,
            "bound_report_sha256":digest,
            "bound_raw_ack_csv_sha256":witness["guest_ack_csv_sha256"],
            "real_guest_two_page_ledger_verified":True,
            "guest_ack_discovery_pages":sum(credits),
            "projection":projections,
            "three_page_model_only":True,
            "four_page_model_only":True,
        })
    return {
        "schema":SCHEMA,
        "status":"REAL_GUEST_DEPTH_TWO_REPLAY_WITH_FROZEN_ACK_DEPTH_HYPOTHESES",
        "source":"TWO_DISTINCT_NRO_BOUND_ACTUAL_GUEST_ACK_DISCOVERY_TRACES",
        "capacity_pages_compared":list(DEPTHS),
        "modes":modes,
        "ack_schedule_exogenous_in_counterfactual_model":True,
        "real_host_ack_feedback_on_capacity_known":False,
        "host_conditions_matched_between_modes_verified":False,
        "production_audio_queue_depth_modified":False,
        "guest_depth_three_or_four_executed":False,
        "original_arcade_audio_verified":False,
        "physical_switch_audio_verified":False,
        "speaker_latency_verified":False,
        "causal_audio_improvement_verified":False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for arg in ("baseline-trace","baseline-report","baseline-binding",
                "baseline-nro","experimental-trace","experimental-report",
                "experimental-binding","experimental-nro"):
        parser.add_argument("--"+arg,type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    opts=parser.parse_args(argv)
    try:
        result=make_report(opts.baseline_trace,opts.baseline_report,
                           opts.baseline_binding,opts.baseline_nro,
                           opts.experimental_trace,opts.experimental_report,
                           opts.experimental_binding,opts.experimental_nro)
        with opts.out.open("x",encoding="ascii") as dest:
            dest.write(json.dumps(result,sort_keys=True)+"\n")
    except (OSError,ValueError,TypeError,KeyError,OverflowError,
            UnicodeError) as exc:
        print(json.dumps({
            "status":"INCONCLUSIVE_FROZEN_GUEST_ACK_CAPACITY_HYPOTHESES",
            "reason":type(exc).__name__,
            "real_host_ack_feedback_on_capacity_known":False,
            "causal_audio_improvement_verified":False},sort_keys=True))
        return 1
    print(json.dumps({
        "status":result["status"],
        "real_guest_baseline_pages":result["modes"][0]["guest_ack_discovery_pages"],
        "real_guest_extra_pages":result["modes"][1]["guest_ack_discovery_pages"],
        "causal_audio_improvement_verified":False},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
