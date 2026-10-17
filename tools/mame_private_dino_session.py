#!/usr/bin/env python3
"""Launch a user-owned dino game in a locally built, instrumented MAME 0.289.

No ROMs or captured game data are bundled, uploaded or printed. This program
never accesses ROM contents directly. It requires an existing private
workspace outside the project, ROM directory and upstream MAME build tree.

The real game must be operated/closed locally by the user. Success is only
a complete, locally verified 6-frame diagnostic capture; NEVER frame parity.
"""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys

try:
    from tools.mame_dino_binary_verify import inspect_binary
    from tools.mame_obj_sequence_alignment import main as alignment_main
except ModuleNotFoundError:
    from mame_dino_binary_verify import inspect_binary
    from mame_obj_sequence_alignment import main as alignment_main

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LUA_SCRIPT = PROJECT_ROOT / 'tools' / 'mame_cps1_capture.lua'
CAPTURE_DIR_NAME = 'cps1-captures'
REPORT_NAME = 'dino-latch-diagnostic.json'
LOG_NAME = 'dino-mame-private-session.log'
FIRST_FRAME = 900
FRAME_COUNT = 6
FRAME_STEP = 2


def _separate(left, right):
    """Neither resolved tree may contain the other (even via symlinks)."""
    return not (left == right or left.is_relative_to(right) or
                right.is_relative_to(left))


def preflight(mame, mame_source_tree, rom_dir, workspace):
    """Check only filesystem and path isolation; do not execute/read ROMs."""
    # Refuse executable symlinks before resolve() erases that fact.
    if Path(mame).expanduser().is_symlink():
        raise ValueError('MAME executable may not be a symlink')
    paths = tuple(Path(x).expanduser().resolve() for x in (
        mame, mame_source_tree, rom_dir, workspace))
    binary, tree, roms, private = paths
    if (not binary.is_file() or binary.is_symlink() or
            not os.access(binary, os.X_OK)):
        raise ValueError('Instrumented MAME executable is missing or not executable')
    if not tree.is_dir() or not (tree / 'src/mame/capcom/cps1_v.cpp').is_file():
        raise ValueError('Full upstream MAME source directory is missing')
    if not roms.is_dir():
        raise ValueError('Private ROM directory is missing')
    if not private.is_dir():
        raise ValueError('Private workspace directory must already exist')
    if os.name == 'posix' and (private.stat().st_mode & 0o077):
        raise ValueError('Private workspace must have 0700-style permissions')
    if any(not _separate(private, other) for other in
           (PROJECT_ROOT, tree, roms)):
        raise ValueError('Capture workspace must be separate from code, MAME and ROM trees')
    if not LUA_SCRIPT.is_file():
        raise ValueError('MAME capture Lua script not found in project')
    # Do not modify previously captured private bytes or diagnostic reports.
    for name in (CAPTURE_DIR_NAME, REPORT_NAME, LOG_NAME):
        if (private / name).exists() or (private / name).is_symlink():
            raise ValueError('Capture workspace already contains session outputs')
    return binary, tree, roms, private


