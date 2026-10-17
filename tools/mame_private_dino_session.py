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
import secrets
from pathlib import Path
import subprocess
import sys
import tempfile

try:
    from tools.mame_dino_binary_verify import inspect_binary
    from tools.mame_obj_sequence_alignment import main as alignment_main
    from tools.mame_reference_activity import reference_activity_diagnostic
    from tools.mame_multistream_interval_evidence import multistream_interval_evidence
    from tools.mame_private_capture_stability import (private_capture_file_snapshot,
                                                     require_stable_private_capture)
    from tools.mame_capture_session_binding import require_private_capture_session
    from tools.mame_private_interval_consistency import private_nominal_interval_consistency
except ModuleNotFoundError:
    from mame_dino_binary_verify import inspect_binary
    from mame_obj_sequence_alignment import main as alignment_main
    from mame_reference_activity import reference_activity_diagnostic
    from mame_multistream_interval_evidence import multistream_interval_evidence
    from mame_private_capture_stability import (private_capture_file_snapshot,
                                               require_stable_private_capture)
    from mame_capture_session_binding import require_private_capture_session
    from mame_private_interval_consistency import private_nominal_interval_consistency

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


def preflight_mame_build(mame, mame_source_tree):
    """Check the local emulator build paths; require no ROM or workspace."""
    # Refuse executable symlinks before resolve() erases that fact.
    if Path(mame).expanduser().is_symlink():
        raise ValueError('MAME executable may not be a symlink')
    binary, tree = (Path(x).expanduser().resolve()
                    for x in (mame, mame_source_tree))
    if (not binary.is_file() or binary.is_symlink() or
            not os.access(binary, os.X_OK)):
        raise ValueError('Instrumented MAME executable is missing or not executable')
    if not tree.is_dir() or not (tree / 'src/mame/capcom/cps1_v.cpp').is_file():
        raise ValueError('Full upstream MAME source directory is missing')
    if not _separate(tree, PROJECT_ROOT):
        raise ValueError('Full MAME source tree must stay outside the project')
    # A modified executable accidentally stored inside the public Git
    # checkout could later be committed by a broad git add. Prevent this
    # even when its associated build/source tree is elsewhere.
    if not _separate(binary, PROJECT_ROOT):
        raise ValueError('MAME executable must stay outside the project')
    return binary, tree


def preflight(mame, mame_source_tree, rom_dir, workspace):
    """Check only filesystem and path isolation; do not execute/read ROMs."""
    binary, tree = preflight_mame_build(mame, mame_source_tree)
    roms, private = (Path(x).expanduser().resolve()
                     for x in (rom_dir, workspace))
    if not roms.is_dir():
        raise ValueError('Private ROM directory is missing')
    # Do not place commercially owned ROM data in the disposable MAME
    # source/build tree, which may be copied, cleaned or archived later.
    # Also refuse a ROM tree that contains the MAME executable itself.
    if not _separate(roms, tree) or not _separate(roms, binary):
        raise ValueError('Private ROM directory must be separate from MAME build')
    # On a public repository, even an accidentally added local ROM
    # could be exposed; keep original game content out of the repo.
    if not _separate(roms, PROJECT_ROOT):
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


def _require_session_aware_build(binary, tree):
    """ROM-free verified MAME driver, compiler object and linked executable."""
    identity = inspect_binary(binary, tree)
    if (identity.get('driver') != 'dino' or
            identity.get('listxml_validated') is not True or
            identity.get('compiled_instrumented_latch_v2_format') is not True or
            identity.get('compiled_session_label_probe_marker') is not True or
            identity.get('compiled_session_environment_probe_marker') is not True or
            identity.get('linked_dino_executable_probe_markers') is not True):
        raise ValueError('MAME identity/session-aware linked probe verification failed')
    return identity


