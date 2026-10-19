#!/usr/bin/env python3
"""ROM-free exact arithmetic of guest PCM skips by frame-batch position.

Two independently NRO/SHA-bound NeXium guest runs are NOT a randomized,
host-matched experiment. An exact three-stratum Kitagawa-style arithmetic
identity separates changes in observed exposure frequencies ("single",
"first", "later" simulation ticks within render frames) from changes in
observed skip rates within those phases. Neither component is a *causal*
effect of frame batching or of enabling the extra poll. Use Fraction to
avoid rounding, and refuse standardization when either run has no exposure
in a phase. Input timestamps are only simulation ticks.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path

try:
    from tools import verify_nexium_audio_ack_tick_trace as ack
    from tools import verify_nexium_audio_paired_artifacts as paired
except ImportError:
    import verify_nexium_audio_ack_tick_trace as ack
    import verify_nexium_audio_paired_artifacts as paired

SCHEMA="dino-guest-ack-frame-phase-standardization-v1"
PHASES=("single","first","later")
TOTAL_TICKS=900


def as_fraction(number):
    if type(number) is not Fraction:
        raise ValueError("exact rational diagnostic expected")
    return {"numerator":number.numerator,"denominator":number.denominator}


def phase_for(row):
    if type(row) is not dict:
        raise ValueError("invalid recorded ACK tick")
    batch=row["batch_size"]
    position=row["batch_position"]
    if (type(batch) is not int or not 1<=batch<=15 or
            type(position) is not int or not 0<=position<batch):
        raise ValueError("invalid frame batching classification")
    return "single" if batch==1 else ("first" if position==0 else "later")


def phase_counts(rows):
    if type(rows) is not list or not 1<=len(rows)<=TOTAL_TICKS:
        raise ValueError("unbounded guest tick list")
    phases={phase:{"ticks":0,"skipped_pcm":0,"ack_pages":0}
            for phase in PHASES}
    for row in rows:
        phase=phase_for(row)
        skip=row["skipped"]
        release=row["released"]
        if (type(skip) is not int or skip not in (0,1) or
                type(release) is not int or not 0<=release<=2):
            raise ValueError("noncanonical guest audio phase counters")
        group=phases[phase]
        group["ticks"]+=1
        group["skipped_pcm"]+=skip
        group["ack_pages"]+=release
    if sum(g["ticks"] for g in phases.values())!=len(rows):
        raise ValueError("guest frame-position exposure conservation failed")
    return phases


def exact_skip_decomposition(base,extra):
    """Symmetric, descriptive split; exact sum equals observed skip delta.

    dS = sum((n1-n0)*(r1+r0)/2 + (r1-r0)*(n1+n0)/2),
    where r=s/n and n are counted simulation-tick exposures, NOT
    controlled or independently assigned experimental conditions.
    """
    if (type(base) is not dict or type(extra) is not dict or
            set(base)!=set(PHASES) or set(extra)!=set(PHASES)):
        raise ValueError("all three frame-batch phase strata required")
    totals={}
    for mode,groups in (("baseline",base),("extra-poll",extra)):
        n=s=a=0
        for phase in PHASES:
            row=groups[phase]
            if type(row) is not dict or set(row)!={"ticks","skipped_pcm","ack_pages"}:
                raise ValueError("noncanonical frame phase counters")
            count,skip,pages=row["ticks"],row["skipped_pcm"],row["ack_pages"]
            if (any(type(v) is not int for v in (count,skip,pages)) or
                    count<0 or not 0<=skip<=count or not 0<=pages<=2*count):
                raise ValueError("impossible phase exposure/skips/ACK pages")
            n+=count;s+=skip;a+=pages
        if not 1<=n<=TOTAL_TICKS:
            raise ValueError("invalid total guest exposure")
        totals[mode]={"ticks":n,"skipped_pcm":s,"released_pages":a}
    if totals["baseline"]["ticks"]!=totals["extra-poll"]["ticks"]:
        raise ValueError("exposure horizons do not match")
    delta=totals["extra-poll"]["skipped_pcm"]-totals["baseline"]["skipped_pcm"]
    result={
        "baseline":base,
        "extra_poll":extra,
        "totals":totals,
        "observed_extra_minus_baseline_skipped_pcm":delta,
        "causal_frame_pacing_explanation_verified":False,
        "causal_audio_mode_effect_verified":False,
        "matched_guest_service_timing_verified":False,
        "arithmetic_decomposition_not_statistical_adjustment":True,
    }
    missing=[phase for phase in PHASES
             if base[phase]["ticks"]==0 or extra[phase]["ticks"]==0]
    if missing:
        result.update({
            "status":"INCOMPARABLE_FRAME_PHASE_WITHOUT_BOTH_EXPOSURES",
            "missing_common_phase_exposure":missing,
            "exact_skip_count_identity":None,
        })
        return result
    exposure=Fraction(0)
    conditional=Fraction(0)
    per_phase=[]
    for phase in PHASES:
        b,e=base[phase],extra[phase]
        n0,n1=b["ticks"],e["ticks"]
        r0=Fraction(b["skipped_pcm"],n0)
        r1=Fraction(e["skipped_pcm"],n1)
        exposure_component=Fraction(n1-n0,2)*(r0+r1)
        conditional_component=Fraction(n1+n0,2)*(r1-r0)
        per_phase.append({
            "phase":phase,
            "baseline_skip_rate_exact":as_fraction(r0),
            "extra_skip_rate_exact":as_fraction(r1),
            "exposure_arithmetic_component":as_fraction(exposure_component),
            "within_phase_rate_arithmetic_component":
                as_fraction(conditional_component),
        })
        exposure+=exposure_component
        conditional+=conditional_component
    if exposure+conditional!=Fraction(delta):
        raise ValueError("skip-change decomposition failed exact identity")
    result.update({
        "status":"EXACT_FRAME_PHASE_SKIP_IDENTITY_NONCAUSAL",
        "missing_common_phase_exposure":[],
        "per_phase":per_phase,
        "arithmetic_exposure_component":as_fraction(exposure),
        "arithmetic_within_phase_rate_component":as_fraction(conditional),
        "exact_skip_count_identity":True,
        "common_phases_observed":True,
    })
    return result


def make_report(base_trace,base_report,base_binding,base_nro,
                extra_trace,extra_report,extra_binding,extra_nro):
    binding=paired.compare(base_report,base_binding,extra_report,
                           extra_binding,base_nro,extra_nro)
    reports=[]
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
            raise ValueError("mode/NRO-bound guest tick evidence changed")
        if len(rows)!=TOTAL_TICKS:
            raise ValueError("actual guest tick count mismatch")
        groups=phase_counts(rows)
        if (sum(g["skipped_pcm"] for g in groups.values())!=
                sum(w["skipped"] for w in witness["ack_discovery_windows"]) or
                sum(g["ack_pages"] for g in groups.values())!=
                witness["ack_pages_observed"]):
            raise ValueError("unreconciled guest frame phase counters")
        reports.append({
            "mode":mode,"guest_ack_csv_sha256":witness["guest_ack_csv_sha256"],
            "guest_stress_report_sha256":digest,"guest_nro_sha256":nro_digest,
            "group_counts":groups,
            "windows":[phase_counts(rows[i:i+150]) for i in range(0,900,150)],
        })
    full=exact_skip_decomposition(
        reports[0]["group_counts"],reports[1]["group_counts"])
    windows=[]
    for i in range(6):
        item=exact_skip_decomposition(
            reports[0]["windows"][i],reports[1]["windows"][i])
        windows.append({"tick_start":i*150,"tick_end":(i+1)*150,**item})
    if (sum(w["observed_extra_minus_baseline_skipped_pcm"] for w in windows)!=
            full["observed_extra_minus_baseline_skipped_pcm"]):
        raise ValueError("guest window skip delta does not reconcile")
    return {
        "schema":SCHEMA,
        "status":"NRO_BOUND_GUEST_PHASE_STRATIFIED_SKIP_DIAGNOSTIC_ONLY",
        "guest_modes":reports,
        "whole_900tick_arithmetic":full,
        "six_150tick_arithmetic_windows":windows,
        "mode_nro_sha256_verified":True,
        "render_frame_exposure_mismatch_diagnostic_only":True,
        "arithmetic_terms_are_not_causal_effects":True,
        "within_phase_service_policy_held_fixed":False,
        "matched_host_conditions_verified":False,
        "matched_guest_frame_pacing_verified":False,
        "original_arcade_audio_verified":False,
        "physical_switch_audio_verified":False,
        "causal_audio_improvement_verified":False,
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
        result=make_report(args.baseline_trace,args.baseline_report,
                           args.baseline_binding,args.baseline_nro,
                           args.experimental_trace,args.experimental_report,
                           args.experimental_binding,args.experimental_nro)
        with args.out.open("x",encoding="ascii") as stream:
            stream.write(json.dumps(result,sort_keys=True)+"\n")
    except (OSError,ValueError,TypeError,KeyError,OverflowError,
            UnicodeError) as exc:
        print(json.dumps({
            "status":"INCONCLUSIVE_FRAME_PHASE_SKIP_DIAGNOSTIC",
            "reason":type(exc).__name__,
            "causal_audio_improvement_verified":False,
            "matched_guest_frame_pacing_verified":False,
        },sort_keys=True))
        return 1
    print(json.dumps({
        "status":result["status"],
        "observed_extra_minus_baseline_skips":result[
            "whole_900tick_arithmetic"][
                "observed_extra_minus_baseline_skipped_pcm"],
        "complete_exposure_stratification":result[
            "whole_900tick_arithmetic"]["exact_skip_count_identity"] is True,
        "causal_audio_improvement_verified":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
