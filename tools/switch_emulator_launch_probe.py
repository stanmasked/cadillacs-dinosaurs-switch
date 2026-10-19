#!/usr/bin/env python3
"""Conservative, ROM-free Nintendo Switch homebrew emulator launch probe.

This program never claims game rendering, controller input or audible
playback from a process-survival check. It runs a user-installed emulator
with a self-built .nro for a bounded interval, then terminates it.
No firmware, prod.keys, ROMs, screenshots or private emulator logs are read,
copied, uploaded or printed. Results contain safe booleans and durations.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

MAX_RUNTIME=120.0
MIN_RUNTIME=0.2


def check_nro(path):
    """Validate NRO header and bounded, nonoverlapping executable segments.

    This is static format validation, not CPU execution, code signing,
    device compatibility or proof that the homebrew rendered a frame.
    """
    try:
        path=Path(path)
        if path.is_symlink() or not path.is_file():
            return False
        size=path.stat().st_size
        if not 0x80<=size<=128*1024*1024:
            return False
        with path.open('rb') as stream:
            head=stream.read(0x40)
        if len(head)<0x40 or head[0x10:0x14]!=b'NRO0':
            return False
        image_size=struct.unpack_from('<I',head,0x18)[0]
        if not (0x80<=image_size<=size and image_size%0x1000==0):
            return False
        sections=[
            struct.unpack_from('<II',head,offset)
            for offset in (0x20,0x28,0x30)
        ]
        previous_end=0
        for index,(start,length) in enumerate(sections):
            if (not length or start%0x1000 or
                    (index==0 and start!=0) or
                    start<previous_end or
                    start+length>image_size):
                return False
            previous_end=start+length
        return True
    except (OSError,ValueError,OverflowError):
        return False


def check_sha256(path,expected):
    """Compare optional user-provided build digest without logging it."""
    if expected is None:
        return None
    if (not isinstance(expected,str) or len(expected)!=64 or
            any(ch not in '0123456789abcdefABCDEF' for ch in expected)):
        return False
    try:
        digest=hashlib.sha256()
        with Path(path).open('rb') as f:
            for block in iter(lambda:f.read(65536),b''):
                digest.update(block)
        return digest.hexdigest()==expected.lower()
    except OSError:
        return False


def resolve_executable(candidate):
    if not candidate:
        return None
    if os.sep in candidate:
        path=Path(candidate)
        return str(path) if path.is_file() and os.access(path,os.X_OK) else None
    return shutil.which(candidate)


def probe(emulator,nro,*,runtime=2.0,extra_args=(),sha256=None):
    """Perform one bounded process check; no emulated-frame claim is made."""
    report={
        'schema':'dino-emulator-launch-v2',
        'nro_format_valid':check_nro(nro),
        'nro_sha256_matches':None,
        'emulator_available':bool(resolve_executable(emulator)),
        'process_launched':False,
        'process_survived_window':False,
        'rendering_verified':False,
        'controller_verified':False,
        'audio_verified':False,
        'status':'NOT_RUN',
    }
    if not report['nro_format_valid']:
        report['status']='INVALID_NRO'
        return report
    if sha256 is not None and (not isinstance(sha256,str) or
            len(sha256)!=64 or
            any(ch not in '0123456789abcdefABCDEF' for ch in sha256)):
        report['status']='INVALID_CHECKSUM_ARGUMENT'
        return report
    report['nro_sha256_matches']=check_sha256(nro,sha256)
    if report['nro_sha256_matches'] is False:
        report['status']='NRO_CHECKSUM_MISMATCH'
        return report
    executable=resolve_executable(emulator)
    if not executable:
        report['status']='EMULATOR_UNAVAILABLE'
        return report
    if not MIN_RUNTIME<=runtime<=MAX_RUNTIME:
        report['status']='INVALID_RUNTIME'
        return report
    # No arbitrary shell interpolation. The homebrew file is the final
    # argument; e.g. Ryujinx /path/to/homebrew.nro.
    args=[executable,*extra_args,str(nro.resolve())]
    proc=None
    try:
        proc=subprocess.Popen(args,stdin=subprocess.DEVNULL,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
        report['process_launched']=True
        deadline=time.monotonic()+runtime
        while time.monotonic()<deadline:
            if proc.poll() is not None:
                report['status']='EMULATOR_EARLY_EXIT'
                return report
            time.sleep(min(0.05,max(0,deadline-time.monotonic())))
        if proc.poll() is None:
            report['process_survived_window']=True
            report['status']='PROCESS_ALIVE_RENDER_UNVERIFIED'
        else:
            report['status']='EMULATOR_EARLY_EXIT'
    except (OSError,ValueError):
        report['status']='EMULATOR_EXEC_FAILED'
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--emulator',required=True,
                        help='Installed emulator executable, e.g. Ryujinx')
    parser.add_argument('--nro',type=Path,required=True,
                        help='ROM-free, user-built .nro application')
    parser.add_argument('--sha256',
                        help='Expected 64-character SHA-256 of NRO (optional)')
    parser.add_argument('--runtime',type=float,default=3.0,
                        help='Seconds to observe (0.2 to 120)')
    parser.add_argument('--emulator-arg',action='append',default=[],
                        help='Extra emulator argument preceding the .nro')
    args=parser.parse_args(argv)
    report=probe(args.emulator,args.nro,runtime=args.runtime,
                 extra_args=args.emulator_arg,sha256=args.sha256)
    print(json.dumps(report,sort_keys=True))
    return 0 if report['process_survived_window'] else 2


if __name__=='__main__':
    raise SystemExit(main())