def execute_private_capture(mame, mame_source_tree, rom_dir=None, workspace=None,
                            *, timeout_seconds=1800, preflight_only=False,
                            verify_build_only=False):
    """Run full MAME locally, then audit all private files with strict checks."""
    if (type(timeout_seconds) is not int or
            not 30 <= timeout_seconds <= 3600):
        raise ValueError('Session timeout must be 30..3600 seconds')
    if type(preflight_only) is not bool:
        raise ValueError('preflight_only must be boolean')
    if type(verify_build_only) is not bool:
        raise ValueError('verify_build_only must be boolean')
    if preflight_only and verify_build_only:
        raise ValueError('Choose one ROM-free preflight mode')
    # A ROM-free build check must work before any owned ROM or private
    # capture workspace exists. Preserve the old four-path form, with its
    # full isolation check, for callers that still supply both paths.
    if verify_build_only and rom_dir is None and workspace is None:
        binary, tree = preflight_mame_build(mame, mame_source_tree)
    else:
        if rom_dir is None or workspace is None:
            raise ValueError('Game capture requires both private ROM and workspace paths')
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

    # The more demanding ROM-free mode checks -listxml and both build
    # artifacts, without creating output directories or starting dino.
    # It intentionally does not report private source paths or ELF hashes.
    if verify_build_only:
        _require_session_aware_build(binary, tree)
        return {
            'status': 'ROM_FREE_SESSION_AWARE_MAME_BUILD_VERIFIED',
            'game_executed': False,
            'capture_verified': False,
            'linked_probe_runtime_verified': False,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        }

    # Real upstream driver and instrumented ELF identity. This only runs
    # -listxml, not any arcade game, and never loads ROM bytes.
    _require_session_aware_build(binary, tree)

    # The sole launcher-issued random label is passed to both Lua and C++
    # as process environment, never printed, logged or saved as a nonce.
    session_id = secrets.token_hex(16)
    launch_env = os.environ.copy()
    launch_env['CPS1_DINO_CAPTURE_SESSION'] = session_id
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
                stdin=None, env=launch_env,
                timeout=timeout_seconds, check=False,
            )
    except subprocess.TimeoutExpired as exc:
        raise ValueError('Local MAME session timed out; private files retained') from exc
    except OSError as exc:
        raise ValueError('Unable to execute local MAME; private files retained') from exc
    if proc.returncode != 0:
        raise ValueError('Local MAME exited unsuccessfully; check private log locally')

    # First require the complete local 54-file Lua/C++ capture set.
    # This stays entirely in process memory and stores no original-game
    # SHA-256 digests in any eventual public or private report.
    snapshot = private_capture_file_snapshot(
        capture_dir, FIRST_FRAME, FRAME_COUNT, FRAME_STEP)

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
        result['capture_session_binding'] = require_private_capture_session(
            capture_dir, session_id, FIRST_FRAME, FRAME_COUNT, FRAME_STEP)
        # A second, independent metadata recalculation must agree with the
        # nominal callback counts, interval annotations and RGB/OBJ fields.
        # This does not establish physical frame ordering or real gameplay.
        result['private_nominal_interval_consistency'] = (
            private_nominal_interval_consistency(
                result, intervals, FIRST_FRAME, FRAME_STEP, FRAME_COUNT))
        result['private_capture_source_stability'] = require_stable_private_capture(
            capture_dir, snapshot, FIRST_FRAME, FRAME_COUNT, FRAME_STEP)
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
        # Recheck after JSON formatting and fsync, as close as possible to
        # publishing. This is not a filesystem lock or proof of origin.
        require_stable_private_capture(
            capture_dir, snapshot, FIRST_FRAME, FRAME_COUNT, FRAME_STEP)
        # Unlike os.replace(), hard-link creation refuses a concurrent
        # existing target; the finalized report can never be clobbered.
        os.link(complete, report)

    return {
        'status': 'PRIVATE_CAPTURE_INTEGRITY_VERIFIED_ONLY',
        'reference_activity': activity,
        'multistream_interval_evidence': intervals,
        'capture_session_binding': result['capture_session_binding'],
        'private_nominal_interval_consistency': result['private_nominal_interval_consistency'],
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
    p.add_argument('--rom-dir', type=Path,
                   help='Required for game capture and filesystem-only preflight')
    p.add_argument('--workspace', type=Path,
                   help='Required for game capture and filesystem-only preflight')
    p.add_argument('--timeout-seconds', type=int, default=1800)
    preflight_options = p.add_mutually_exclusive_group()
    preflight_options.add_argument(
        '--preflight-only', action='store_true',
        help='Validate isolated paths only; no MAME process or ROM reading')
    preflight_options.add_argument(
        '--verify-build-only', action='store_true',
        help='Verify ROM-free driver/ELF with only --mame and --mame-tree')
    args = p.parse_args(argv)
    try:
        result = execute_private_capture(
            args.mame, args.mame_tree, args.rom_dir, args.workspace,
            timeout_seconds=args.timeout_seconds,
            preflight_only=args.preflight_only,
            verify_build_only=args.verify_build_only)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, TypeError, json.JSONDecodeError) as exc:
        # All raised messages are deliberately generic (no private file paths).
        print('Private MAME capture refused:', exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
