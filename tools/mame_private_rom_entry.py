#!/usr/bin/env python3
"""Structural dino ROM-entry presence check; no archive/ROM bytes are read.

The original game stays outside the project and MAME build source tree.
A filename with nonempty data is NOT proof the ROMs are valid, complete,
legally owned, or accepted by the emulator. This is non-adversarial preflight.
"""
import stat
from pathlib import Path


def _safe_metadata(path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def require_private_dino_entry(rom_directory):
    """Require an ordinary dino.zip or unpacked dino/ directory.

    Only directory entries, types and nonzero lengths are inspected; no
    archive decompression, file reads, names or paths in the returned result.
    """
    directory = Path(rom_directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError('Private ROM directory must be an ordinary directory')
    zip_path = directory / 'dino.zip'
    folder_path = directory / 'dino'
    zip_entry = _safe_metadata(zip_path)
    folder_entry = _safe_metadata(folder_path)
    if zip_entry is not None and (
            not stat.S_ISREG(zip_entry.st_mode) or zip_entry.st_size <= 0):
        raise ValueError('Private dino archive must be a nonempty regular file')
    if folder_entry is not None and not stat.S_ISDIR(folder_entry.st_mode):
        raise ValueError('Private unpacked dino set must be a real directory')

    unpacked_present = False
    if folder_entry is not None:
        # A single ordinary nonempty top-level game image is sufficient to
        # establish structural presence; names/data are never persisted.
        # Reject any links, even if an ordinary file is also present.
        num_entries = 0
        for candidate in folder_path.iterdir():
            num_entries += 1
            if num_entries > 4096:
                raise ValueError('Private unpacked dino directory has too many entries')
            candidate_meta = _safe_metadata(candidate)
            if candidate_meta is None or stat.S_ISLNK(candidate_meta.st_mode):
                raise ValueError('Private unpacked dino set contains unsafe entries')
            if stat.S_ISREG(candidate_meta.st_mode) and candidate_meta.st_size > 0:
                unpacked_present = True
        if not unpacked_present:
            raise ValueError('Private unpacked dino set contains no nonempty files')

    if zip_entry is None and not unpacked_present:
        raise ValueError('No private dino set entry found for first-run preflight')
    return {
        'status': 'PRIVATE_DINO_ROM_ENTRY_PRESENT_UNVALIDATED',
        'diagnostic_only': True,
        'game_set_entry_observed': True,
        'rom_file_bytes_read': False,
        'rom_integrity_verified': False,
        'rom_set_completeness_verified': False,
        'original_game_authenticity_verified': False,
        'game_executed': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
