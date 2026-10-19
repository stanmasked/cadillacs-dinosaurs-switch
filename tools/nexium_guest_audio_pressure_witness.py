#!/usr/bin/env python3
"""ROM-free admission-pressure accounting for two *real* guest ACK traces.

A PCM attempt is skipped in the current depth-two queue precisely when
the pre-admission poll still finds a full queue. Actual libnx service
arrival times are UNKNOWN. Extra mid-batch poll returns cannot identify
their own counterfactual benefit because guest scheduling may change.

Require independent NRO/mode/SHA evidence before accepting any published
report. No PCM audio, ROM, arbitrary libnx polling, or timing changes.
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

SCHEMA = "dino-nro-bound-guest-queue-pressure-witness-v1"
CATEGORIES = ("single", "first", "later")


def fresh():
    return dict(ticks=0, full_before_poll=0, recovered_when_full=0,
                unrecovered_full=0, skipped=0, admitted=0,
                returned_pages=0, discovery_ticks=0,
                extra_poll_calls=0, extra_poll_pages=0,
                extra_poll_return_ticks=0)


def add(group, r):
    group["ticks"] += 1
    group["full_before_poll"] += r["pre_poll_full"]
    group["recovered_when_full"] += r["pre_poll_recovered"]
    group["unrecovered_full"] += (
        r["pre_poll_full"] - r["pre_poll_recovered"])
    group["skipped"] += r["skipped"]
    group["admitted"] += r["submitted"]
    group["returned_pages"] += r["released"]
    group["discovery_ticks"] += int(r["released"] > 0)
    group["extra_poll_calls"] += r["mid_calls"]
    group["extra_poll_pages"] += r["mid_released"]
    group["extra_poll_return_ticks"] += int(r["mid_released"] > 0)


def summarize(rows, mode):
    if mode not in ("baseline", "extra-poll"):
        raise ValueError("selected guest NRO audio mode unknown")
    if type(rows) is not list or len(rows) != 900:
        raise ValueError("exact 900-tick guest pressure trace required")
    combined = fresh()
    phases = {k: fresh() for k in CATEGORIES}
    windows = []
    current = fresh()
    longest_no_return = longest_skips = 0
    no_return_run = skips_run = 0
    for index, r in enumerate(rows):
        if type(r) is not dict:
            raise ValueError("guest pressure row missing")
        keys = ("pre_poll_full", "pre_poll_recovered", "skipped",
                "submitted", "released", "pending",
                "mid_calls", "mid_released", "batch_size", "batch_position")
        if any(type(r.get(k)) is not int for k in keys):
            raise ValueError("noncanonical guest PCM pressure counter")
        full = r["pre_poll_full"]
        recovered = r["pre_poll_recovered"]
        release = r["released"]
        skipped = r["skipped"]
        submitted = r["submitted"]
        calls = r["mid_calls"]
        mid_return = r["mid_released"]
        size = r["batch_size"]
        pos = r["batch_position"]
        if (full not in (0,1) or recovered not in (0,1) or
            skipped not in (0,1) or submitted not in (0,1) or
            not 0 <= release <= 2 or not 1 <= r["pending"] <= 2 or
            calls not in (0,1) or not 0 <= mid_return <= release or
            not 1 <= size <= 15 or not 0 <= pos < size):
            raise ValueError("impossible queue pressure or render position")
        if ((recovered != int(full == 1 and release > 0)) or
            (skipped != full - recovered) or
            (submitted != 1 - skipped) or
            (skipped and r["pending"] != 2) or
            (mid_return and calls != 1) or
            (calls and pos == 0) or
            (mode == "baseline" and (calls or mid_return))):
            raise ValueError("guest full/recovery/drop identity violated")
        phase = "single" if size == 1 else ("first" if pos == 0 else "later")
        for group in (combined, current, phases[phase]):
            add(group, r)
        no_return_run = no_return_run + 1 if release == 0 else 0
        skips_run = skips_run + 1 if skipped else 0
        longest_no_return = max(longest_no_return, no_return_run)
        longest_skips = max(longest_skips, skips_run)
        if (index + 1) % 150 == 0:
            windows.append({"tick_start": index - 149,
                            "tick_end": index + 1, **current})
            current = fresh()
    if (combined["ticks"] != 900 or
        combined["unrecovered_full"] != combined["skipped"] or
        combined["recovered_when_full"] +
            combined["unrecovered_full"] != combined["full_before_poll"]):
        raise ValueError("unexpected guest pressure accounting")
    if combined["admitted"] + combined["skipped"] != 900:
        raise ValueError("PCM attempts lost in pressure ledger")
    for field in combined:
        if (sum(v[field] for v in phases.values()) != combined[field] or
            sum(v[field] for v in windows) != combined[field]):
            raise ValueError("phase/window queue pressure totals disagree")
    return {
        "status": "GUEST_DEPTH_TWO_PRESSURE_DROP_IDENTITY_WITNESSED",
        "mode": mode,
        "totals": combined,
        "by_game_tick_position": phases,
        "six_150tick_windows": windows,
        "longest_consecutive_no_return_ticks": longest_no_return,
        "longest_consecutive_skipped_pcm_ticks": longest_skips,
        "all_skips_are_full_queue_without_observed_recovery": True,
        "extra_poll_return_is_not_proof_of_avoided_skip": True,
        "libnx_audout_service_release_time_known": False,
        "causal_mid_batch_poll_benefit_verified": False,
        "actual_speaker_latency_verified": False,
    }


def make_report(base_trace, base_report, base_binding, base_nro,
                extra_trace, extra_report, extra_binding, extra_nro):
    bound = paired.compare(base_report, base_binding, extra_report,
                           extra_binding, base_nro, extra_nro)
    profiles = []
    for mode, trace, report, sha, nro_sha in (
        ("baseline", base_trace, base_report,
         bound["baseline_report_sha256"], bound["baseline_guest_nro_sha256"]),
        ("extra-poll", extra_trace, extra_report,
         bound["experimental_report_sha256"],
         bound["experimental_guest_nro_sha256"]),
    ):
        witness = ack.verify(trace, report, mode)
        raw, rows = ack.parse_csv(trace)
        if (hashlib.sha256(raw).hexdigest() !=
                witness["guest_ack_csv_sha256"] or
            witness["guest_stress_report_sha256"] != sha):
            raise ValueError("guest pressure ledger not NRO/report bound")
        profile = summarize(rows, mode)
        counters = profile["totals"]
        if (counters["returned_pages"] != witness["ack_pages_observed"] or
            counters["skipped"] != bound["descriptive_comparison"][
                "baseline" if mode == "baseline" else "experimental"
            ]["audio_blocks_skipped"]):
            raise ValueError("guest pressure ledger counters mismatch")
        profiles.append({
            **profile,
            "guest_ack_csv_sha256": witness["guest_ack_csv_sha256"],
            "bound_report_sha256": sha,
            "bound_guest_nro_sha256": nro_sha,
        })
    return {
        "schema": SCHEMA,
        "status": "BOTH_NRO_BOUND_GUEST_PRESSURE_IDENTITIES_WITNESSED",
        "profiles": profiles,
        "recorded_guest_queue_depth": 2,
        "queue_depth_altered_in_production": False,
        "host_conditions_matched": False,
        "audio_service_arrival_timestamps_available": False,
        "direct_extra_poll_causal_savings_identified": False,
        "physical_switch_audio_verified": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for key in ("baseline-trace", "baseline-report", "baseline-binding",
                "baseline-nro", "experimental-trace", "experimental-report",
                "experimental-binding", "experimental-nro"):
        p.add_argument("--" + key, required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    a = p.parse_args(argv)
    try:
        result = make_report(a.baseline_trace, a.baseline_report,
                             a.baseline_binding, a.baseline_nro,
                             a.experimental_trace, a.experimental_report,
                             a.experimental_binding, a.experimental_nro)
        with a.out.open("x", encoding="ascii") as f:
            f.write(json.dumps(result, sort_keys=True) + "\n")
    except (OSError, ValueError, KeyError, TypeError, OverflowError,
            UnicodeError) as exc:
        print(json.dumps({
            "status": "INCONCLUSIVE_GUEST_QUEUE_PRESSURE_IDENTITY",
            "reason": type(exc).__name__,
            "direct_extra_poll_causal_savings_identified": False,
        }, sort_keys=True))
        return 1
    print(json.dumps({
        "status": result["status"],
        "baseline_pcm_skips": result["profiles"][0]["totals"]["skipped"],
        "extra_pcm_skips": result["profiles"][1]["totals"]["skipped"],
        "direct_extra_poll_causal_savings_identified": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
