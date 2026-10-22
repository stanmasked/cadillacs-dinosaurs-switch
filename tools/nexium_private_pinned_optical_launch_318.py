#!/usr/bin/env python3
"""Stage318: pinned-input gate BEFORE exposing private original CPS-1 assets.

Validate the EXACT Stage316 opt-in NRO and EXACT release-pinned NeXium
archive, then extract it into an isolated ephemeral folder using Python's
safe tar filter. Only afterwards invoke the existing private Stage316 runner,
which verifies the user's original ROM and holds frames until real X11 proof.

Public CI exercises this validator with invented tiny files and injected
expected hashes; never commits or uploads original ROM or derived graphics.
"""
import argparse
import hashlib
import os
import signal
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tarfile
import tempfile

try:
    from . import wolfmame0106_private_binary_gate as guard
except ImportError:
    import wolfmame0106_private_binary_gate as guard

NRO_SHA256 = "8ff351fe9c5bf31d31ab2510908bcdb45bb965c4ea375c024d8b77395a67d0ac"
NRO_BYTES = 313541
NEXIUM_SHA256 = "d96cdd186447eec7a5c05a28fa5aa1b8bb6c8fb85fd7bf76721b349cf2c97dde"
NEXIUM_BYTES = 114560520
PASSED = "PRIVATE_PINNED_NEXIUM_OPTICAL_ORIGINAL_GFX_X11_CONFIRMED"
BLOCKED = "BLOCKED_PRIVATE_PINNED_NEXIUM_OPTICAL_PREFLIGHT"
STAGE316_PASS = "PRIVATE_ORIGINAL_CPS1_GFX_SYNTHETIC_SCENES_14_HOST_X11_MATCH"
MAX_ARCHIVE_MEMBERS = 4096
MAX_ARCHIVE_UNPACKED = 3*1024*1024*1024
RUN_TIMEOUT_SECONDS = 220


def _secure_regular(path, size, digest):
    """No symlinked files or ancestors, no public-repo inputs, exact bytes."""
    path = Path(path)
    if (not guard.outside_repo(path) or not guard.is_regular(path)
            or any(p.is_symlink() for p in path.parents)
            or path.stat().st_size != size
            or type(digest) is not str or len(digest) != 64):
        raise ValueError("pinned private executable input absent or unsafe")
    checksum = hashlib.sha256()
    with path.open("rb") as inp:
        for chunk in iter(lambda: inp.read(1024*1024), b""):
            checksum.update(chunk)
    if checksum.hexdigest() != digest:
        raise ValueError("NRO or emulator archive differs from exact pin")
    return path


def _safe_members(handle):
    """Restrict package structure before any guest/private data is handled."""
    members=handle.getmembers()
    if not 1<=len(members)<=MAX_ARCHIVE_MEMBERS:
        raise ValueError("unexpected NeXium archive member count")
    total=0
    for member in members:
        name=PurePosixPath(member.name)
        if (name.is_absolute() or not name.parts or
                any(x in ("..", ".") for x in name.parts) or
                "\\" in member.name or not member.name.strip()):
            raise ValueError("NeXium archive has unsafe path")
        if not (member.isfile() or member.isdir() or
                member.issym() or member.islnk()):
            raise ValueError("NeXium archive has unsupported special entry")
        if member.isfile():
            total+=member.size
            if member.size < 0 or total>MAX_ARCHIVE_UNPACKED:
                raise ValueError("NeXium archive expansion exceeds limit")
    return members


def _extract_verified_executable(archive, scratch):
    """Extract pinned archive with Python 3.12+ data filter, not raw tar."""
    if not hasattr(tarfile,"data_filter"):
        raise ValueError("requires Python tar safe data filter")
    scratch=Path(scratch)
    dest=scratch/"pinned-nexium"
    dest.mkdir(mode=0o700)
    with tarfile.open(archive,"r:gz") as tar:
        _safe_members(tar)
        tar.extractall(dest,filter="data")
    found={}
    for name in ("nexium-gui","nexium"):
        files=[p for p in dest.rglob(name) if p.is_file() and
               not p.is_symlink() and
               all(not a.is_symlink() for a in p.parents)]
        if len(files)>1:
            raise ValueError("ambiguous NeXium executable name")
        if files:
            found[name]=files[0]
    exe=found.get("nexium-gui") or found.get("nexium")
    if exe is None:
        raise ValueError("no native NeXium host executable in pinned archive")
    exe.chmod((exe.stat().st_mode&0o666)|0o100)
    if not os.access(exe,os.X_OK):
        raise ValueError("NeXium executable cannot be launched")
    return exe


def preflight(nro, archive):
    """Read-only immutable input verification: no game inputs are examined."""
    _secure_regular(nro,NRO_BYTES,NRO_SHA256)
    _secure_regular(archive,NEXIUM_BYTES,NEXIUM_SHA256)
    return True



