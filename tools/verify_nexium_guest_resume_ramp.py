#!/usr/bin/env python3
"""Verify opt-in PCM ramp use in an ACTUAL ROM-free NeXium guest NRO.

The file is written by the NRO after 900 game ticks. It proves only
guest-side one-shot PCM output processing/diagnostic counters, not
speaker sound, latency, fewer queue skips or audible click reduction.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

try:
    from tools import verify_nexium_audio_ack_tick_trace as ack
    from tools import verify_nexium_audio_mode_binding as mode_binding
except ImportError:
    import verify_nexium_audio_ack_tick_trace as ack
    import verify_nexium_audio_mode_binding as mode_binding

COLUMNS = ("sampled_ticks", "applied_start", "applied_end",
           "full_skips_start", "full_skips_end",
           "pending_at_start", "pending_at_end")
MARKER = b"cadillacs-guest-resume-ramp.csv"
SCHEMA = "dino-nexium-nro-guest-optin-pcm-resume-ramp-v1"


def parse(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or not 32 <= p.stat().st_size <= 512:
        raise ValueError("missing or oversized guest resume ramp witness")
    data = p.read_bytes()
    if len(data) != p.stat().st_size:
        raise ValueError("ramp witness changed during read")
    try:
        inp = csv.DictReader(data.decode("ascii").splitlines(), strict=True)
        if tuple(inp.fieldnames or ()) != COLUMNS:
            raise ValueError("wrong resume ramp evidence columns")
        values = list(inp)
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("invalid ramp CSV") from exc
    if len(values) != 1 or None in values[0] or set(values[0]) != set(COLUMNS):
        raise ValueError("expected exactly one canonical ramp witness")
    row = {}
    for key in COLUMNS:
        value = values[0][key]
        if (type(value) is not str or not value.isascii() or
            not value.isdecimal() or len(value) > 10 or
            (len(value) > 1 and value[0] == "0")):
            raise ValueError("noncanonical guest resume counter")
        row[key] = int(value)
        if row[key] > 0xffffffff:
            raise ValueError("counter over uint32")
    return data, row


def check(row, ticks):
    if type(row) is not dict or set(row) != set(COLUMNS):
        raise ValueError("missing ramp counters")
    if any(type(v) is not int or v < 0 or v > 0xffffffff
           for v in row.values()):
        raise ValueError("noninteger or out-of-range ramp counter")
    if type(ticks) is not list or len(ticks) != 900:
        raise ValueError("requires 900 exact guest PCM attempts")
    if (row["sampled_ticks"] != 900 or
        row["pending_at_start"] not in (0, 1) or
        row["pending_at_end"] not in (0, 1)):
        raise ValueError("invalid guest stress window bounds")
    if (row["applied_end"] < row["applied_start"] or
        row["full_skips_end"] < row["full_skips_start"]):
        raise ValueError("ramp or full-queue counter reversed")
    pending = bool(row["pending_at_start"])
    applied = 0
    skips = 0
    for t in ticks:
        if (type(t) is not dict or
            type(t.get("skipped")) is not int or
            type(t.get("submitted")) is not int or
            t["skipped"] not in (0, 1) or
            t["submitted"] not in (0, 1) or
            t["skipped"] + t["submitted"] != 1):
            raise ValueError("noncanonical actual guest admission row")
        if t["skipped"]:
            skips += 1
            pending = True
        elif pending:
            applied += 1
            pending = False
    if (row["full_skips_end"] - row["full_skips_start"] != skips or
        row["applied_end"] - row["applied_start"] != applied or
        row["pending_at_end"] != int(pending)):
        raise ValueError("real guest ramp state not aligned with 900 PCM ticks")
    # A skip at the very last measured tick has no later admission.
    # It must leave the one-shot marker pending, not invent an attack.
    return {
        "measured_pcm_ticks": 900,
        "full_queue_pcm_skips": skips,
        "ramp_applications_inside_window": applied,
        "ramp_pending_at_window_start": row["pending_at_start"],
        "ramp_pending_at_window_end": row["pending_at_end"],
        "audio_block_requeue_count": 0,
        "expected_from_exact_guest_pcm_admissions": True,
        "speaker_click_reduction_verified": False,
        "physical_switch_audio_latency_verified": False,
        "causal_pcm_skip_reduction_verified": False,
    }


def verify(ramp_path, trace_path, report_path, nro_path):
    mode = mode_binding.attest("baseline", report_path, nro_path)
    if (mode["selected_mode"] != "baseline" or
        mode["guest_simulation_ticks"] != 900 or
        mode["guest_poll_enabled"]):
        raise ValueError("not the selected baseline-mode ROM-free NRO")
    nro = Path(nro_path)
    if MARKER not in nro.read_bytes():
        raise ValueError("opt-in guest ramp code path absent from NRO")
    witness = ack.verify(trace_path, report_path, "baseline")
    raw, ticks = ack.parse_csv(trace_path)
    if (hashlib.sha256(raw).hexdigest() != witness["guest_ack_csv_sha256"] or
        witness["guest_stress_report_sha256"] != mode["guest_report_sha256"]):
        raise ValueError("guest clock or stress report not source-bound")
    ramp_raw, row = parse(ramp_path)
    result = check(row, ticks)
    if result["full_queue_pcm_skips"] != sum(
            t["skipped"] for t in ticks):
        raise ValueError("PCM sample loss not conserved")
    return {
        "schema": SCHEMA,
        "status": "REAL_GUEST_OPTIN_PCM_RAMP_EXACT_ADMISSION_STATE_WITNESSED",
        "selected_guest_audio_mode": "baseline",
        "optin_ramp_witness_sha256": hashlib.sha256(ramp_raw).hexdigest(),
        "guest_ack_csv_sha256": witness["guest_ack_csv_sha256"],
        "guest_report_sha256": mode["guest_report_sha256"],
        "guest_nro_sha256": mode["guest_nro_sha256"],
        **result,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("ramp", "trace", "report", "nro", "out"):
        p.add_argument("--" + name, required=True, type=Path)
    a = p.parse_args(argv)
    try:
        result = verify(a.ramp, a.trace, a.report, a.nro)
        with a.out.open("x", encoding="ascii") as f:
            f.write(json.dumps(result, sort_keys=True) + "\n")
    except (ValueError, TypeError, OSError, KeyError, OverflowError,
            UnicodeError) as exc:
        print(json.dumps({
            "status": "INCONCLUSIVE_GUEST_OPTIN_PCM_RESUME_RAMP",
            "reason": type(exc).__name__,
            "speaker_click_reduction_verified": False,
        }, sort_keys=True))
        return 1
    print(json.dumps({
        "status": result["status"],
        "full_queue_pcm_skips": result["full_queue_pcm_skips"],
        "ramp_applications_inside_window":
            result["ramp_applications_inside_window"],
        "speaker_click_reduction_verified": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
