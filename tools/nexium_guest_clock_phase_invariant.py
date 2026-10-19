#!/usr/bin/env python3
"""Prove 60-Hz accumulator consistency of NRO-attested guest frame clocks.

Given existing per-render-frame *capped* integer-nanosecond intervals d_i,
and game-step counts t_i, the scheduler uses exactly:
    carry_next = carry_previous + 60*d_i - 1_000_000_000*t_i.
There must exist ONE unknown initial integer carry from [0, 1e9-1]
that keeps every subsequent carry in that same range. We intersect the
start-phase constraints without guessing the first phase. This is an
arithmetic invariant of the observed 60-Hz *simulation* scheduler; it is
NOT a measurement of audio playback latency, host presentation timing, or
uncapped time. Zero-game-tick render iterations remain in the sequence.
"""
import argparse
import hashlib
import json
from pathlib import Path

SCHEMA = "dino-nexium-guest-60hz-clock-phase-invariant-v1"
DENOM = 1000000000
CLOCK_HZ = 60
MAX_FRAME_ROWS = 4096
MAX_NS = 250000000


def verify_phase(rows):
    """Exact O(n) interval intersection; rejects impossible real traces."""
    if type(rows) is not list or not 1 <= len(rows) <= MAX_FRAME_ROWS:
        raise ValueError("missing/unbounded guest frame interval sequence")
    low, high = 0, DENOM - 1
    cumulative = 0
    previous_id = None
    total_ticks = 0
    frames_with_no_game_tick = 0
    ceiling = 0
    for index, frame in enumerate(rows):
        if type(frame) is not dict or set(frame) != {
            "frame_id", "elapsed_ns_capped", "frame_game_ticks",
            "stress_game_ticks",
        }:
            raise ValueError("noncanonical guest render frame")
        if any(type(value) is not int for value in frame.values()):
            raise ValueError("noninteger clock witness")
        fid = frame["frame_id"]
        interval = frame["elapsed_ns_capped"]
        steps = frame["frame_game_ticks"]
        observed = frame["stress_game_ticks"]
        if (not 1 <= fid <= 0xffffffff or
            (previous_id is not None and fid != previous_id + 1) or
            not 0 <= interval <= MAX_NS or not 0 <= steps <= 15 or
            not 0 <= observed <= steps):
            raise ValueError("invalid capped clock or game-step count")
        previous_id = fid
        total_ticks += observed
        frames_with_no_game_tick += int(steps == 0)
        ceiling += int(interval == MAX_NS)
        cumulative += CLOCK_HZ * interval - DENOM * steps
        low = max(low, -cumulative)
        high = min(high, DENOM - 1 - cumulative)
        if low > high:
            raise ValueError(
                "no feasible 60Hz starting carry at observed frame "
                + str(index + 1)
            )
    return {
        "status": "EXACT_GUEST_60HZ_CARRY_START_INTERVAL_EXISTS",
        "observed_render_iterations": len(rows),
        "observed_stress_game_ticks": total_ticks,
        "initial_carry_min_inclusive": low,
        "initial_carry_max_inclusive": high,
        "initial_carry_feasible_integer_count": high - low + 1,
        "final_carry_min_inclusive": low + cumulative,
        "final_carry_max_inclusive": high + cumulative,
        "final_carry_delta_integer_units": cumulative,
        "zero_game_tick_render_iterations": frames_with_no_game_tick,
        "existing_scheduler_250ms_clamped_rows": ceiling,
        "frame_clock_cap_ns": MAX_NS,
        "simulation_clock_hz": CLOCK_HZ,
        "initial_phase_was_measured_directly": False,
        "frame_intervals_are_previously_capped": True,
        "unclamped_elapsed_host_time_verified": False,
        "audio_service_release_timestamps_verified": False,
        "physical_speaker_audio_latency_verified": False,
    }


def make_report(base_clock, base_trace, base_report, base_binding, base_nro,
                extra_clock, extra_trace, extra_report, extra_binding,
                extra_nro):
    if any(not Path(p).is_file() for p in (
        base_clock, base_trace, base_report, base_binding, base_nro,
        extra_clock, extra_trace, extra_report, extra_binding, extra_nro,
    )):
        raise ValueError("missing NRO-bound clock/guest report inputs")
    try:
        from tools import verify_nexium_guest_frame_clock as witness
    except ImportError:
        import verify_nexium_guest_frame_clock as witness
    verified = witness.make_report(
        base_clock, base_trace, base_report, base_binding, base_nro,
        extra_clock, extra_trace, extra_report, extra_binding, extra_nro,
    )
    results = []
    for path, original in zip((base_clock, extra_clock), verified["profiles"]):
        raw, rows = witness.read_clock(path)
        if hashlib.sha256(raw).hexdigest() != original["guest_clock_sha256"]:
            raise ValueError("clock CSV does not match NRO-bound guest witness")
        phase = verify_phase(rows)
        if (phase["observed_render_iterations"] != original["frame_rows"] or
            phase["observed_stress_game_ticks"] != 900 or
            phase["zero_game_tick_render_iterations"] !=
                original["zero_game_tick_render_iterations"] or
            phase["existing_scheduler_250ms_clamped_rows"] !=
                original["capped_250ms_interval_rows"]):
            raise ValueError("60Hz phase envelope not bound to guest counters")
        results.append({
            "mode": original["mode"],
            "guest_clock_sha256": original["guest_clock_sha256"],
            "guest_nro_sha256": original["bound_guest_nro_sha256"],
            "guest_stress_report_sha256": original["guest_stress_report_sha256"],
            **phase,
        })
    return {
        "schema": SCHEMA,
        "status": "BOTH_NRO_BOUND_GUEST_60HZ_CARRY_PHASES_FEASIBLE",
        "profiles": results,
        "unknown_initial_carry_interval_is_not_timestamp": True,
        "matching_host_conditions_verified": False,
        "physical_switch_audio_verified": False,
        "causal_audio_improvement_verified": False,
        "production_frame_scheduler_modified": False,
        "production_pcm_queue_modified": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in (
        "baseline-clock", "baseline-trace", "baseline-report",
        "baseline-binding", "baseline-nro", "experimental-clock",
        "experimental-trace", "experimental-report",
        "experimental-binding", "experimental-nro",
    ):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = make_report(
            args.baseline_clock, args.baseline_trace, args.baseline_report,
            args.baseline_binding, args.baseline_nro,
            args.experimental_clock, args.experimental_trace,
            args.experimental_report, args.experimental_binding,
            args.experimental_nro,
        )
        with args.out.open("x", encoding="ascii") as out:
            out.write(json.dumps(result, sort_keys=True) + "\n")
    except (OSError, ValueError, KeyError, TypeError, OverflowError,
            UnicodeError) as exc:
        print(json.dumps({
            "status": "INCONCLUSIVE_GUEST_60HZ_CARRY_PHASE",
            "reason": type(exc).__name__,
            "causal_audio_improvement_verified": False,
            "physical_switch_audio_verified": False,
        }, sort_keys=True))
        return 1
    print(json.dumps({
        "status": result["status"],
        "baseline_initial_phase_feasible_integer_count": result[
            "profiles"][0]["initial_carry_feasible_integer_count"],
        "extra_poll_initial_phase_feasible_integer_count": result[
            "profiles"][1]["initial_carry_feasible_integer_count"],
        "physical_switch_audio_verified": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