def _descendant_pids(root_pid):
    """Return the current Linux process-tree descendants of a runner PID.

    NeXium itself uses a separate session so it can clean up its own helper
    processes. If the outer deadline fires, enumerate descendants before
    killing the runner so those separate process groups can also be stopped.
    """
    children={}
    try:
        entries=Path("/proc").iterdir()
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            try:
                fields=(entry/"stat").read_text(encoding="ascii").rsplit(")",1)[1].split()
                parent=int(fields[1])
                pid=int(entry.name)
            except (OSError,ValueError,IndexError):
                continue
            children.setdefault(parent,[]).append(pid)
    except OSError:
        return []
    result=[]
    pending=list(children.get(root_pid,[]))
    seen=set()
    while pending:
        pid=pending.pop()
        if pid==root_pid or pid in seen:
            continue
        seen.add(pid)
        result.append(pid)
        pending.extend(children.get(pid,[]))
    return result


def _signal_pids(pids, sig):
    """Signal only the explicitly enumerated runner descendants."""
    for pid in pids:
        try:
            os.kill(pid,sig)
        except ProcessLookupError:
            pass


def _terminate_process_group(proc):
    """Stop runner descendants and its session, including Xvfb/NeXium helpers."""
    descendants=set(_descendant_pids(proc.pid))
    _signal_pids(descendants,signal.SIGTERM)
    try:
        os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=6)
    except subprocess.TimeoutExpired:
        pass
    descendants.update(_descendant_pids(proc.pid))
    _signal_pids(descendants,signal.SIGKILL)
    try:
        os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:
        pass
    if proc.poll() is None:
        proc.wait(timeout=6)


def _execute_bounded(command, *, cwd, timeout=RUN_TIMEOUT_SECONDS):
    """Run the private optical harness with a hard deadline and tree cleanup."""
    try:
        proc=subprocess.Popen(
            command,cwd=cwd,stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.STDOUT,
            start_new_session=True)
    except OSError:
        raise ValueError("bounded private X11 run failed") from None
    try:
        try:
            returncode=proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise ValueError("bounded private X11 run failed") from None
        return subprocess.CompletedProcess(command,returncode)
    finally:
        _terminate_process_group(proc)


def run(rom,nro,archive,receipt,*,execute=None):
    preflight(nro,archive)
    receipt=Path(receipt)
    if (not guard.outside_repo(receipt) or receipt.exists()
            or receipt.is_symlink() or not receipt.parent.is_dir()
            or any(x.is_symlink() for x in receipt.parents)):
        raise ValueError("receipt must be a new private regular path")
    root=Path(__file__).resolve().parents[1]
    script=root/"tools"/"run_private_original_gfx_optical_316.sh"
    if not script.is_file() or script.is_symlink():
        raise ValueError("Stage316 local private runner unavailable")
    with tempfile.TemporaryDirectory(prefix="stage318-pinned-host-") as temp:
        exe=_extract_verified_executable(archive,temp)
        command=["bash",str(script),str(rom),str(nro),str(exe),str(receipt)]
        try:
            if execute is None:
                result=_execute_bounded(command,cwd=root)
            else:
                result=execute(
                    command,cwd=root,stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,
                    timeout=RUN_TIMEOUT_SECONDS,check=False)
        except (subprocess.TimeoutExpired,OSError):
            raise ValueError("bounded private X11 run failed") from None
    if result.returncode!=0 or not receipt.is_file() or receipt.is_symlink():
        raise ValueError("no complete private host-visible proof")
    if not (0<receipt.stat().st_size<8192
            and (receipt.stat().st_mode&0o777)==0o600):
        raise ValueError("private proof receipt has unsafe attributes")
    import json
    record=json.loads(receipt.read_text("utf-8"))
    if (type(record) is not dict or record.get("status")!=STAGE316_PASS
            or record.get("guest_submitted_original_graphics_synthetic_frames")!=14
            or record.get("host_x11_optical_original_graphics_synthetic_frames")!=14
            or record.get("original_graphics_uploaded_to_public_github") is not False
            or record.get("actual_original_game_executed") is not False
            or record.get("physical_nintendo_switch_display_verified") is not False):
        raise ValueError("incomplete or overclaimed private X11 receipt")
    return True


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rom",required=True,type=Path)
    p.add_argument("--nro",required=True,type=Path)
    p.add_argument("--nexium-archive",required=True,type=Path)
    p.add_argument("--receipt",required=True,type=Path)
    args=p.parse_args(argv)
    try:
        run(args.rom,args.nro,args.nexium_archive,args.receipt)
    except Exception:
        # NEVER print argv, private filenames, archive contents, frame bytes,
        # PIN hashes or subprocess logs into public/user-shared artifacts.
        print(BLOCKED)
        return 2
    print(PASSED)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
