#!/usr/bin/env python3
"""Check the 54 exact private MAME frame files stayed byte-identical.

Two snapshots bracket the CRC32/FNV/RGB/interval audit. SHA-256 digests
and filesystem identities are kept only in memory, never saved to JSON or
sent to GitHub. This detects accidental mid-audit edits, not an adversarial
emulator or a continuously immutable filesystem.
"""
import hashlib
import os
from pathlib import Path
import stat

try:
    from tools.mame_obj_sequence_alignment import CAPTURE_SIZES
except ModuleNotFoundError:
    from mame_obj_sequence_alignment import CAPTURE_SIZES

OTHER_SIZES = {
    'manifest.json': 16 * 1024,   # maximum; JSON lengths vary
    'render-regs-be.bin': 128,
    'buffered-obj-be.bin': 2048,
    'obj-latch-count.txt': 80,     # maximum; V2 text lengths vary
}
EXPECTED_SIZES = {**CAPTURE_SIZES, **OTHER_SIZES}
VARIABLE_LENGTH = frozenset(('manifest.json', 'obj-latch-count.txt'))
MAX_TOTAL_FILES = 24 * len(EXPECTED_SIZES)


def private_capture_file_snapshot(directory, first_frame=900,
                                  frame_count=6, frame_step=2):
    """Read exact regular files with no symlink following and bounded hashing.

    Requires a completed private game session; never operates on ROMs.
    The returned mapping is for *internal use only*, not a saved report.
    """
    if (type(first_frame) is not int or not 0 <= first_frame <= 99999999
            or type(frame_count) is not int or not 4 <= frame_count <= 24
            or type(frame_step) is not int or not 1 <= frame_step <= 120
            or first_frame + (frame_count - 1) * frame_step > 99999999):
        raise ValueError('Invalid bounded private capture snapshot interval')
    root = Path(directory)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Private capture directory is invalid or symlinked')
    expected = {
        f'frame-{first_frame + i * frame_step:08d}.{suffix}': (size, suffix)
        for i in range(frame_count)
        for suffix, size in EXPECTED_SIZES.items()
    }
    if len(expected) > MAX_TOTAL_FILES:
        raise ValueError('Too many private capture files')
    actual = set(os.listdir(root))
    if actual != set(expected):
        raise ValueError('Private MAME capture has missing or unexpected files')

    snapshots = {}
    for name in sorted(expected):
        max_size, suffix = expected[name]
        path = root / name
        entry = path.lstat()
        if not stat.S_ISREG(entry.st_mode) or entry.st_nlink != 1:
            raise ValueError('Private MAME capture contains a nonregular or linked file')
        flags = os.O_RDONLY
        if hasattr(os, 'O_NOFOLLOW'):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            if (not stat.S_ISREG(opened.st_mode) or
                    opened.st_ino != entry.st_ino or
                    opened.st_dev != entry.st_dev or
                    opened.st_nlink != 1):
                raise ValueError('Private MAME capture file changed during open')
            size = opened.st_size
            if (size < 1 or size > max_size or
                    (suffix not in VARIABLE_LENGTH and size != max_size)):
                raise ValueError('Private MAME capture file size is invalid')
            digest = hashlib.sha256()
            total = 0
            while True:
                data = os.read(fd, min(64 * 1024, size - total + 1))
                if not data:
                    break
                total += len(data)
                if total > max_size:
                    raise ValueError('Private MAME capture changed while being read')
                digest.update(data)
            after = os.fstat(fd)
            if (total != size or after.st_size != size or
                    after.st_ino != opened.st_ino or
                    after.st_mtime_ns != opened.st_mtime_ns or
                    after.st_ctime_ns != opened.st_ctime_ns):
                raise ValueError('Private MAME capture changed while being hashed')
            snapshots[name] = (
                opened.st_dev, opened.st_ino, opened.st_size,
                opened.st_mtime_ns, opened.st_ctime_ns, digest.digest())
        finally:
            os.close(fd)
    if set(os.listdir(root)) != set(expected):
        raise ValueError('Private MAME capture file set changed during scan')
    return snapshots


def require_stable_private_capture(directory, snapshot, first_frame=900,
                                   frame_count=6, frame_step=2):
    """Reject any file addition/removal, inode replacement or content edit."""
    if not isinstance(snapshot, dict):
        raise ValueError('Invalid private capture snapshot')
    current = private_capture_file_snapshot(
        directory, first_frame, frame_count, frame_step)
    if current != snapshot:
        raise ValueError('Private MAME capture changed during the audit')
    return {
        'source_files_checked': len(current),
        'source_files_unchanged_during_audit': True,
        'hash_algorithm': 'SHA256_LOCAL_ONLY_NO_DIGESTS_PUBLISHED',
        'filesystem_snapshot_not_hardware_provenance': True,
        'diagnostic_only': True,
        'real_game_authenticity_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
