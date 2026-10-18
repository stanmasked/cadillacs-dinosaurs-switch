#!/usr/bin/env python3
"""Guard NeXium fallback input from resetting an in-flight guest audio test.

The optional host pixel sampler may report inconclusive even after all five
real guest HID effects completed. Repeating Y at that point resets the arena
while its 900-tick audio window is active, invalidating queue-accounting.
Only inspect fixed ROM-free guest witness filenames. Never print paths/data.
"""
import os
from pathlib import Path
import sys


WITNESS='cadillacs-controller-selftest.csv'
STRESS='cadillacs-audio-stress.csv'


def may_send_fallback(roots):
    """True ONLY when no guest completion/stress state is observed."""
    seen=set()
    for directory in roots:
        parent=Path(directory)
        if not parent.is_dir() or parent.is_symlink():
            continue
        root=os.fspath(parent.resolve())
        if root in seen:
            continue
        seen.add(root)
        for current, subdirs, filenames in os.walk(root,followlinks=False):
            # Avoid descending into symlinked emulator directories.
            subdirs[:]=[d for d in subdirs
                        if not (Path(current)/d).is_symlink()]
            for name in filenames:
                if name not in (WITNESS,STRESS):
                    continue
                file=Path(current)/name
                # Inconclusive private files must never trigger new input.
                if file.is_symlink() or not file.is_file():
                    return False
                if name==STRESS:
                    # Any open stress file means an attempt started.
                    # It must not be interrupted even if malformed.
                    return False
                try:
                    if not 1<=file.stat().st_size<=1024:
                        return False
                    raw=file.read_bytes()
                    if len(raw)>1024:
                        return False
                    lines=raw.decode('ascii').splitlines()
                except (OSError,UnicodeError):
                    return False
                if any(line.startswith('INPUT_DONE,31,') for line in lines):
                    return False
    return True


def main(argv=None):
    roots=sys.argv[1:] if argv is None else argv
    if not roots:
        return 1
    try:
        return 0 if may_send_fallback(roots) else 1
    except (OSError,ValueError):
        return 1


if __name__=='__main__':
    raise SystemExit(main())
