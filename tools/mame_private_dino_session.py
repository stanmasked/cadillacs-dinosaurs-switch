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
import tempfile

try:
    from tools.mame_dino_binary_verify import inspect_binary
    from tools.mame_obj_sequence_alignment import main as alignment_main
    from tools.mame_reference_activity import reference_activity_diagnostic
    from tools.mame_multistream_interval_evidence import multistream_interval_evidence
except ModuleNotFoundError:
    from mame_dino_binary_verify import inspect_binary
    from mame_obj_sequence_alignment import main as alignment_main
    from mame_reference_activity import reference_activity_diagnostic
    from mame_multistream_interval_evidence import multistream_interval_evidence

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
    # On a public repository, even an accidentally added local ROM or
    # modified upstream MAME source tree could be exposed. Keep BOTH out.
    if (not _separate(roms, PROJECT_ROOT) or
            not _separate(tree, PROJECT_ROOT)):
        raise ValueError('ROM and full MAME source trees must stay outside the project')
    if not private.is_dir():
        raise ValueError('Private workspace directory must already exist')
    if any(not _separate(private, other) for other in
           (PROJECT_ROOT, tree, roms)):
        raise ValueError('Capture workspace must be separate from code, MAME and ROM trees')
    if os.name == 'posix' and (private.stat().st_mode & 0o077):
        raise ValueError('Private workspace must have 0700-style permissions')
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

    # The multi-frame CLI writes JSON before the later RGB and
    # multi-stream checks. Keep its result in a PRIVATE TEMPORARY
    # DIRECTORY so a late failure never leaves a final-looking report.
    # The final report is published via hard-link (exclusive, atomic,
    # same filesystem) ONLY after all checks have succeeded.
    report = private / REPORT_NAME
    with tempfile.TemporaryDirectory(
            prefix='.dino-audit-pending-', dir=private) as staging_dir:
        staging = Path(staging_dir)
        raw_audit = staging / 'alignment.json'
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            code = alignment_main([
                str(capture_dir), '--first-frame', str(FIRST_FRAME),
                '--frame-count', str(FRAME_COUNT),
                '--frame-step', str(FRAME_STEP),
                '--latch-count-evidence', '--out', str(raw_audit),
            ])
        if code != 0 or not raw_audit.is_file():
            raise ValueError('Private capture is incomplete or invalid; no verified report')
        with raw_audit.open('rb') as source:
            data = source.read(128 * 1024 + 1)
        if len(data) > 128 * 1024:
            raise ValueError('Unexpected oversized local diagnostic JSON')
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError('Unexpected private diagnostic report structure')
        latch = result.get('obj_latch_count_evidence')
        if not isinstance(latch, dict) or (
                latch.get('sidecar_format_version') != 2 or
                latch.get('obj_byte_fingerprint_verified_count') != FRAME_COUNT or
                latch.get('obj_byte_fingerprint_binding') != 'FNV1A64_ALL_SAMPLES_MATCHED' or
                result.get('frame_sync_verified') is not False or
                result.get('pixel_parity_eligible') is not False):
            raise ValueError('Capture report does not satisfy conservative V2 requirements')

        # These checks may fail independently of all earlier CRC/FNV
        # checks; NO final report must be published until they pass.
        activity = reference_activity_diagnostic(
            capture_dir, FIRST_FRAME, FRAME_COUNT, FRAME_STEP)
        intervals = multistream_interval_evidence(
            result, activity, FIRST_FRAME, FRAME_STEP, FRAME_COUNT)
        result['reference_activity'] = activity
        result['multistream_interval_evidence'] = intervals
        result['private_capture_completion'] = {
            'status': 'PRIVATE_CAPTURE_INTEGRITY_VERIFIED_ONLY',
            'full_check_sequence_completed': True,
            'diagnostic_only': True,
            'nominal_frame_count': FRAME_COUNT,
            'crc32_lua_components_checked': FRAME_COUNT * 5,
            'v2_bound_obj_samples': FRAME_COUNT,
            'original_game_authenticity_verified': False,
            'active_gameplay_verified': False,
            'obj_latch_age_verified': False,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        }

        complete = staging / 'completed.json'
        with complete.open('x', encoding='utf-8') as output:
            json.dump(result, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.chmod(complete, 0o600)
        # Unlike os.replace(), hard-link creation refuses a concurrent
        # existing target; the finalized report can never be clobbered.
        os.link(complete, report)

    return {
        'status': 'PRIVATE_CAPTURE_INTEGRITY_VERIFIED_ONLY',
        'reference_activity': activity,
        'multistream_interval_evidence': intervals,
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
            'files. Reference activity is structural and cannot prove active '
            'gameplay. Physical VBlank ordering, displayed pixel parity and '
            'Nintendo Switch gameplay remain unverified.'
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
