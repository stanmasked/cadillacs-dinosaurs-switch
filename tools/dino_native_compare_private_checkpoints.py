#!/usr/bin/env python3
"""Compare two private Stage278 native C checkpoint logs without echoing them.

This local diagnostic locates the first observed state divergence to an
input-frame bracket. It cannot tell which implementation is correct, and it
does not reproduce WolfMAME/Capcom gameplay or verify actual original video.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

LINE=re.compile(r"DINO278_CHECKPOINT frame=([0-9]+) full_state=([0-9a-f]{16})")
MAX_LOG=8*1024*1024
ROOT=Path(__file__).resolve().parents[1]

def parse_log(raw,frames,period):
    if type(frames) is not int or type(period) is not int or not (
            1<=frames<=10000000 and 1<=period<=10000000):
        raise ValueError("invalid bounded frame count or checkpoint interval")
    if (frames+period-1)//period>200000:
        raise ValueError("too many checkpoints for bounded private audit")
    if type(raw) is not bytes or len(raw)>MAX_LOG:
        raise ValueError("checkpoint log too large/invalid")
    try:
        lines=raw.decode("ascii").splitlines()
    except UnicodeError as err:
        raise ValueError("non-ASCII checkpoint log") from err
    expected=list(range(period,frames+1,period))
    if not expected or expected[-1]!=frames:
        expected.append(frames)
    if len(lines)!=len(expected):
        raise ValueError("missing, extra or duplicated checkpoints")
    values=[]
    for line,position in zip(lines,expected):
        match=LINE.fullmatch(line)
        if not match or int(match.group(1))!=position:
            raise ValueError("malformed or out-of-order checkpoint")
        values.append(match.group(2))
    return values

def compare(a,b,frames,period):
    first=parse_log(a,frames,period)
    second=parse_log(b,frames,period)
    indices=list(range(period,frames+1,period))
    if not indices or indices[-1]!=frames:
        indices.append(frames)
    mismatch=next((i for i,(x,y) in enumerate(zip(first,second))
                   if x!=y),None)
    def receipt(series):
        return hashlib.sha256("\n".join(series).encode("ascii")).hexdigest()
    return {
        "schema":"dino-private-native-full-state-checkpoint-comparison-v1",
        "status":"FULL_STATE_CHAINS_MATCH" if mismatch is None else "FIRST_OBSERVED_STATE_MISMATCH",
        "record_count":frames,"checkpoint_interval":period,
        "checkpoints_compared":len(indices),
        "first_observed_mismatch_at_input_frame":None if mismatch is None else indices[mismatch],
        "last_matching_checkpoint_input_frame":None if mismatch is None else (
            indices[mismatch-1] if mismatch else 0),
        "reference_checkpoint_chain_sha256":receipt(first),
        "candidate_checkpoint_chain_sha256":receipt(second),
        "WolfMAME_original_gameplay_verified":False,
        "full_per_frame_input_exposed":False,
    }

def ordinary_private_log(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("checkpoint log must be a regular non-symlink file")
    if path.stat().st_size>MAX_LOG:
        raise ValueError("checkpoint log exceeds bound")
    return path.read_bytes()

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--reference",type=Path,required=True)
    p.add_argument("--candidate",type=Path,required=True)
    p.add_argument("--input-frames",type=int,required=True)
    p.add_argument("--checkpoint-every",type=int,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args(argv)
    if ROOT==a.out.resolve() or ROOT in a.out.resolve().parents:
        raise ValueError("private receipt output must be outside repository")
    if a.out.exists():
        raise FileExistsError("refusing to replace private checkpoint report")
    result=compare(ordinary_private_log(a.reference),
                   ordinary_private_log(a.candidate),
                   a.input_frames,a.checkpoint_every)
    if a.out.parent.is_symlink():
        raise ValueError("private output parent may not be a symlink")
    with a.out.open("x",encoding="utf-8") as fp:
        json.dump(result,fp,indent=2)
        fp.write("\n")
    print(result["status"])
    return 0 if result["status"]=="FULL_STATE_CHAINS_MATCH" else 1

if __name__=="__main__":
    raise SystemExit(main())
