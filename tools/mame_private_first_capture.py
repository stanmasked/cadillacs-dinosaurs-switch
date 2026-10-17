#!/usr/bin/env python3
"""One-command first dino private capture: ROM-free check, explicit game --run.

Run only with privately held ROM assets and instrumented MAME 0.289.
All results use fixed metadata fields: no original paths, hashes or
capture bytes are echoed or sent to GitHub.
"""
import argparse
import contextlib
import io
import json
from pathlib import Path
import sys

try:
    from tools.mame_private_dino_session import execute_private_capture
    from tools.mame_private_capture_failure_summary import safe_capture_failure_report
    from tools.mame_private_auto_exit_evidence import private_mame_auto_exit_log_observation
    from tools.mame_private_auto_exit_reconciliation import reconcile_auto_exit_with_capture
except ModuleNotFoundError:
    from mame_private_dino_session import execute_private_capture
    from mame_private_capture_failure_summary import safe_capture_failure_report
    from mame_private_auto_exit_evidence import private_mame_auto_exit_log_observation
    from mame_private_auto_exit_reconciliation import reconcile_auto_exit_with_capture


SAFE_MARKERS = frozenset({
    'LOCAL_LUA_REPORTED_SIZE_READY_EXIT',
    'LOCAL_LUA_REPORTED_GRACE_LIMIT_EXIT',
    'LOCAL_MAME_AUTO_EXIT_LOG_REFUSED',
    'LOCAL_MAME_AUTO_EXIT_MARKER_NOT_OBSERVED',
    'LOCAL_MAME_AUTO_EXIT_MARKERS_AMBIGUOUS',
})
SAFE_RECONCILIATIONS = frozenset({
    'READY_MESSAGE_AGREES_WITH_SIZE_ONLY_FILES',
    'READY_MESSAGE_CONTRADICTS_POST_RUN_FILES',
    'GRACE_MESSAGE_AGREES_WITH_INCOMPLETE_FILES',
    'GRACE_MESSAGE_CONTRADICTS_POST_RUN_FILES',
    'AUTO_EXIT_RECONCILIATION_UNAVAILABLE',
    'AUTO_EXIT_MARKER_NOT_USABLE',
    'AUTO_EXIT_PROGRESS_NOT_USABLE',
})
SAFE_PROGRESS = frozenset({
    'NO_PRIVATE_CAPTURE_DIRECTORY',
    'NO_EXPECTED_PRIVATE_CAPTURE_FILES',
    'INCOMPLETE_PRIVATE_CAPTURE_FILE_SET',
    'INVALID_PRIVATE_CAPTURE_FILE_SIZES',
    'UNEXPECTED_PRIVATE_CAPTURE_ENTRIES',
    'COMPLETE_FILE_SET_UNVERIFIED',
    'PRIVATE_CAPTURE_PROGRESS_REFUSED',
})


def _fixed_status(item, allowed, fallback):
    if not isinstance(item, dict):
        return fallback
    candidate = item.get('status')
    return candidate if type(candidate) is str and candidate in allowed else fallback


def _base(status):
    return {
        'schema': 'PRIVATE_DINO_FIRST_CAPTURE_HANDOFF_V1',
        'status': status,
        'diagnostic_only': True,
        'original_game_authenticity_verified': False,
        'active_gameplay_verified': False,
        'physical_vblank_verified': False,
        'obj_latch_age_verified': False,
        'switch_gameplay_verified': False,
        'pixel_parity_eligible': False,
        'original_game_files_or_paths_in_report': False,
        'safe_to_share_this_summary_only': True,
    }


def _successful_capture(result):
    if (type(result) is not dict or
            result.get('status') != 'PRIVATE_CAPTURE_INTEGRITY_VERIFIED_ONLY' or
            result.get('game_executed') is not True or
            result.get('nominal_frame_count') != 6 or
            result.get('crc32_lua_components_checked') != 30 or
            result.get('bound_cpp_obj_samples') != 6 or
            result.get('local_mame_verifyroms_exit_zero_before_capture') is not True or
            result.get('private_rom_content_sha256_stable_during_capture') is not True or
            result.get('auto_exit_after_capture_requested') is not True or
            result.get('frame_sync_verified') is not False or
            result.get('pixel_parity_eligible') is not False):
        raise ValueError('Private first capture result lacks strict structural evidence')
    out = _base('PRIVATE_SIX_FRAME_STRUCTURAL_AUDIT_PASSED')
    out.update({
        'local_original_rom_read_during_explicit_run': True,
        'local_mame_rom_audit_exited_zero': True,
        'verified_file_count': 54,
        'nominal_frame_count': 6,
        'lua_crc32_blobs_checked': 30,
        'cpp_obj_fnv_samples_checked': 6,
        'local_original_rom_sha256_stable': True,
        'game_emulator_process_completed': True,
        'auto_exit_marker_status': _fixed_status(
            result.get('auto_exit_log_observation'), SAFE_MARKERS,
            'LOCAL_MAME_AUTO_EXIT_MARKER_NOT_OBSERVED'),
        'auto_exit_post_run_reconciliation_status': _fixed_status(
            result.get('auto_exit_post_run_reconciliation'), SAFE_RECONCILIATIONS,
            'AUTO_EXIT_RECONCILIATION_UNAVAILABLE'),
    })
    return out


