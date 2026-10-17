#!/usr/bin/env python3
"""Bounded private SHA-256 checks for the local owned dino game set.

Original ROM bytes are read *locally* by Python in guarded/verify-only
modes; never print, persist, export, upload, or put SHA digests in reports.
This is NOT an independent authentication of the game's provenance and
not an atomic lock against a malicious concurrent writer.
"""
import hashlib
import os
from pathlib import Path
import stat

try:
    from tools.mame_private_rom_metadata import (
        snapshot_private_dino_rom_entries, _fields,
    )
except ModuleNotFoundError:
    from mame_private_rom_metadata import (
        snapshot_private_dino_rom_entries, _fields,
    )

MAX_ROM_TOTAL_BYTES = 256 * 1024 * 1024
MAX_ROM_FILE_BYTES = 256 * 1024 * 1024
READ_CHUNK_SIZE = 1024 * 1024


def _file_digest(path, expected_metadata):
    """Hash only an ordinary single-link file with stable fstat metadata."""
    flags = os.O_RDONLY
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    if hasattr(os, 'O_CLOEXEC'):
        flags |= os.O_CLOEXEC
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or
                not 0 < before.st_size <= MAX_ROM_FILE_BYTES or
                _fields(before) != expected_metadata):
            raise ValueError('Private dino ROM content snapshot refused')
        sha = hashlib.sha256()
        total = 0
        while True:
            block = os.read(fd, READ_CHUNK_SIZE)
            if not block:
                break
            total += len(block)
            if total > before.st_size or total > MAX_ROM_FILE_BYTES:
                raise ValueError('Private dino ROM content exceeds bounded size')
            sha.update(block)
        after = os.fstat(fd)
        if total != before.st_size or _fields(after) != expected_metadata:
            raise ValueError('Private dino ROM content changed while hashing')
        return sha.digest()
    finally:
        os.close(fd)


def snapshot_private_dino_rom_content(rom_directory):
    """Keep private metadata and SHA-256 byte digests *only in memory*.

    The Stage 88 metadata pass rejects unsafe paths/nested entries.
    Files are re-checked via fstat before/after bounded streaming reads.
    The two snapshots reject visible concurrent entry swaps.
    """
    roms = Path(rom_directory)
    before = snapshot_private_dino_rom_entries(roms)
    _, archive, unpacked, children = before
    total = (archive[4] if archive is not None else 0)
    total += sum(meta[4] for _, meta in children)
    if not 0 < total <= MAX_ROM_TOTAL_BYTES:
        raise ValueError('Private dino ROM content exceeds bounded total size')
    digests = []
    if archive is not None:
        digests.append(('dino.zip', _file_digest(roms / 'dino.zip', archive)))
    if unpacked is not None:
        for name, meta in children:
            digests.append((name, _file_digest(roms / 'dino' / name, meta)))
    if snapshot_private_dino_rom_entries(roms) != before:
        raise ValueError('Private dino ROM metadata changed while hashing')
    return before, tuple(digests)


def require_stable_private_dino_rom_content(rom_directory, expected):
    """Refuse metadata or SHA-256 content drift, never exposing the digest."""
    if not isinstance(expected, tuple) or len(expected) != 2:
        raise ValueError('Private dino ROM content snapshot invalid')
    try:
        current = snapshot_private_dino_rom_content(rom_directory)
    except (ValueError, OSError) as exc:
        raise ValueError('Private dino ROM content changed; capture refused') from exc
    if current != expected:
        raise ValueError('Private dino ROM content changed; capture refused')
    return True
