#!/usr/bin/env python3
"""Audit the pinned historical public MAME 0.106 source against the private
Windows -verifyroms *protocol* without running or exposing any game ROM.

This is static source evidence, NOT an executed MAME ROM verification. On a
public runner only the synthetic tests are permitted; the private source ZIP
and owners' manifest are processed in an isolated owner session.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import zipfile

from tools.mame0106_private_windows_capsule import POWERSHELL

SOURCE_ZIP_SHA256 = 'ec0811d8f3e651d1004909127416886e1a0ac7609094c14eea1de0b9d7383f94'
SOURCES = {
    'mame0106/src/windows/fronthlp.c': '2f43c5b2a2fe53aa0aa5bcf439b2c2300c236fb1587b1520cb5a35dbdcc6a408',
    'mame0106/src/windows/config.c': '9dd65af9daaf387491a8fdda3876d19df70e83c7e8713b4ff18be38b765afbd8',
    'mame0106/src/windows/fileio.c': '8e023489ba51683b5818af4eb013bef39db582ba5845dbeafd0042561ad92284',
}
MAX_BYTES = 20 * 1024 * 1024


class ProtocolRefused(Exception):
    """Fixed error reason, never leaks original file paths or source data."""


def private_guard() -> None:
    if os.environ.get('GITHUB_ACTIONS', '').lower() == 'true':
        raise ProtocolRefused('public_runner_forbidden')


def verify_contract(front: str, config: str, fileio: str,
                    script: str = POWERSHELL) -> dict[str, object]:
    """Source-level contract only, strict enough to catch accidental drift."""
    required = {
        'verifyroms_option': bool(re.search(r'\{\s*"verifyroms"\s*,\s*NULL\s*,\s*rc_set_int\s*,\s*&verify', front)),
        'verifyroms_mode': bool(re.search(r'&verify\s*,\s*NULL\s*,\s*VERIFY_ROMS', front)),
        'driver_filter': 'strwildcmp(gamename, drivers[i]->name)' in front,
        'individual_result_prefix': 'printf ("romset %s ", drivers[i]->name);' in front,
        'correct_output': bool(re.search(r'else if\s*\(res\s*==\s*CORRECT\)\s*\{\s*printf\s*\("is good\\n"\)\s*;\s*correct\+\+', front)),
        'summary_output': bool(re.search(r'printf\s*\("%d %s found, %d were OK\.\\n"\s*,\s*correct\s*\+\s*incorrect\s*,', front)),
        'zero_when_no_incorrect': bool(re.search(r'if\s*\(incorrect\s*>\s*0\)\s*return\s+2\s*;\s*else\s*return\s+0\s*;', front)),
        'missing_noset_nonzero': bool(re.search(r'if\s*\(correct\s*\+\s*incorrect\s*==\s*0\)\s*\{[\s\S]{0,500}?return\s+1\s*;', front)),
        'rompath_option': bool(re.search(r'\{\s*"rompath"\s*,\s*"rp"\s*,\s*rc_string', fileio)),
        'readconfig_option': bool(re.search(r'\{\s*"readconfig"\s*,\s*"rc"\s*,\s*rc_bool', config)),
        'stdout_results': 'printf ("is good\\n")' in front and 'fprintf(stderr,"%d%%\\r"' in front,
        'script_calls_verifyroms': "dino -verifyroms -rompath" in script and '-noreadconfig' in script,
        'script_requires_exit_zero': bool(re.search(r'\$process\.ExitCode\s+-eq\s+0', script)),
        'script_requires_good_line': "^romset dino is good" in script,
        'script_requires_summary': "^1 romsets found, 1 were OK" in script,
        'script_rejects_negative': 'and -not $negative' in script,
        'script_rejects_public_ci': "if ($env:GITHUB_ACTIONS -eq 'true')" in script,
        'script_explicit_not_replay': 'recording_playback=not_executed' in script,
    }
    missing = [name for name, passed in required.items() if not passed]
    return {
        'schema': 'cadillacs-stage370-pinned-mame0106-source-protocol-v1',
        'status': 'source_contract_pass_no_runtime_execution' if not missing else 'source_contract_mismatch',
        'checks_total': len(required),
        'checks_passed': len(required) - len(missing),
        'missing_checks': missing,
        'historic_mame_verifyroms_executed': False,
        'original_wolfmame_replay_executed': False,
        'private_original_rom_accessed': False,
    }


def audit_zip(path: Path, *, expected_zip_sha: str = SOURCE_ZIP_SHA256) -> dict[str, object]:
    private_guard()
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ProtocolRefused('unsafe_source_zip')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_zip_sha:
        raise ProtocolRefused('source_zip_sha256_mismatch')
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if len(names) != len(set(names)) or any(x not in names for x in SOURCES):
                raise ProtocolRefused('source_members_missing_or_duplicated')
            content: dict[str, str] = {}
            for name, expected in SOURCES.items():
                info = z.getinfo(name)
                if info.file_size > 100000 or info.is_dir() or (stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK):
                    raise ProtocolRefused('invalid_historic_source_member')
                raw = z.read(name)
                if hashlib.sha256(raw).hexdigest() != expected:
                    raise ProtocolRefused('historical_source_member_sha256_mismatch')
                content[name] = raw.decode('latin1')
            if z.testzip() is not None:
                raise ProtocolRefused('source_zip_crc_mismatch')
    except (zipfile.BadZipFile, OSError, UnicodeError, ValueError, RuntimeError) as exc:
        raise ProtocolRefused('invalid_source_zip') from exc
    report = verify_contract(content['mame0106/src/windows/fronthlp.c'],
                             content['mame0106/src/windows/config.c'],
                             content['mame0106/src/windows/fileio.c'])
    report['pinned_historic_source_zip_sha256_verified'] = True
    report['pinned_historic_source_member_count'] = len(SOURCES)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-zip', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit_zip(args.source_zip)
    except (ProtocolRefused, OSError):
        report = {'schema': 'cadillacs-stage370-pinned-mame0106-source-protocol-v1',
                  'status': 'source_audit_refused',
                  'historic_mame_verifyroms_executed': False,
                  'original_wolfmame_replay_executed': False}
    print(json.dumps(report, sort_keys=True))
    return 0 if report['status'] == 'source_contract_pass_no_runtime_execution' else 2


if __name__ == '__main__':
    raise SystemExit(main())
