#!/usr/bin/env python3
"""ROM-free gate-vs-fixed-attack analysis with the actual native C functions.

The previous sample is a *hypothetical preceding submitted PCM block tail*,
not a hardware-audout last played sample. This benchmark does not support
turning on either DSP algorithm in the actual Nintendo Switch game.
"""
import argparse
import ctypes
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

try:
    from tools import dino_pcm_resume_edge_benchmark as edge
except ImportError:
    import dino_pcm_resume_edge_benchmark as edge

SCHEMA="dino-rom-free-guarded-pcm-proxy-v1"
ROOT=Path(__file__).resolve().parents[1]


def native_gate(library):
    fn=library.dino_pcm_resume_guarded_proxy_would_help
    fn.argtypes=(ctypes.POINTER(ctypes.c_int16),
                 ctypes.POINTER(ctypes.c_int16),
                 ctypes.c_size_t,ctypes.c_size_t)
    fn.restype=ctypes.c_bool
    return fn


def channel_peak(previous, samples, channel):
    if (len(previous)!=2 or len(samples)!=2*edge.FRAMES or
        channel not in (0,1)):
        raise ValueError("malformed stereo step window")
    prev=previous[channel]
    peak=0
    for i in range(edge.ATTACK):
        val=samples[2*i+channel]
        peak=max(peak,abs(val-prev))
        prev=val
    return peak


def profile(name, previous, original, shaped, selected):
    before=[channel_peak(previous,original,ch) for ch in (0,1)]
    attacked=[channel_peak(previous,shaped,ch) for ch in (0,1)]
    expected=(all(y<=x for x,y in zip(before,attacked)) and
              max(attacked)<max(before))
    if type(selected) is not bool or selected!=expected:
        raise ValueError("native C gate contradicts independent peak oracle")
    proposed=shaped if selected else original
    measured=[channel_peak(previous,proposed,ch) for ch in (0,1)]
    if any(y>x for x,y in zip(before,measured)):
        raise ValueError("selected proxy worsens channel peak")
    if proposed[2*edge.ATTACK:]!=original[2*edge.ATTACK:]:
        raise ValueError("selected output modifies PCM tail")
    return {
        "scenario":name,
        "fixed_96frame_attack_would_run":True,
        "guarded_proxy_would_run":selected,
        "raw_window_peak_by_stereo_channel":before,
        "fixed_ramp_window_peak_by_stereo_channel":attacked,
        "guard_selected_window_peak_by_stereo_channel":measured,
        "selected_window_peak_not_worse_in_either_channel":True,
        "selected_pcm_tail_unchanged":True,
        "previous_sample_is_confirmed_played_on_device":False,
        "speaker_click_reduction_measured":False,
    }


def benchmark():
    if not shutil.which("gcc"):
        raise ValueError("GCC is required for actual-C gated PCM proxy")
    records=[]
    cases=edge.make_cases()
    cases["one_channel_worsens"]=(
        (0,10000),[30000,10000]*edge.FRAMES)
    with tempfile.TemporaryDirectory(prefix="dino-guarded-c-") as temp:
        filename=Path(temp)/"guarded.so"
        cmd=["gcc","-std=c11","-O2","-Wall","-Wextra","-Werror",
             "-shared","-fPIC","-Itools/native","-Isource",
             "tools/native/dino_pcm_resume_guarded_proxy.c",
             "source/dino_pcm_resume_ramp.c","-o",str(filename)]
        proc=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,
                            timeout=25,check=False)
        if proc.returncode:
            raise ValueError("native C gate/ramp compile failed: "+
                             proc.stderr[-400:])
        lib=ctypes.CDLL(str(filename))
        gate=native_gate(lib)
        attack=lib.dino_pcm_resume_ramp_apply
        attack.argtypes=[ctypes.POINTER(ctypes.c_int16),
                        ctypes.c_size_t,ctypes.c_size_t]
        attack.restype=ctypes.c_bool
        for name,(previous,original) in cases.items():
            prev=(ctypes.c_int16*2)(*previous)
            data=(ctypes.c_int16*(2*edge.FRAMES))(*original)
            selected=bool(gate(prev,data,edge.FRAMES,edge.ATTACK))
            if not attack(data,edge.FRAMES,edge.ATTACK):
                raise ValueError("native C ramp refused a valid PCM block")
            records.append(profile(name,previous,original,list(data),selected))
    mapping={r["scenario"]:r for r in records}
    if (not mapping["silence_to_loud"]["guarded_proxy_would_run"] or
        mapping["already_continuous"]["guarded_proxy_would_run"] or
        mapping["zero_signal"]["guarded_proxy_would_run"] or
        mapping["one_channel_worsens"]["guarded_proxy_would_run"]):
        raise ValueError("missing positive/negative guarded controls")
    return {
        "schema":SCHEMA,
        "status":"C_GATE_REJECTS_WORSE_WINDOW_STEP_PROXY_CASES",
        "pcm_frame_count":edge.FRAMES,
        "ramp_frames":edge.ATTACK,
        "sample_rate_hz":edge.RATE,
        "source":"two_actual_native_C_functions_and_independent_Python_oracle",
        "input_audio":"six_deterministic_rom_free_synthetic_cases",
        "profiles":records,
        "guard_off_by_default":True,
        "production_enabled":False,
        "previous_pcm_tail_was_submitted_not_proven_played":True,
        "max_step_proxy_is_not_perceptual_audio_quality":True,
        "physical_switch_speaker_audio_verified":False,
        "audible_click_reduction_verified":False,
        "production_enablement_recommended":False,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args(argv)
    try:
        result=benchmark()
        with a.out.open("x",encoding="ascii") as f:
            f.write(json.dumps(result,sort_keys=True)+"\n")
    except (OSError,ValueError,TypeError,OverflowError,UnicodeError,
            subprocess.SubprocessError) as exc:
        print(json.dumps({
            "status":"INCONCLUSIVE_GUARDED_SAMPLE_STEP_PCM_PROXY",
            "reason":type(exc).__name__,
            "production_enablement_recommended":False,
        },sort_keys=True))
        return 1
    print(json.dumps({
        "status":result["status"],
        "gated_case_count":sum(
            r["guarded_proxy_would_run"] for r in result["profiles"]),
        "total_cases":len(result["profiles"]),
        "production_enablement_recommended":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
