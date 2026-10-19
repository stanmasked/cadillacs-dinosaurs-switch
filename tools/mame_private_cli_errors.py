#!/usr/bin/env python3
"""Fixed-vocabulary private launcher failure summaries; never render exceptions.

A local filesystem error may contain a private directory, ROM filename or
session label. The CLI deliberately outputs *only* safe codes and static
guidance, not original exception text, tracebacks or input paths.
"""
import json


def public_failure_report(error):
    """Classify exceptions without reflecting any untrusted exception text."""
    # These are classification hints only. No message is ever emitted.
    message = str(error)
    if isinstance(error, (ValueError, TypeError)):
        if any(marker in message for marker in (
            'preflight mode', 'must be boolean', 'requires both',
            'Session timeout must be', 'Invalid private triage frame count',
        )):
            code = 'INVALID_LAUNCH_ARGUMENTS'
            action = 'Recheck CLI flags, private path options and timeout bounds.'
        elif any(marker in message for marker in (
            'Instrumented MAME executable', 'MAME executable may not',
            'Full upstream MAME source', 'MAME executable must stay',
            'MAME identity/session-aware',
        )):
            code = 'MAME_BUILD_OR_IDENTITY_UNVERIFIED'
            action = 'Recheck the local MAME 0.289 build and ROM-free verification.'
        elif any(marker in message for marker in (
            'Private ROM directory', 'outside the project', 'ROM and full MAME',
            'private ROM', 'No private dino', 'Private dino',
            'Private unpacked dino',
        )):
            code = 'PRIVATE_ROM_LAYOUT_INVALID'
            action = 'Check the locally owned dino set and separated ROM directory.'
        elif any(marker in message for marker in (
            'Private workspace', 'Capture workspace', 'Capture workspace already',
        )):
            code = 'PRIVATE_WORKSPACE_INVALID'
            action = 'Use a new empty isolated private workspace with 0700 permissions.'
        elif any(marker in message for marker in (
            'Private MAME ROM verification',
        )):
            code = 'PRIVATE_MAME_ROMSET_AUDIT_FAILED'
            action = 'Review the private MAME ROM verification log locally.'
        elif any(marker in message for marker in (
            'Local MAME session timed out', 'Local MAME exited unsuccessfully',
            'Unable to execute local MAME',
        )):
            code = 'LOCAL_MAME_PROCESS_FAILED'
            action = 'Inspect the private MAME log locally; do not upload game files.'
        elif any(marker in message for marker in (
            'capture', 'Capture', 'frame', 'Frame', 'RGB', 'OBJ',
            'latch', 'sidecar', 'diagnostic', 'alignment', 'interval',
            'fingerprint', 'snapshot',
        )):
            code = 'PRIVATE_CAPTURE_AUDIT_REFUSED'
            action = 'Inspect the local private capture and diagnostic log.'
        else:
            code = 'PRIVATE_LAUNCH_REJECTED'
            action = 'Inspect the private workspace locally and retry with valid inputs.'
    elif isinstance(error, OSError):
        code = 'PRIVATE_FILESYSTEM_ERROR'
        action = 'Inspect local file permissions, space and existing output files.'
    else:
        code = 'UNEXPECTED_PRIVATE_LAUNCH_FAILURE'
        action = 'Inspect the local environment; do not publish private tracebacks.'
    return {
        'status': 'PRIVATE_MAME_CAPTURE_REFUSED',
        'reason_code': code,
        'next_local_action': action,
        'private_paths_disclosed': False,
        'gameplay_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }


def write_private_failure(error, destination):
    """Write only known-safe JSON to stderr; no dynamic content copied."""
    destination.write(json.dumps(public_failure_report(error)) + '\n')
