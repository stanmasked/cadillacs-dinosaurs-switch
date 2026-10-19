#!/usr/bin/env python3
"""Bounded, byte-free local ROM metadata stability checks for guarded MAME.

These snapshots remain in process memory: NEVER save, print or publish
individual private names, paths, inode numbers or timestamps. Identical
metadata is not evidence that identical ROM bytes were read by MAME.
"""
from pathlib import Path
import stat

try:
    from tools.mame_private_rom_entry import require_private_dino_entry
except ModuleNotFoundError:
    from mame_private_rom_entry import require_private_dino_entry

MAX_UNPACKED_ENTRIES = 4096


def _fields(metadata):
    return (
        metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_nlink,
        metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns,
    )


def _read_entry(path, *, directory=False):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if directory:
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError('Private dino metadata directory type changed')
    elif not stat.S_ISREG(metadata.st_mode) or metadata.st_size <= 0:
        raise ValueError('Private dino metadata file type or size changed')
    # Linked content can change outside the watched private directory.
    if not directory and metadata.st_nlink != 1:
        raise ValueError('Private dino ROM archive has multiple hard links')
    return _fields(metadata)


def snapshot_private_dino_rom_entries(rom_directory):
    """Observe bounded local dino entries without opening any file bytes.

    Reject symlinks and nested directories within unpacked dino sets:
    guarding *all* possible nested files would require a recursive scan.
    A single normal MAME dino.zip is preferred.
    """
    require_private_dino_entry(rom_directory)
    root = Path(rom_directory)
    if root.is_symlink():
        raise ValueError('Private ROM metadata directory may not be a symlink')
    archive = _read_entry(root / 'dino.zip')
    folder = root / 'dino'
    folder_meta = _read_entry(folder, directory=True)
    children = []
    if folder_meta is not None:
        for n, child in enumerate(folder.iterdir(), 1):
            if n > MAX_UNPACKED_ENTRIES:
                raise ValueError('Private dino metadata set exceeds bounded entries')
            # The name is held only in memory, never in a returned report.
            children.append((child.name, _read_entry(child)))
        if not children:
            raise ValueError('Private dino metadata set is empty')
    return (
        _fields(root.lstat()), archive, folder_meta,
        tuple(sorted(children)),
    )


def require_stable_private_dino_rom_entries(rom_directory, previous):
    """Refuse changed/missing/added/link-replaced local ROM entries.

    Not a content hash, filesystem lock or protection from a malicious
    in-place writer preserving all metadata. Fail closed when uncertain.
    """
    if (not isinstance(previous, tuple) or len(previous) != 4 or
            snapshot_private_dino_rom_entries(rom_directory) != previous):
        raise ValueError('Private dino ROM metadata changed; capture refused')
    return True
