#!/usr/bin/env python3
"""Stage271: bounded, ROM-free capture plan from a PRIVATE Stage270 summary.

No INP/WLF/ROM is loaded here. The emitted list of frame indices is a
playback *request*, not proof of captured frames, exact emulation, or stages.
"""
import argparse
import hashlib
import json
from pathlib import Path

SOURCE_SCHEMA="dino-wolfmame0106-input-mapping-rom-free-v1"
PLAN_SCHEMA="dino-wolfmame0106-private-reference-capture-plan-v1"
MAX_INPUT_BYTES=1024*1024
OVERVIEW_INTERVAL_FRAMES=60
CAPTURE_WINDOW_FRAMES=1200

def positive_int(value,name,allow_zero=False):
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise ValueError("invalid "+name)
    return value

def create_plan(source):
    if type(source) is not dict or source.get("schema")!=SOURCE_SCHEMA:
        raise ValueError("not a Stage270 input summary")
    if source.get("status")!="STRUCTURAL_PORT_INFERENCE_NOT_REPLAY_VERIFIED":
        raise ValueError("unexpected input authenticity claims")
    if (source.get("original_0_106_serializer_confirmed") is not False or
        source.get("distinct_human_players_confirmed") is not False or
        source.get("native_gameplay_or_sprite_parity_confirmed") is not False or
        source.get("safe_to_publish_original_files") is not False):
        raise ValueError("unverified recording cannot claim replay or redistribution")
    frames=positive_int(source.get("frames"),"recorded frames")
    positive_int(source.get("total_press_onsets"),"input onsets")
    if source.get("game")!="dino" or not 900<=frames<=10000000:
        raise ValueError("game or frame count outside supported reference bounds")
    if source.get("port_byte_offsets")!={"system":3,"p1":19,"p2":18,"p3":23}:
        raise ValueError("incorrect active-low CPS-1 port byte ordering")
    items=source.get("candidate_private_replay_capture_windows")
    if type(items) is not list or not 1<=len(items)<=12:
        raise ValueError("require 1..12 bounded candidate windows")
    selected=[]
    previous_end=0
    for idx,item in enumerate(items):
        if type(item) is not dict:
            raise ValueError("invalid capture window")
        start=positive_int(item.get("start_frame"),"window start",True)
        end=positive_int(item.get("end_frame_exclusive"),"window end")
        actions=positive_int(item.get("player1_action_onsets"),"P1 action count")
        if (start%CAPTURE_WINDOW_FRAMES or end<=start or
            end>frames or end-start>CAPTURE_WINDOW_FRAMES or
            start<previous_end or (idx and start-previous_end<600)):
            raise ValueError("overlapping, unaligned or impossible capture window")
        previous_end=end
        selected.append((start,end,actions))
    overview=sorted({frame for start,end,_ in selected
                     for frame in range(start,end,OVERVIEW_INTERVAL_FRAMES)})
    # One dense candidate for animation inspection, selected by ACTION ONSETS,
    # not by guessed level names, player count or original frame contents.
    detail_start,detail_end,score=max(
        selected,key=lambda entry:(entry[2],-entry[0]))
    full=list(range(detail_start,detail_end))
    canonical=json.dumps(source,ensure_ascii=True,sort_keys=True,
                         separators=(",",":")).encode("ascii")
    return {
        "schema":PLAN_SCHEMA,
        "status":"PRIVATE_PLAYBACK_CAPTURE_REQUEST_NOT_EXECUTED",
        "game":"dino",
        "summary_sha256":hashlib.sha256(canonical).hexdigest(),
        "total_original_recorded_frames":frames,
        "approximate_fps_not_measured":60,
        "overview":{"sample_interval_frames":OVERVIEW_INTERVAL_FRAMES,
                    "candidate_windows":len(selected),
                    "requested_frames":overview},
        "animation_detail":{"selection":"highest_P1_action_onsets_only",
                            "start_frame":detail_start,
                            "end_frame_exclusive":detail_end,
                            "P1_action_onsets":score,
                            "requested_frames":full},
        "overview_frame_count":len(overview),
        "detail_frame_count":len(full),
        "requires_matching_WolfMAME_0_106_and_private_ROM":True,
        "input_binding_and_exact_video_frame_alignment_verified":False,
        "actual_emulator_frames_captured":False,
        "native_switch_or_original_graphic_parity_verified":False,
        "public_GitHub_raw_capture_export_permitted":False,
    }

def read_source(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("input must be an ordinary report file")
    if not 30<=path.stat().st_size<=MAX_INPUT_BYTES:
        raise ValueError("report outside size bounds")
    try:
        data=json.loads(path.read_text("utf-8"),
                        object_pairs_hook=unique_pairs)
    except (UnicodeError,json.JSONDecodeError) as e:
        raise ValueError("invalid report JSON") from e
    return data

def unique_pairs(pairs):
    out={}
    for key,value in pairs:
        if key in out:raise ValueError("duplicate JSON key")
        out[key]=value
    return out

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--summary",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args(argv)
    plan=create_plan(read_source(a.summary))
    with a.out.open("x",encoding="utf-8") as fp:
        json.dump(plan,fp,indent=2,ensure_ascii=True)
        fp.write("\n")
    print(plan["status"],plan["overview_frame_count"],
          plan["detail_frame_count"])

if __name__=="__main__":
    main()