def execute_private_capture(mame, mame_source_tree, rom_dir, workspace,
                            *, timeout_seconds=1800, preflight_only=False):
    """Run full MAME locally, then audit all private files with strict checks."""
    if (type(timeout_seconds) is not int or
            not 30 <= timeout_seconds <= 3600):
        raise ValueError('Session timeout must be 30..3600 seconds')
    if type(preflight_only) is not bool:
        raise ValueError('preflight_only must be boolean')
    binary, tree, roms, private = preflight(
        mame, mame_source_tree, rom_dir, workspace)
    if preflight_only:
        return {
            'status': 'FILESYSTEM_PREFLIGHT_ONLY',
            'game_executed': False,
            'capture_verified': False,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        }

    # Real upstream driver and instrumented ELF identity. This only runs
    # -listxml, not any arcade game, and never loads ROM bytes.
    identity = inspect_binary(binary, tree)
    if (identity.get('driver') != 'dino' or
            identity.get('compiled_instrumented_latch_v2_format') is not True):
        raise ValueError('MAME identity/compiled V2 probe verification failed')

    capture_dir = private / CAPTURE_DIR_NAME
    # Never create outputs until the real build identity passed.
    capture_dir.mkdir(mode=0o700, exist_ok=False)
    argv = [
        str(binary), 'dino', '-rompath', str(roms),
        '-autoboot_script', str(LUA_SCRIPT),
    ]
    # Capture potential private ROM filenames and local MAME messages to
    # a PRIVATE log rather than CI or console. No shell or network used.
    try:
        # O_EXCL protects earlier logs; 0600 avoids leaking filenames
        # from emulator diagnostics on multi-user machines.
        fd = os.open(private / LOG_NAME,
                     os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'wb') as log:
            proc = subprocess.run(
                argv, cwd=private, stdout=log, stderr=subprocess.STDOUT,
                stdin=None, timeout=timeout_seconds, check=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Local MAME session timed out; private files retained') from exc
    except OSError as exc:
        raise ValueError('Unable to execute local MAME; private files retained') from exc
    if proc.returncode != 0:
        raise ValueError('Local MAME exited unsuccessfully; check private log locally')

    # Real audit output stays in the supplied private workspace. The
    # multiframe CLI enforces all 5 CRC32 files, C++ probe size, and
    # V2 OBJ-latch FNV binding. Never relax its diagnostic-only flags.
    report = private / REPORT_NAME
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        code = alignment_main([
            str(capture_dir), '--first-frame', str(FIRST_FRAME),
            '--frame-count', str(FRAME_COUNT),
            '--frame-step', str(FRAME_STEP),
            '--latch-count-evidence', '--out', str(report),
        ])
    if code != 0 or not report.is_file():
        raise ValueError('Private capture is incomplete or invalid; no verified report')
    # Reading our own small diagnostic metadata does not expose source data.
    with report.open('rb') as source:
        data = source.read(128 * 1024 + 1)
    if len(data) > 128 * 1024:
        raise ValueError('Unexpected oversized local diagnostic JSON')
    os.chmod(report, 0o600)
    result = json.loads(data)
    latch = result.get('obj_latch_count_evidence', {})
    if (latch.get('sidecar_format_version') != 2 or
            latch.get('obj_byte_fingerprint_verified_count') != FRAME_COUNT or
            latch.get('obj_byte_fingerprint_binding') != 'FNV1A64_ALL_SAMPLES_MATCHED' or
            result.get('frame_sync_verified') is not False or
            result.get('pixel_parity_eligible') is not False):
        raise ValueError('Capture report does not satisfy conservative V2 requirements')
    return {
        'status': 'PRIVATE_CAPTURE_INTEGRITY_VERIFIED_ONLY',
        'nominal_frame_count': FRAME_COUNT,
        'crc32_lua_components_checked': FRAME_COUNT * 5,
        'bound_cpp_obj_samples': FRAME_COUNT,
        'game_executed': True,
        'original_game_authenticity_verified': False,
        'obj_latch_age_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
        'warning': (
            'The locally started MAME game emitted internally consistent '
            'files. The run itself, physical VBlank ordering, displayed '
            'pixel parity and Nintendo Switch gameplay remain unverified.'
        ),
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mame', type=Path, required=True)
    p.add_argument('--mame-tree', type=Path, required=True)
    p.add_argument('--rom-dir', type=Path, required=True)
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--timeout-seconds', type=int, default=1800)
    p.add_argument('--preflight-only', action='store_true',
                   help='Only validate isolated paths; no ROM reading or MAME execution')
    args = p.parse_args(argv)
    try:
        result = execute_private_capture(
            args.mame, args.mame_tree, args.rom_dir, args.workspace,
            timeout_seconds=args.timeout_seconds,
            preflight_only=args.preflight_only)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        # All raised messages are deliberately generic (no private file paths).
        print('Private MAME capture refused:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
