#!/usr/bin/env python3
"""Conservative, ROM-free Nintendo Switch homebrew emulator launch probe.

This program never claims game rendering, controller input or audible
playback from a process-survival check. It runs a user-installed emulator
with a self-built .nro for a bounded interval, then terminates it.
No firmware, prod.keys, ROMs, screenshots or private emulator logs are read,
copied, uploaded or printed. Results contain safe booleans and durations.
"""
import argparse
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
    """Check the public homebrew binary header; never read game assets."""
    try:
        stat=path.stat()
        if not path.is_file() or not 0x80<=stat.st_size<=128*1024*1024:
            return False
        with path.open('rb') as stream:
            head=stream.read(0x20)
        if len(head)<0x20 or head[0x10:0x14]!=b'NRO0':
            return False
        image_size=struct.unpack_from('<I',head,0x18)[0]
        return 0x80<=image_size<=stat.st_size
    except (OSError,ValueError,OverflowError):
        return False


def resolve_executable(candidate):
    if not candidate:
        return None
    if os.sep in candidate:
        path=Path(candidate)
        return str(path) if path.is_file() and os.access(path,os.X_OK) else None
    return shutil.which(candidate)


def probe(emulator,nro,*,runtime=2.0,extra_args=()):
    """Perform one bounded process check; no emulated-frame claim is made."""
    report={
        'schema':'dino-emulator-launch-v1',
        'nro_format_valid':check_nro(nro),
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
    parser.add_argument('--runtime',type=float,default=3.0,
                        help='Seconds to observe (0.2 to 120)')
    parser.add_argument('--emulator-arg',action='append',default=[],
                        help='Extra emulator argument preceding the .nro')
    args=parser.parse_args(argv)
    report=probe(args.emulator,args.nro,runtime=args.runtime,
                 extra_args=args.emulator_arg)
    print(json.dumps(report,sort_keys=True))
    return 0 if report['process_survived_window'] else 2


if __name__=='__main__':
    raise SystemExit(main())
