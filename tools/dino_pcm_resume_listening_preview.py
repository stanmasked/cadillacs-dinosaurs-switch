#!/usr/bin/env python3
"""Generate three entirely invented stereo WAVs to LISTEN to an experimental
96-frame PCM resume attack and a host-only guarded proxy decision.

No arcade ROM, samples, MIDI, copyrighted game sounds or console recording.
Audibility cannot be inferred from the integer sample discontinuity score.
The guest's previous *submitted* sample is not its last *played* sample.
This offline wave constructor knows its immediately preceding synthetic
sample; that knowledge does NOT transfer to asynchronous libnx audout.
Nothing here changes/links the standard or opt-in Switch NRO.
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
import wave

RATE=48000
CHANNELS=2
TICK_FRAMES=800
ATTACK_FRAMES=96
SCHEMA="dino-synthetic-pcm-resume-listening-preview-v1"
FILE_NAMES=("raw.wav","fixed_ramp.wav","guarded_proxy.wav")
ROOT=Path(__file__).resolve().parents[1]
A_PRE=12000
A_GAP=2400
A_RESUME=12000
SEPARATOR=4800
B_PRE=12000
B_RESUME=12000
TAIL=2400
TOTAL=A_PRE+A_GAP+A_RESUME+SEPARATOR+B_PRE+B_RESUME+TAIL
A_POS=A_PRE+A_GAP
B_POS=A_PRE+A_GAP+A_RESUME+SEPARATOR+B_PRE


def tone(frames):
    """A harmless newly synthesized deterministic two-channel 440Hz tone."""
    if type(frames) is not int or not 0<=frames<=RATE*10:
        raise ValueError("bad invented tone length")
    out=[]
    for i in range(frames):
        # cos at 0 starts near full amplitude intentionally, to challenge
        # a previous-silence boundary; 0.25s is 110 complete 440Hz cycles.
        phase=2*math.pi*440*i/RATE
        out.extend((round(22000*math.cos(phase)),
                    round(-15000*math.cos(phase))))
    return out


def create_base_samples():
    prior=tone(A_PRE)
    restarted=tone(A_RESUME)
    b_all=tone(B_PRE+B_RESUME)
    data=(prior+[0]*(A_GAP*CHANNELS)+restarted+
          [0]*(SEPARATOR*CHANNELS)+b_all+
          [0]*(TAIL*CHANNELS))
    if len(data)!=TOTAL*CHANNELS:
        raise ValueError("incorrect stereo preview length")
    # The two regions deliberately have DIFFERENT continuity:
    # A is genuine synthetic silence -> tone, B is continuous tone.
    if data[(A_POS-1)*2:A_POS*2]!=[0,0]:
        raise ValueError("episode A does not start after silence")
    if data[(B_POS-1)*2:B_POS*2] != tone(B_PRE)[-2:]:
        raise ValueError("episode B has malformed preceding tone")
    return data


def build_native(tmp):
    if shutil.which("gcc") is None:
        raise ValueError("native GCC is required; never substitute model audio")
    library_file=Path(tmp)/"dino-offline-pcm.so"
    result=subprocess.run([
        "gcc","-std=c11","-O2","-Wall","-Wextra","-Werror",
        "-fPIC","-shared","-Itools/native","-Isource",
        "source/dino_pcm_resume_ramp.c",
        "tools/native/dino_pcm_resume_guarded_proxy.c",
        "-o",str(library_file),
    ],cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
      text=True,check=False,timeout=30)
    if result.returncode!=0:
        raise ValueError("actual native C PCM functions failed to compile: "+
                         result.stderr[-600:])
    lib=ctypes.CDLL(str(library_file))
    ramp=lib.dino_pcm_resume_ramp_apply
    ramp.argtypes=(ctypes.POINTER(ctypes.c_int16),ctypes.c_size_t,
                   ctypes.c_size_t)
    ramp.restype=ctypes.c_bool
    gate=lib.dino_pcm_resume_guarded_proxy_would_help
    gate.argtypes=(ctypes.POINTER(ctypes.c_int16),
                   ctypes.POINTER(ctypes.c_int16),ctypes.c_size_t,
                   ctypes.c_size_t)
    gate.restype=ctypes.c_bool
    return ramp,gate


def boundary(samples,index):
    if len(samples)!=TOTAL*CHANNELS or not 1<=index<TOTAL:
        raise ValueError("bad synthetic audio boundary")
    return [abs(samples[2*index+c]-samples[2*(index-1)+c])
            for c in (0,1)]


def process(ramp,gate):
    raw=create_base_samples()
    fixed=raw.copy()
    guarded=raw.copy()
    episodes=[]
    for name,index,expected in (
        ("silence_to_tone",A_POS,True),
        ("continuous_tone",B_POS,False),
    ):
        previous=raw[2*(index-1):2*index]
        original=raw[2*index:2*(index+TICK_FRAMES)]
        prev_c=(ctypes.c_int16*2)(*previous)
        candidate=(ctypes.c_int16*(2*TICK_FRAMES))(*original)
        select=bool(gate(prev_c,candidate,TICK_FRAMES,ATTACK_FRAMES))
        if select!=expected:
            raise ValueError("host C gate failed a required positive/negative control")
        if not ramp(candidate,TICK_FRAMES,ATTACK_FRAMES):
            raise ValueError("host C fixed ramp refused valid input")
        shaped=list(candidate)
        if shaped[2*ATTACK_FRAMES:] != original[2*ATTACK_FRAMES:]:
            raise ValueError("fixed C ramp mutated tail")
        if original[:2]==shaped[:2] and select:
            raise ValueError("no actual sample-level effect at accepted boundary")
        fixed[2*index:2*(index+TICK_FRAMES)]=shaped
        if select:
            guarded[2*index:2*(index+TICK_FRAMES)]=shaped
        episodes.append({
            "name":name,
            "start_stereo_frame":index,
            "guarded_proxy_selected":select,
            "raw_boundary_steps":boundary(raw,index),
            "fixed_ramp_boundary_steps":boundary(fixed,index),
            "guarded_proxy_boundary_steps":boundary(guarded,index),
            "synthetic_prior_sample_known":True,
            "equivalent_to_asynchronous_guest_audio_queue":False,
        })
    if (guarded[2*B_POS:]!=raw[2*B_POS:] or
        guarded[2*A_POS:2*(A_POS+TICK_FRAMES)]==
            raw[2*A_POS:2*(A_POS+TICK_FRAMES)]):
        raise ValueError("guarded profile did not isolate intended attack")
    for array in (raw,fixed,guarded):
        if len(array)!=TOTAL*2 or any(not -32768<=x<=32767 for x in array):
            raise ValueError("incorrect stereo PCM bounds")
    return {"raw.wav":raw,"fixed_ramp.wav":fixed,
            "guarded_proxy.wav":guarded},episodes


def pcm_bytes(samples):
    if len(samples)!=TOTAL*CHANNELS:
        raise ValueError("malformed PCM preview")
    return struct.pack("<"+str(len(samples))+"h",*samples)


def generate(out_dir):
    path=Path(out_dir)
    if not path.exists() or not path.is_dir() or path.is_symlink():
        raise ValueError("create an empty real destination directory first")
    manifest=path/"listening-preview-manifest.json"
    output_files=[path/name for name in FILE_NAMES]+[manifest]
    if any(p.exists() or p.is_symlink() for p in output_files):
        raise ValueError("refuse to overwrite existing WAV or report")
    with tempfile.TemporaryDirectory(prefix="dino-wav-gcc-") as temp:
        streams,episodes=process(*build_native(temp))
    output=[]
    for name in FILE_NAMES:
        buf=pcm_bytes(streams[name])
        file=path/name
        with wave.open(str(file),"xb") as wav:
            wav.setnchannels(CHANNELS)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes(buf)
        output.append({
            "file_name":name,
            "sha256_pcm_le":hashlib.sha256(buf).hexdigest(),
            "pcm_bytes":len(buf),
            "sample_frames":TOTAL,
        })
    report={
        "schema":SCHEMA,
        "status":"SYNTHETIC_WAV_C_FIXED_VS_GUARDED_PCM_ATTACK",
        "sample_rate_hz":RATE,
        "bit_depth":16,
        "stereo_channels":CHANNELS,
        "attack_frames":ATTACK_FRAMES,
        "attack_duration_ms":2,
        "input_source":"newly_invented_440hz_cosine_not_game_audio",
        "files":output,
        "episodes":episodes,
        "no_original_game_assets_included":True,
        "audio_queue_timestamps_measured":False,
        "physical_switch_speaker_verified":False,
        "audible_click_reduction_proven":False,
        "production_audio_code_modified":False,
        "production_enablement_recommended":False,
    }
    with manifest.open("x",encoding="ascii") as f:
        f.write(json.dumps(report,sort_keys=True)+"\n")
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir",type=Path,required=True)
    a=p.parse_args(argv)
    try:
        result=generate(a.out_dir)
    except (OSError,ValueError,TypeError,OverflowError,
            subprocess.SubprocessError) as exc:
        print(json.dumps({
            "status":"INCONCLUSIVE_SYNTHETIC_PCM_LISTENING_PREVIEW",
            "reason":type(exc).__name__,
            "audible_click_reduction_proven":False,
        },sort_keys=True))
        return 1
    print(json.dumps({
        "status":result["status"],
        "files":[x["file_name"] for x in result["files"]],
        "audible_click_reduction_proven":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