def private_first_capture_handoff(mame, tree, roms, workspace, *,
                                  run=False, timeout_seconds=1800):
    """Only --run may read private original game bytes and launch emulation."""
    if type(run) is not bool:
        raise ValueError('Private first capture run flag must be boolean')
    with contextlib.redirect_stdout(io.StringIO()), \
         contextlib.redirect_stderr(io.StringIO()):
        if not run:
            result = execute_private_capture(
                mame, tree, roms, workspace, timeout_seconds=timeout_seconds,
                check_launch_readiness=True)
            if (type(result) is not dict or
                    result.get('status') != 'PRIVATE_DINO_LAUNCH_PREFLIGHT_ONLY' or
                    result.get('compiled_session_probe_elf_checked') is not True or
                    result.get('private_rom_entry_observed') is not True or
                    result.get('rom_file_bytes_read') is not False or
                    result.get('game_executed') is not False):
                raise ValueError('Private launch readiness result was not verified')
            out = _base('PRIVATE_DINO_FIRST_CAPTURE_READINESS_METADATA_ONLY')
            out.update({
                'mame_instrumented_build_checked': True,
                'private_game_entry_observed': True,
                'original_rom_bytes_read': False,
                'game_executed': False,
                'requires_explicit_run_for_original_game': True,
            })
            return out
        result = execute_private_capture(
            mame, tree, roms, workspace, timeout_seconds=timeout_seconds,
            verify_private_romset_before_capture=True,
            auto_exit_after_capture=True)
        return _successful_capture(result)


def _safe_failure(exc, workspace, attempted_run):
    with contextlib.redirect_stdout(io.StringIO()), \
         contextlib.redirect_stderr(io.StringIO()):
        failure = safe_capture_failure_report(
            exc, workspace, include_progress=attempted_run)
        out = _base('PRIVATE_DINO_FIRST_CAPTURE_REFUSED')
        out['reason_code'] = failure['reason_code']
        out['original_rom_may_have_been_read_locally'] = attempted_run
        if attempted_run:
            progress = failure.get('capture_progress') or {}
            out['capture_progress_status'] = _fixed_status(
                progress, SAFE_PROGRESS, 'PRIVATE_CAPTURE_PROGRESS_REFUSED')
            for key in ('present_files', 'missing_files', 'invalid_size_files'):
                value = progress.get(key)
                if type(value) is int and 0 <= value <= 54:
                    out[key] = value
            marker = private_mame_auto_exit_log_observation(workspace)
            out['auto_exit_marker_status'] = _fixed_status(
                marker, SAFE_MARKERS, 'LOCAL_MAME_AUTO_EXIT_LOG_REFUSED')
            out['auto_exit_post_run_reconciliation_status'] = _fixed_status(
                reconcile_auto_exit_with_capture(
                    marker, failure_progress=progress),
                SAFE_RECONCILIATIONS, 'AUTO_EXIT_RECONCILIATION_UNAVAILABLE')
        return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mame', type=Path, required=True)
    parser.add_argument('--mame-tree', type=Path, required=True)
    parser.add_argument('--rom-dir', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--run', action='store_true',
                        help='Explicitly verify privately held ROM and run original dino locally')
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    args = parser.parse_args(argv)
    try:
        out = private_first_capture_handoff(
            args.mame, args.mame_tree, args.rom_dir, args.workspace,
            run=args.run, timeout_seconds=args.timeout_seconds)
    except Exception as exc:
        try:
            out = _safe_failure(exc, args.workspace, args.run)
        except Exception:
            out = _base('PRIVATE_DINO_FIRST_CAPTURE_REFUSED')
            out['reason_code'] = 'UNEXPECTED_PRIVATE_LAUNCH_FAILURE'
        print(json.dumps(out, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
