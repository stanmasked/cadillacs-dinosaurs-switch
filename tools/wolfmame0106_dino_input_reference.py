#!/usr/bin/env python3
"""ROM-free local-only structural reader for WolfMAME 0.106 dino INP/WLF.

The output is ONLY aggregate input diagnostics and candidate replay windows.
It does not bundle or upload a user's INP, WLF, ROM, screenshots or input stream.
The offset mapping is inferred from the CPS-1 IN1/IN2 port layout; true
playback/controller mapping MUST still be checked in WolfMAME 0.106.
"""
import argparse
import json
import struct
from pathlib import Path

HEADER_BYTES = 32
FRAME_BYTES = 124
FPS_APPROX = 60.0
PORTS = {"system": 3, "p1": 19, "p2": 18, "p3": 23}
COMMON = {0:"right", 1:"left", 2:"down", 3:"up",
          4:"attack_button1", 5:"jump_button2"}
NAMES = {
    "system": {0:"coin1",1:"coin2",2:"service1",4:"start1",5:"start2"},
    "p1": COMMON, "p2": COMMON,
    "p3": {**COMMON, 6:"coin3", 7:"start3"},
}
ALIASES = (
    (("p1", "right"),("p2", "left")),
    (("p1", "down"),("p2", "jump_button2")),
    (("p1", "attack_button1"),("p3", "down")),
    (("p1", "jump_button2"),("p3", "right")),
)

def metadata(inp, wlf):
    with inp.open("rb") as handle:
        header = handle.read(HEADER_BYTES)
    companion = wlf.read_bytes()
    if (len(header)!=HEADER_BYTES or len(companion)!=598 or
            companion[:4]!=b"WLF\x00" or
            struct.unpack_from("<I",companion,4)[0]!=9):
        raise ValueError("Unsupported WolfMAME header/WLF revision")
    if (header[:4]!=b"dino" or
            companion[148:157].split(b"\x00",1)[0]!=b"dino"):
        raise ValueError("Not the dino game")
    if header[16:20]!=companion[248:252]:
        raise ValueError("INP/WLF recording tag mismatch")
    version=companion[157:240].split(b"\x00",1)[0].decode("ascii","replace")
    if not version.startswith("0.106 "):
        raise ValueError("Expected the WolfMAME 0.106 family")
    frames=struct.unpack_from("<I",companion,264)[0]
    if not frames or inp.stat().st_size!=HEADER_BYTES+frames*FRAME_BYTES:
        raise ValueError("Invalid fixed record count/stride")
    start,end=struct.unpack_from("<II",companion,256)
    if end<start or end-start>20*3600:
        raise ValueError("Invalid recording timestamps")
    return frames,version,end-start

def analyze(inp, wlf):
    frames,version,elapsed=metadata(inp,wlf)
    signals=[(p,name,bit) for p,defs in NAMES.items()
             for bit,name in defs.items()]
    prev={ (p,name):False for p,name,bit in signals }
    held={ (p,name):0 for p,name,bit in signals }
    edges={ (p,name):0 for p,name,bit in signals }
    active_overlap={i:0 for i in range(len(ALIASES))}
    active_union={i:0 for i in range(len(ALIASES))}
    action_buckets={}
    variable=set()
    first_record=None
    with inp.open("rb") as handle:
        handle.seek(HEADER_BYTES)
        for frame in range(frames):
            raw=handle.read(FRAME_BYTES)
            if len(raw)!=FRAME_BYTES:
                raise ValueError("Truncated frame")
            if first_record is None:
                first_record=raw
            for offset in range(FRAME_BYTES):
                if raw[offset]!=first_record[offset]:
                    variable.add(offset)
            current={}
            for port,name,bit in signals:
                pressed=(raw[PORTS[port]]&(1<<bit))==0
                key=(port,name)
                current[key]=pressed
                if pressed:
                    held[key]+=1
                    if not prev[key]:
                        edges[key]+=1
                        if port=="p1" and name in ("attack_button1","jump_button2"):
                            bucket=frame//1200
                            action_buckets[bucket]=action_buckets.get(bucket,0)+1
                prev[key]=pressed
            for i,(a,b) in enumerate(ALIASES):
                active_overlap[i]+=int(current[a] and current[b])
                active_union[i]+=int(current[a] or current[b])
    windows=[]
    ranked=sorted(action_buckets.items(),key=lambda row:(-row[1],row[0]))
    for bucket,actions in ranked:
        start=bucket*1200
        if all(abs(start-w["start_frame"])>=1800 for w in windows):
            windows.append({"start_frame":start,
                "end_frame_exclusive":min(start+1200,frames),
                "approx_start_seconds":round(start/FPS_APPROX,3),
                "player1_action_onsets":actions})
        if len(windows)==12:break
    windows.sort(key=lambda row:row["start_frame"])
    alias_results=[]
    for i,(a,b) in enumerate(ALIASES):
        intersection=active_overlap[i]
        union=active_union[i]
        overlap=(intersection/union if union else 0)
        alias_results.append({
            "signal_a":".".join(a),"signal_b":".".join(b),
            "active_overlap_jaccard":round(overlap,5),
            "mismatching_frames":held[a]+held[b]-2*intersection,
            "looks_correlated":overlap>=0.95})
    return {
        "schema":"dino-wolfmame0106-input-mapping-rom-free-v1",
        "status":"STRUCTURAL_PORT_INFERENCE_NOT_REPLAY_VERIFIED",
        "game":"dino","recording_version":version,
        "frames":frames,"wall_clock_duration_seconds":elapsed,
        "approximate_frame_rate":FPS_APPROX,
        "port_byte_offsets":PORTS,
        "variable_byte_offsets":sorted(variable),
        "total_press_onsets":sum(edges.values()),
        "signals":[{"port":port,"name":name,"bit":bit,
                    "held_frames":held[(port,name)],
                    "press_onsets":edges[(port,name)]}
                   for port,name,bit in signals if held[(port,name)]],
        "cross_player_alias_diagnostics":alias_results,
        "candidate_private_replay_capture_windows":windows,
        "original_0_106_serializer_confirmed":False,
        "distinct_human_players_confirmed":False,
        "native_gameplay_or_sprite_parity_confirmed":False,
        "physical_Nintendo_Switch_tested":False,
        "safe_to_publish_original_files":False,
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inp",type=Path,required=True)
    p.add_argument("--wlf",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    result=analyze(a.inp,a.wlf)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    if a.out.exists():
        raise FileExistsError("Refusing to overwrite an existing audit")
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",
                     encoding="utf-8")
    print(result["status"],result["frames"],result["total_press_onsets"])

if __name__=="__main__":
    main()
