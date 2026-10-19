#!/usr/bin/env python3
"""Controlled, ROM-free PCM resume-edge benchmark using the ACTUAL C ramp.

Unlike a playback evaluation, this tests exact sample mathematics for a
fixed 96-frame stereo attack and never records commercial ROM audio.
An edge can IMPROVE after silence while WORSENING a signal that was
already continuous. Both outcomes MUST be reported. The observations
are integer sample discontinuity proxies, NOT click audibility, DAC
behavior, actual console output, or causal latency measurements.
"""
import argparse
import ctypes
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

SCHEMA="dino-rom-free-resume-ramp-edge-benchmark-v1"
RATE=48000
STEREO=2
FRAMES=800
ATTACK=96
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"source"/"dino_pcm_resume_ramp.c"
TEST_CASES=("silence_to_loud", "already_continuous", "opposite_polarity",
            "zero_signal", "sine_zero_crossing")


def oracle_sample(value, frame_index):
    if type(value) is not int or not -32768<=value<=32767:
        raise ValueError("out-of-range signed PCM sample")
    if type(frame_index) is not int or not 0<=frame_index<ATTACK:
        raise ValueError("invalid attack frame")
    new=abs(value)*(frame_index+1)//ATTACK
    return -new if value<0 else new


def make_cases():
    result={}
    result["silence_to_loud"]=(
        (0,0),[30000,-24000]*FRAMES)
    result["already_continuous"]=(
        (30000,-24000),[30000,-24000]*FRAMES)
    result["opposite_polarity"]=(
        (-30000,24000),[30000,-24000]*FRAMES)
    result["zero_signal"]=(
        (0,0),[0,0]*FRAMES)
    samples=[]
    # Offline invented tone; no game/console-derived samples whatsoever.
    for i in range(FRAMES):
        s=round(22000*math.sin(2*math.pi*440*i/RATE))
        samples.extend([s,-s])
    result["sine_zero_crossing"]=((0,0),samples)
    return result


def compile_ramp(tmp):
    if not shutil.which("gcc"):
        raise ValueError("native host GCC is needed to verify the real C code")
    if SOURCE.is_symlink() or not SOURCE.is_file():
        raise ValueError("native ramp source is unavailable")
    binary=Path(tmp)/"dino-resume-edge.so"
    run=subprocess.run([
        "gcc","-std=c11","-O2","-Wall","-Wextra","-Werror",
        "-fPIC","-shared","-Isource",
        "source/dino_pcm_resume_ramp.c","-o",str(binary),
    ],cwd=ROOT,capture_output=True,text=True,timeout=25,check=False)
    if run.returncode:
        raise ValueError("native C ramp compilation failed: "+
                         run.stderr[-500:])
    library=ctypes.CDLL(str(binary))
    apply=library.dino_pcm_resume_ramp_apply
    apply.argtypes=[ctypes.POINTER(ctypes.c_int16),
                    ctypes.c_size_t,ctypes.c_size_t]
    apply.restype=ctypes.c_bool
    return apply


def edge_metric(previous,values):
    if len(previous)!=2 or len(values)!=2*FRAMES:
        raise ValueError("expected one stereo tick with previous frame")
    return max(abs(values[ch]-previous[ch]) for ch in range(2))


def attack_max_step(previous,values):
    if len(previous)!=2 or len(values)!=2*FRAMES:
        raise ValueError("invalid stereo data for derivative benchmark")
    result=0
    prior=previous
    for f in range(ATTACK):
        this=(values[2*f],values[2*f+1])
        result=max(result,max(abs(this[ch]-prior[ch]) for ch in range(2)))
        prior=this
    return result


