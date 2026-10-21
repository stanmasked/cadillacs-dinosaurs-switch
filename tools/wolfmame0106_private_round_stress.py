#!/usr/bin/env python3
"""Stage275: run *invented* native training bouts on private WolfMAME P1 bytes.

This does not run the original arcade game, use proprietary ROMs, or derive
authentic game physics. No original input stream or per-frame trace is saved.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

if __package__:
    from tools.wolfmame0106_dino_input_reference import metadata, HEADER_BYTES, FRAME_BYTES, PORTS
else:
    from wolfmame0106_dino_input_reference import metadata, HEADER_BYTES, FRAME_BYTES, PORTS

ROOT=Path(__file__).resolve().parents[1]
SCHEMA="dino-private-independent-native-sparring-rounds-v1"

def checked_positive_int(value,label):
    if type(value) is not int or not 1<=value<=12000:
        raise ValueError("invalid "+label)
    return value

def run_rounds(input_bytes,compiler,round_frames=1200):
    checked_positive_int(round_frames,"round-frame count")
    if type(input_bytes) is not bytes or not 1<=len(input_bytes)<=10000000:
        raise ValueError("invalid bounded active-low input stream")
    executable=shutil.which(compiler)
    if not executable or compiler not in ("gcc","clang"):
        raise ValueError("compiler unavailable/not permitted")
    with tempfile.TemporaryDirectory(prefix="dino275-") as folder:
        binary=Path(folder)/"arena_stress"
        subprocess.run(
            [executable,"-std=c99","-O2","-Wall","-Wextra","-Werror",
             "-I",str(ROOT/"source"),str(ROOT/"source"/"dino_arena.c"),
             str(ROOT/"tools"/"dino_arena_recorded_input_stress.c"),
             "-o",str(binary)],
            capture_output=True,text=True,check=True,timeout=30)
        # Preserve input-edge continuity even while deliberately resetting
        # the invented arena at every round boundary.
        rounds=[(i,input_bytes[i:i+round_frames])
                for i in range(0,len(input_bytes),round_frames)]
        boundary_held_attack=sum(
            not (input_bytes[i-1]&16) and not (input_bytes[i]&16)
            for i in range(round_frames,len(input_bytes),round_frames))
        boundary_held_jump=sum(
            not (input_bytes[i-1]&32) and not (input_bytes[i]&32)
            for i in range(round_frames,len(input_bytes),round_frames))
        expected_attack_edges=sum(
            not (byte&16) and (i==0 or bool(input_bytes[i-1]&16))
            for i,byte in enumerate(input_bytes))
        expected_jump_edges=sum(
            not (byte&32) and (i==0 or bool(input_bytes[i-1]&32))
            for i,byte in enumerate(input_bytes))
        outcome={}
        for mode in ("normal","invented_sparring"):
            records=[]
            for offset,chunk in rounds:
                prior=input_bytes[offset-1] if offset else 255
                cmd=[str(binary)]+(["--spar"] if mode=="invented_sparring" else [])
                cmd.append(f"--prior-active-low={prior:02x}")
                p=subprocess.run(cmd,input=chunk,capture_output=True,check=True,timeout=30)
                item=json.loads(p.stdout)
                if (item.get("nominal_input_records")!=len(chunk) or
                    item.get("training_only") is not True or
                    item.get("wolfmame_playback_verified") is not False or
                    item.get("sparring_mode") is not (mode=="invented_sparring")):
                    raise ValueError("bad native input receipt")
                full_digest=item.get("full_state_digest_fnv64")
                if (item.get("full_state_fields")!=30 or
                    not isinstance(full_digest,str) or len(full_digest)!=16 or
                    any(ch not in "0123456789abcdef" for ch in full_digest)):
                    raise ValueError("missing or malformed full native combat-state witness")
                records.append(item)
            if (sum(i["attack_press_edges"] for i in records)!=expected_attack_edges or
                sum(i["jump_press_edges"] for i in records)!=expected_jump_edges):
                raise ValueError("round boundaries changed authentic P1 press-edge totals")
            hash_digest=hashlib.sha256(
                (";".join(i["state_digest_fnv64"] for i in records)).encode("ascii")
            ).hexdigest()
            full_digest_sha256=hashlib.sha256(
                (";".join(i["full_state_digest_fnv64"] for i in records)).encode("ascii")
            ).hexdigest()
            outcome[mode]={
                "rounds":len(records),
                "records":sum(i["nominal_input_records"] for i in records),
                "nominal_attack_press_edges":expected_attack_edges,
                "nominal_jump_press_edges":expected_jump_edges,
                "rounds_with_swings":sum(i["actual_training_swings"]>0 for i in records),
                "rounds_with_jumps":sum(i["actual_training_jumps"]>0 for i in records),
                "rounds_with_hits":sum(i["successful_training_hits"]>0 for i in records),
                "swings":sum(i["actual_training_swings"] for i in records),
                "jumps":sum(i["actual_training_jumps"] for i in records),
                "hits":sum(i["successful_training_hits"] for i in records),
                "player_defeated_rounds":sum(i["player_hp"]==0 for i in records),
                "continued_held_attack_edges_suppressed":boundary_held_attack,
                "continued_held_jump_edges_suppressed":boundary_held_jump,
                "round_state_digest_sha256":hash_digest,
                "round_full_state_digest_sha256":full_digest_sha256,
                "full_state_fields_witnessed":30,
            }
        return outcome

def compare_private_input(inp,wlf,round_frames=1200,compilers=("gcc","clang")):
    checked_positive_int(round_frames,"round-frame count")
    if inp.is_symlink() or wlf.is_symlink():
        raise ValueError("do not follow private input symlinks")
    n,version,_duration=metadata(inp,wlf)
    full=inp.read_bytes()
    if len(full)!=HEADER_BYTES+FRAME_BYTES*n:
        raise ValueError("private input changed during read")
    stream=full[HEADER_BYTES+PORTS["p1"]::FRAME_BYTES]
    if len(stream)!=n:raise ValueError("P1 extraction mismatch")
    if not compilers or len(set(compilers))!=len(compilers):
        raise ValueError("invalid compiler set")
    results={compiler:run_rounds(stream,compiler,round_frames)
             for compiler in compilers}
    first=next(iter(results.values()))
    matching=all(result==first for result in results.values())
    if not matching:
        raise ValueError("native round state mismatch across compilers")
    return {
        "schema":SCHEMA,
        "status":"EXACT_NATIVE_TRAINING_ROUNDS_NOT_ARCADE_REPLAY",
        "game":"dino",
        "nominal_wolfmame_version":version,
        "input_records":n,"round_frame_limit":round_frames,
        "compiler_variants":list(compilers),
        "cross_compiler_exact_result_match":matching,
        "aggregates":first,
        "rounds_reset_independently":True,
        "frame_index_video_alignment_verified":False,
        "original_emulator_executed":False,
        "original_game_physics_or_sprites_verified":False,
        "full_original_input_stream_in_report":False,
    }

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inp",type=Path,required=True)
    p.add_argument("--wlf",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--round-frames",type=int,default=1200)
    p.add_argument("--compiler",action="append",choices=("gcc","clang"))
    args=p.parse_args(argv)
    if ROOT in args.out.resolve().parents:
        raise ValueError("private derived report must stay outside tracked repo")
    report=compare_private_input(
        args.inp,args.wlf,args.round_frames,tuple(args.compiler or ("gcc","clang")))
    with args.out.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2)
        f.write("\n")
    print(report["status"],report["input_records"])

if __name__=="__main__":
    main()
