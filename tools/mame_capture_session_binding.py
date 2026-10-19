"""Fail closed when Lua and C++ capture files are from different MAME sessions.

An unpredictable launcher-supplied label is an accidental-mixing guard,
NOT a signature of an authentic original game, trusted MAME process or VBlank.
The token is not included in saved diagnostic JSON or external logs.
"""
import json
from pathlib import Path
import re

SESSION_RE = re.compile(r'[0-9a-f]{32}\Z')
LATCH_RE = re.compile(
    rb'CPS1_DINO_LATCH_V2 (0|[1-9][0-9]*) [0-9a-f]{16}\n'
    rb'CPS1_DINO_SESSION ([0-9a-f]{32})\n\Z')


def require_private_capture_session(directory, expected_session,
                                    first_frame=900, frame_count=6, frame_step=2):
    if (type(expected_session) is not str or
            SESSION_RE.fullmatch(expected_session) is None):
        raise ValueError('Invalid local capture session label')
    if (type(first_frame) is not int or not 0 <= first_frame <= 99999999 or
            type(frame_count) is not int or not 4 <= frame_count <= 24 or
            type(frame_step) is not int or not 1 <= frame_step <= 120 or
            first_frame + (frame_count - 1) * frame_step > 99999999):
        raise ValueError('Invalid bounded local capture interval')
    root = Path(directory)
    for i in range(frame_count):
        stem = f'frame-{first_frame + i * frame_step:08d}'
        with (root / (stem + '.manifest.json')).open('rb') as file:
            source = file.read(16 * 1024 + 1)
        if len(source) > 16 * 1024:
            raise ValueError('Private Lua manifest too large for session validation')
        try:
            manifest = json.loads(source)
        except (ValueError, UnicodeError) as exc:
            raise ValueError('Malformed private Lua session manifest') from exc
        if (not isinstance(manifest, dict) or
                manifest.get('capture_session') != expected_session):
            raise ValueError('Private Lua capture session label mismatch')
        with (root / (stem + '.obj-latch-count.txt')).open('rb') as file:
            line = file.read(129)
        if len(line) > 128:
            raise ValueError('Private C++ latch session sidecar too large')
        match = LATCH_RE.fullmatch(line)
        if not match or match.group(2).decode('ascii') != expected_session:
            raise ValueError('Private C++ capture session label mismatch')
    return {
        'status': 'SAME_LAUNCHER_SESSION_LABEL_OBSERVED',
        'diagnostic_only': True,
        'lua_manifest_session_samples': frame_count,
        'cpp_latch_session_samples': frame_count,
        'shared_session_label_consistent': True,
        'label_is_authenticated_game_provenance': False,
        'active_gameplay_verified': False,
        'hardware_vblank_observed': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
