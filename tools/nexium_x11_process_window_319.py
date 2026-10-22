#!/usr/bin/env python3
"""Stage319: bind private original-GFX X11 window captures to a NEW NeXium PID.

A window title alone cannot prove which emulator run owns an X11 image.
Require the client-reported _NET_WM_PID to match the exact NeXium process
created by this probe, or an existing descendant in /proc. Reject ambiguous
windows. This is a fail-closed X11 ownership check, NOT cryptographic
attestation of the X server, the game ROM or original gameplay.

Public CI only tests synthetic process trees and mocked xdotool outputs.
"""
import re
import subprocess

WINDOW_LIMIT = 32
SEARCH_BYTES_LIMIT = 4096
MAX_ANCESTORS = 24


def _parent_linux(pid):
    """Read only the numeric PPid from Linux /proc; no path is exported."""
    if type(pid) is not int or pid <= 1:
        raise ValueError("invalid X11 owner PID")
    with open("/proc/%d/status" % pid, "r", encoding="ascii") as handle:
        for line in handle:
            if line.startswith("PPid:"):
                value = line[5:].strip()
                if not re.fullmatch(r"[0-9]{1,10}", value):
                    raise ValueError("invalid Linux process parent")
                return int(value)
    raise ValueError("no process parent in Linux procfs")


def belongs_to_run(owner, root, *, parent_for=_parent_linux):
    """Require an unbroken ancestor chain from the X11 client to root."""
    if type(owner) is not int or type(root) is not int:
        return False
    if owner <= 1 or root <= 1:
        return False
    seen=set()
    current=owner
    for _ in range(MAX_ANCESTORS):
        if current == root:
            return True
        if current <= 1 or current in seen:
            return False
        seen.add(current)
        try:
            parent=parent_for(current)
        except (OSError,ValueError,TypeError):
            return False
        if type(parent) is not int or parent <= 1 or parent == current:
            return False
        current=parent
    return False


def window_for_process(root, *, runner=subprocess.run,
                       parent_for=_parent_linux):
    """Return one distinct visible X11 window belonging to this emulator run.

    Missing _NET_WM_PID, stale NeXium windows, unrelated processes, an
    ambiguous collection of same-run windows, or failing xdotool all
    result in None. Every use is explicitly scoped to a live subprocess.
    """
    if type(root) is not int or root <= 1:
        return None
    try:
        found=runner(
            ["xdotool","search","--onlyvisible","--name","NeXium"],
            capture_output=True,text=True,timeout=3)
        if (found.returncode != 0 or type(found.stdout) is not str
                or len(found.stdout)>SEARCH_BYTES_LIMIT):
            return None
        raw=[x.strip() for x in found.stdout.splitlines() if x.strip()]
        if len(raw)>WINDOW_LIMIT or any(not re.fullmatch(r"[0-9]{1,10}",x)
                                        for x in raw):
            return None
        ids=list(dict.fromkeys(raw))
        accepted=[]
        for wid in ids:
            response=runner(["xdotool","getwindowpid",wid],
                            capture_output=True,text=True,timeout=3)
            if response.returncode!=0 or type(response.stdout) is not str:
                continue
            value=response.stdout.strip()
            if not re.fullmatch(r"[0-9]{1,10}",value):
                continue
            owner=int(value)
            if belongs_to_run(owner,root,parent_for=parent_for):
                accepted.append(wid)
        return accepted[0] if len(accepted)==1 else None
    except (OSError,ValueError,TypeError,subprocess.SubprocessError):
        return None
