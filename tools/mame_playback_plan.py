#!/usr/bin/env python3
"""Validate locally recorded MAME input for deterministic capture attempts.

The INP's contents are neither parsed as genuine nor redistributed here;
MAME itself must decide whether replay is compatible with the system.
"""
import hashlib
from pathlib import Path

MAX_INPUT_BYTES = 64 * 1024 * 1024


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
    if not 1 <= size <= MAX_INPUT_BYTES:
        raise ValueError('Recorded input size must be 1..67108864 bytes')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(131072), b''):
            digest.update(chunk)
    if path.stat().st_size != size:
        raise ValueError('Input replay file changed during initial inspection')
    return ['-playback', str(path.resolve())], {
        'enabled': True,
        'bytes': size,
        'sha256': digest.hexdigest(),
        'input_replay_verified': False,
        'note': 'MAME INP compatibility and desync have not been established',
    }


def confirm_playback_unchanged(input_path, original_metadata):
    """Fail if replay data changed during MAME invocation."""
    if not original_metadata.get('enabled'):
        return True
    _, current = playback_plan(input_path)
    return (current['bytes'] == original_metadata['bytes'] and
            current['sha256'] == original_metadata['sha256'])
