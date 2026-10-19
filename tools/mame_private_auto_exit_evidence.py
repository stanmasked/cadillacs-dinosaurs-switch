#!/usr/bin/env python3
"""Fixed-line, bounded local MAME exit marker observation; never publish logs."""
import os
from pathlib import Path
import stat

LOG_NAME = 'dino-mame-private-session.log'
MAX_LOG_SCAN_BYTES = 16 * 1024 * 1024
READY_LINE = b'CPS1_DINO_AUTO_EXIT_V1_READY_54_SIZE_ONLY'
GRACE_LINE = b'CPS1_DINO_AUTO_EXIT_V1_GRACE_INCOMPLETE_SIZE_ONLY'


def _result(status, observed):
    return {
        'status': status,
        'marker_observed': observed,
        'read_private_mame_log_locally': True,
        'observed_message_not_independent_proof': True,
        'rom_bytes_read': False,
        'capture_bytes_read': False,
        'frame_sync_verified': False,
        'original_game_authenticity_verified': False,
        'pixel_parity_eligible': False,
    }


def private_mame_auto_exit_log_observation(workspace):
    """Return only a fixed code, never game logs, private paths or original bytes."""
    try:
        filename = Path(workspace) / LOG_NAME
        entry = filename.lstat()
        if (not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1 or
                not 0 <= entry.st_size <= MAX_LOG_SCAN_BYTES):
            return _result('LOCAL_MAME_AUTO_EXIT_LOG_REFUSED', False)
        flags = os.O_RDONLY
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        if hasattr(os, 'O_CLOEXEC'):
            flags |= os.O_CLOEXEC
        fd = os.open(filename, flags)
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                    before.st_dev != entry.st_dev or
                    before.st_ino != entry.st_ino or
                    before.st_size != entry.st_size):
                return _result('LOCAL_MAME_AUTO_EXIT_LOG_REFUSED', False)
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                raw = stream.read(MAX_LOG_SCAN_BYTES + 1)
            after = os.fstat(fd)
            if (len(raw) != before.st_size or
                    before.st_size != after.st_size or
                    before.st_mtime_ns != after.st_mtime_ns or
                    before.st_ctime_ns != after.st_ctime_ns or
                    len(raw) > MAX_LOG_SCAN_BYTES):
                return _result('LOCAL_MAME_AUTO_EXIT_LOG_REFUSED', False)
        finally:
            os.close(fd)
        ready = grace = 0
        for line in raw.splitlines():
            if line == READY_LINE:
                ready += 1
            elif line == GRACE_LINE:
                grace += 1
        if ready == 1 and grace == 0:
            return _result('LOCAL_LUA_REPORTED_SIZE_READY_EXIT', True)
        if grace == 1 and ready == 0:
            return _result('LOCAL_LUA_REPORTED_GRACE_LIMIT_EXIT', True)
        if ready or grace:
            return _result('LOCAL_MAME_AUTO_EXIT_MARKERS_AMBIGUOUS', False)
        return _result('LOCAL_MAME_AUTO_EXIT_MARKER_NOT_OBSERVED', False)
    except (OSError, ValueError, TypeError):
        return _result('LOCAL_MAME_AUTO_EXIT_LOG_REFUSED', False)
