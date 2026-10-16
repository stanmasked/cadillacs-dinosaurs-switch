#!/usr/bin/env python3
"""Validate a local MAME 3.x INP header for CPS-1 dino input replay.

MAME reference: src/emu/ioport.cpp inp_header (64-byte MAMEINP header).
A valid header does not prove runtime replay synchronization.
"""
import hashlib
from pathlib import Path

MAX_INPUT_BYTES = 64 * 1024 * 1024
HEADER_BYTES = 64
MAGIC = b'MAMEINP\0'
SUPPORTED_MAJOR = 3
SYSTEM_NAME = b'dino'


def read_header(header):
    """Validate original MAME 64-byte INP header and target game."""
    if len(header) != HEADER_BYTES:
        raise ValueError('MAME INP is missing its 64-byte header')
    if header[:8] != MAGIC:
        raise ValueError('MAME INP magic is incorrect or unsupported')
    major, minor = header[0x10], header[0x11]
    if major != SUPPORTED_MAJOR:
        raise ValueError(f'Unsupported MAME INP major version {major}')
    game = header[0x14:0x20].split(b'\0', 1)[0]
    if game != SYSTEM_NAME:
        raise ValueError('MAME INP recording targets a different system, not dino')
    return {'system': 'dino', 'format_major': major, 'format_minor': minor,
            'header_validated': True}


def playback_plan(input_path):
    """Return direct subprocess flags and non-content provenance.

    Reject symlinks to avoid accidentally referencing an unreviewed file.
    Hash the complete file, but never include the contents or source path in
    the serializable metadata. None explicitly disables input replay.
    """
    if input_path is None:
        return [], {'enabled': False, 'input_replay_verified': False}
    path = Path(input_path).expanduser()
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != '.inp':
        raise ValueError('Recorded input must be a regular, non-symlink .inp file')
    size = path.stat().st_size
    if not HEADER_BYTES < size <= MAX_INPUT_BYTES:
        raise ValueError('Recorded input size must exceed the 64-byte header and be <=67108864 bytes')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        header = stream.read(HEADER_BYTES)
        parsed = read_header(header)
        digest.update(header)
        for chunk in iter(lambda: stream.read(131072), b''):
            digest.update(chunk)
    if path.stat().st_size != size:
        raise ValueError('Input replay file changed during initial inspection')
    return ['-playback', str(path.resolve())], {
        'enabled': True,
        'bytes': size,
        'sha256': digest.hexdigest(),
        **parsed,
        'input_replay_verified': False,
        'note': 'Correct INP header is not proof of MAME replay synchronisation',
    }


def confirm_playback_unchanged(input_path, original_metadata):
    """Fail if replay data changed during MAME invocation."""
    if not original_metadata.get('enabled'):
        return True
    try:
        _, current = playback_plan(input_path)
    except (ValueError, OSError):
        return False
    return (current['bytes'] == original_metadata['bytes'] and
            current['sha256'] == original_metadata['sha256'])
