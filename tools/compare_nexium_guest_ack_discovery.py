#!/usr/bin/env python3
"""ROM-free, descriptive profile of bound NeXium guest ACK-discovery traces.

Runs *after* independent raw-900-tick validators and mode/NRO SHA binding.
ACK discovery at a simulated game tick is not the instant the audio service
released PCM, real-world playback latency or comparable host conditions.
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

SCHEMA="dino-nexium-bound-guest-ack-discovery-profile-v1"
GROUPS=("single","first","later")


def longest(predicate, rows):
    length=maximum=0
    for row in rows:
        if predicate(row):
            length+=1
            maximum=max(maximum,length)
        else:
            length=0
    return maximum


def summarize(rows):
    """Only call on a validated exact 900-tick trace; use no external timing."""
    if type(rows) is not list or len(rows)!=ack.MAX_TICKS:
        raise ValueError("expected 900 guest tick entries")
    totals=[]
    for k in range(0,900,150):
        chunk=rows[k:k+150]
        phases={}
        for phase in GROUPS:
            selection=[r for r in chunk if (
                "single" if r["batch_size"]==1 else
                ("first" if r["batch_position"]==0 else "later"))==phase]
            phases[phase]={
                "simulation_ticks":len(selection),
                "release_pages":sum(r["released"] for r in selection),
                "ack_discovery_ticks":sum(r["released"]>0 for r in selection),
                "skipped_blocks":sum(r["skipped"] for r in selection),
            }
        totals.append({
            "tick_start":k,"tick_end":k+150,
            "released_pages":sum(r["released"] for r in chunk),
            "ack_discovery_ticks":sum(r["released"]>0 for r in chunk),
            "max_consecutive_ticks_without_ack_discovery":
                longest(lambda r:r["released"]==0,chunk),
            "max_consecutive_skipped_pcm_ticks":
                longest(lambda r:r["skipped"]==1,chunk),
            "phases":phases,
        })
    out={
        "simulated_ticks":900,
        "ack_discovery_ticks":sum(r["released"]>0 for r in rows),
        "one_page_discovery_ticks":sum(r["released"]==1 for r in rows),
        "two_page_discovery_ticks":sum(r["released"]==2 for r in rows),
        "zero_page_discovery_ticks":sum(r["released"]==0 for r in rows),
        "released_pages":sum(r["released"] for r in rows),
        "submitted_blocks":sum(r["submitted"] for r in rows),
        "skipped_blocks":sum(r["skipped"] for r in rows),
        "mid_batch_extra_poll_calls":sum(r["mid_calls"] for r in rows),
        "mid_batch_extra_poll_returned_pages":sum(
            r["mid_released"] for r in rows),
        "max_consecutive_ticks_without_ack_discovery":
            longest(lambda r:r["released"]==0,rows),
        "max_consecutive_skipped_pcm_ticks":
            longest(lambda r:r["skipped"]==1,rows),
        "windows":totals,
        "exact_service_release_timestamps_available":False,
        "actual_speaker_audio_latency_verified":False,
    }
    if (out["ack_discovery_ticks"]!=
        out["one_page_discovery_ticks"]+out["two_page_discovery_ticks"] or
        out["zero_page_discovery_ticks"]+out["ack_discovery_ticks"]!=900 or
        out["released_pages"]!=out["one_page_discovery_ticks"]+
        2*out["two_page_discovery_ticks"] or
        out["submitted_blocks"]+out["skipped_blocks"]!=900):
        raise ValueError("guest ACK timeline conservation failed")
    for window in totals:
        if (sum(x["simulation_ticks"] for x in window["phases"].values())!=150 or
            sum(x["release_pages"] for x in window["phases"].values())!=
            window["released_pages"]):
            raise ValueError("ACK phase/window totals do not reconcile")
    return out


def compare(base_trace,base_report,base_binding,base_nro,
            extra_trace,extra_report,extra_binding,extra_nro):
    # Stronger than comparing CSV totals: both real guest NROs have
    # distinct validated SHA-256 bindings and valid 900-tick stress reports.
    binding=paired.compare(base_report,base_binding,extra_report,
                           extra_binding,base_nro,extra_nro)
    results=[]
    for mode,trace,report,expected_digest in (
        ("baseline",base_trace,base_report,binding["baseline_report_sha256"]),
        ("extra-poll",extra_trace,extra_report,
         binding["experimental_report_sha256"]),
    ):
        verifier=ack.verify(trace,report,mode)
        if verifier["guest_stress_report_sha256"]!=expected_digest:
            raise ValueError("ACK trace is not bound to approved guest report")
        raw,rows=ack.parse_csv(trace)
        if hashlib.sha256(raw).hexdigest()!=verifier["guest_ack_csv_sha256"]:
            raise ValueError("guest tick source changed during validation")
        profile=summarize(rows)
        if (profile["released_pages"]!=verifier["ack_pages_observed"] or
            profile["ack_discovery_ticks"]!=verifier["ack_discovery_ticks"] or
            profile["skipped_blocks"]!=
            binding["descriptive_comparison"][
                "baseline" if mode=="baseline" else "experimental"
            ]["audio_blocks_skipped"]):
            raise ValueError("per-tick guest profile contradicts NRO witness")
        for window,old in zip(profile["windows"],
                              verifier["ack_discovery_windows"]):
            if (window["released_pages"]!=old["released_pages"] or
                window["ack_discovery_ticks"]!=old["ack_discovery_ticks"] or
                sum(x["skipped_blocks"]
                    for x in window["phases"].values())!=old["skipped"]):
                raise ValueError("guest ACK profile window mismatch")
        results.append({
            "selected_mode":mode,
            "bound_guest_nro_sha256":(
                binding["baseline_guest_nro_sha256"] if mode=="baseline"
                else binding["experimental_guest_nro_sha256"]),
            "guest_ack_csv_sha256":verifier["guest_ack_csv_sha256"],
            "guest_stress_report_sha256":expected_digest,
            **profile,
        })
    return {
        "schema":SCHEMA,
        "status":"NRO_BOUND_ACK_DISCOVERY_DESCRIPTIVE_PROFILE_ONLY",
        "profiles":results,
        "host_conditions_matched_verified":False,
        "six_window_batch_exposure_matched_verified":
            binding["window_skip_diagnostics"]["matched_six_window_batch_exposure"],
        "causal_extra_poll_benefit_verified":False,
        "causal_audio_improvement_verified":False,
        "physical_switch_audio_verified":False,
        "exact_service_release_timestamps_available":False,
        "speaker_latency_verified":False,
        "original_arcade_audio_verified":False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for item in ("baseline-trace","baseline-report","baseline-binding",
                 "baseline-nro","experimental-trace","experimental-report",
                 "experimental-binding","experimental-nro"):
        parser.add_argument("--"+item,required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        result=compare(args.baseline_trace,args.baseline_report,
                       args.baseline_binding,args.baseline_nro,
                       args.experimental_trace,args.experimental_report,
                       args.experimental_binding,args.experimental_nro)
        with args.out.open("x",encoding="ascii") as stream:
            stream.write(json.dumps(result,sort_keys=True)+"\n")
    except (OSError,ValueError,TypeError,KeyError,OverflowError,
            UnicodeError) as exc:
        print(json.dumps({
            "status":"INCONCLUSIVE_GUEST_ACK_DISCOVERY_PROFILE",
            "reason":type(exc).__name__,
            "causal_audio_improvement_verified":False,
            "physical_switch_audio_verified":False},sort_keys=True))
        return 1
    print(json.dumps({
        "status":result["status"],
        "baseline_released_pages":result["profiles"][0]["released_pages"],
        "experimental_released_pages":result["profiles"][1]["released_pages"],
        "host_conditions_matched_verified":False,
        "causal_audio_improvement_verified":False},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