def score(previous,original,shaped,case):
    if (case not in TEST_CASES or len(previous)!=STEREO or
        len(original)!=STEREO*FRAMES or len(shaped)!=STEREO*FRAMES):
        raise ValueError("incorrect bounded edge scenario")
    if any(type(x) is not int or not -32768<=x<=32767
           for x in (*previous,*original,*shaped)):
        raise ValueError("noncanonical signed PCM")
    if original[STEREO*ATTACK:]!=shaped[STEREO*ATTACK:]:
        raise ValueError("output beyond the 96-frame attack was modified")
    for f in range(ATTACK):
        for ch in (0,1):
            if shaped[2*f+ch]!=oracle_sample(original[2*f+ch],f):
                raise ValueError("compiled C does not match integer oracle")
    before=edge_metric(previous,original)
    after=edge_metric(previous,shaped)
    changed=sum(x!=y for x,y in zip(original,shaped))
    difference_energy=sum((x-y)**2 for x,y in zip(original,shaped))
    return {
        "case":case,
        "previous_stereo_frame":list(previous),
        "first_original_stereo_frame":original[:2],
        "first_shaped_stereo_frame":shaped[:2],
        "boundary_max_abs_sample_step_before":before,
        "boundary_max_abs_sample_step_after":after,
        "boundary_step_delta_after_minus_before":after-before,
        "max_sample_step_within_attack_including_boundary_before":
            attack_max_step(previous,original),
        "max_sample_step_within_attack_including_boundary_after":
            attack_max_step(previous,shaped),
        "changed_attack_samples":changed,
        "squared_sample_difference_sum":difference_energy,
        "unchanged_sample_count_after_attack":(FRAMES-ATTACK)*STEREO,
        "output_frame_count_before":FRAMES,
        "output_frame_count_after":FRAMES,
        "actual_c_ramp_matched_integer_oracle":True,
        "shaped_pcm_sha256":hashlib.sha256(struct.pack(
            "<"+str(len(shaped))+"h",*shaped)).hexdigest(),
        "boundary_discontinuity_improved":after<before,
        "boundary_discontinuity_worsened":after>before,
    }


def benchmark():
    cases=make_cases()
    if tuple(cases)!=TEST_CASES:
        raise ValueError("synthetic fixture order unexpectedly changed")
    profiles=[]
    with tempfile.TemporaryDirectory(prefix="dino-edge-math-") as tmp:
        apply=compile_ramp(tmp)
        for name,(previous,original) in cases.items():
            raw=(ctypes.c_int16*(FRAMES*STEREO))(*original)
            if not apply(raw,FRAMES,ATTACK):
                raise ValueError("real C ramp refused valid stereo PCM")
            shaped=list(raw)
            profiles.append(score(previous,original,shaped,name))
    if (not profiles[0]["boundary_discontinuity_improved"] or
        not profiles[1]["boundary_discontinuity_worsened"] or
        profiles[3]["boundary_max_abs_sample_step_after"]!=0):
        raise ValueError("benchmark controls failed to expose both effects")
    return {
        "schema":SCHEMA,
        "status":"ACTUAL_C_PCM_ATTACK_HAS_CONDITION_DEPENDENT_EDGE_TRADEOFF",
        "sample_rate_hz":RATE,
        "stereo_channels":STEREO,
        "pcm_frames_per_game_tick":FRAMES,
        "ramp_frames":ATTACK,
        "ramp_duration_ms_exact":2,
        "source":"compiled_unmodified_portable_C_ramp",
        "input_samples":"synthetic_rom_free_only",
        "profiles":profiles,
        "sample_math_and_tail_conservation_verified":True,
        "guaranteed_boundary_improvement":False,
        "host_audio_capture_performed":False,
        "guest_arm64_audio_output_measured":False,
        "physical_switch_speaker_audio_verified":False,
        "audible_click_reduction_verified":False,
        "causal_pcm_skip_reduction_verified":False,
        "production_enablement_recommended":False,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        result=benchmark()
        with args.out.open("x",encoding="ascii") as f:
            f.write(json.dumps(result,sort_keys=True)+"\n")
    except (OSError,ValueError,TypeError,OverflowError,UnicodeError,
            subprocess.SubprocessError) as exc:
        print(json.dumps({
            "status":"INCONCLUSIVE_RESUME_EDGE_BENCHMARK",
            "reason":type(exc).__name__,
            "production_enablement_recommended":False,
        },sort_keys=True))
        return 1
    print(json.dumps({
        "status":result["status"],
        "silence_to_loud_boundary_delta":result["profiles"][0][
            "boundary_step_delta_after_minus_before"],
        "already_continuous_boundary_delta":result["profiles"][1][
            "boundary_step_delta_after_minus_before"],
        "production_enablement_recommended":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
