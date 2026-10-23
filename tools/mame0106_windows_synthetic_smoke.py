"""Windows-only synthetic smoke for the historical-MAME private PS runner.

Runs on public Windows Actions using ONLY a locally compiled fake C# binary
and a text fixture pretending to be a zip. No ROM, input, historical MAME EXE,
private capture, or original game hash enters the runner.

A TEMPORARY synthetic-copy of the runner replaces three production SHA pins,
the Actions guard, and the success label. The production runner remains guarded
and untouched. This is PowerShell behavior coverage, NOT a real -verifyroms.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from tools.mame0106_private_verifyroms import EXE_SHA, PINNED_ROM_SHA256, PINNED_XML_SHA256
from tools.mame0106_private_windows_capsule import POWERSHELL, SCHEMA

GUARD = "if ($env:GITHUB_ACTIONS -eq 'true') { Write-Output 'status=public_runner_forbidden'; exit 3 }"
PRODUCTION_SUCCESS = "Write-Output 'status=native_verified'"
SYNTHETIC_SUCCESS = "Write-Output 'status=synthetic_runner_branch_only'"
FAKE_ROM = b'STAGE367 SYNTHETIC TEXT DATA, DEFINITELY NOT GAME ROM\n' * 3
SOURCE = r'''using System;
class Stage367SyntheticOnly {
    static int Main(string[] args) {
        string mode = Environment.GetEnvironmentVariable("STAGE367_SYNTHETIC_MODE") ?? "good";
        if (mode == "silent") return 0;
        if (mode == "stderr_only") {
            Console.Error.WriteLine("romset dino is good");
            Console.Error.WriteLine("1 romsets found, 1 were OK.");
            return 0;
        }
        Console.WriteLine("romset dino is good");
        if (mode != "missing_summary") Console.WriteLine("1 romsets found, 1 were OK.");
        if (mode == "bad_marker") Console.WriteLine("romset synthetic is bad");
        if (mode == "not_found") Console.WriteLine("synthetic fixture not found");
        if (mode == "oversized") Console.WriteLine(new String('X', 180000));
        return mode == "nonzero" ? 2 : 0;
    }
}'''


class SyntheticSmokeError(Exception):
    """Public-safe fixed identifier, never contains runtime paths or output."""


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def synthetic_copy(binary_sha: str, rom_sha: str, xml_sha: str) -> str:
    """Change exact known strings only in disposable fixture's PS script."""
    script = POWERSHELL
    replacements = (
        (GUARD, "# STAGE367 synthetic fixture ONLY: GITHUB_ACTIONS guard tested separately"),
        (EXE_SHA, binary_sha),
        (PINNED_ROM_SHA256, rom_sha),
        (PINNED_XML_SHA256, xml_sha),
        (PRODUCTION_SUCCESS, SYNTHETIC_SUCCESS),
    )
    for old, new in replacements:
        if script.count(old) != 1:
            raise SyntheticSmokeError('unexpected_production_script_structure')
        script = script.replace(old, new, 1)
    if (GUARD in script or PRODUCTION_SUCCESS in script or
            any(x in script for x in (EXE_SHA, PINNED_ROM_SHA256, PINNED_XML_SHA256))):
        raise SyntheticSmokeError('incomplete_synthetic_isolation')
    return script


def csc_path() -> Path:
    root = Path(os.environ.get('WINDIR', r'C:\Windows'))
    return root / 'Microsoft.NET' / 'Framework' / 'v4.0.30319' / 'csc.exe'


def invoke(script: Path, mode: str = 'good') -> tuple[int, list[str]]:
    env = os.environ.copy()
    env['STAGE367_SYNTHETIC_MODE'] = mode
    try:
        p = subprocess.run(
            ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
             '-ExecutionPolicy', 'Bypass', '-File', str(script)],
            cwd=script.parent, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=105, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SyntheticSmokeError('synthetic_powershell_launch_failed') from exc
    if len(p.stdout) > 32768 or len(p.stderr) > 32768:
        raise SyntheticSmokeError('synthetic_runner_output_overflow')
    # No path, raw child-process output, or private-data-like string is logged.
    return p.returncode, p.stdout.decode('utf-8', errors='replace').strip().splitlines()


def expect(script: Path, mode: str, code: int, status: str) -> None:
    ret, lines = invoke(script, mode)
    expected_lines = ([status, 'game=dino', 'recording_playback=not_executed']
                      if code == 0 else [status])
    if ret != code or lines != expected_lines:
        # Only internal fixed labels/counts; NEVER print raw PowerShell output.
        allowed = {'status=public_runner_forbidden',
                   'status=synthetic_runner_branch_only',
                   'status=native_verification_failed',
                   'status=private_verification_refused'}
        actual_status = lines[0] if lines and lines[0] in allowed else 'unknown'
        raise SyntheticSmokeError(
            'synthetic_case_' + mode + '_rc_' + str(ret) +
            '_lines_' + str(len(lines)) + '_status_' + actual_status.replace('status=', ''))


def run() -> dict[str, object]:
    if sys.platform != 'win32' or os.getenv('GITHUB_ACTIONS', '').lower() != 'true':
        raise SyntheticSmokeError('requires_public_windows_synthetic_runner')
    with tempfile.TemporaryDirectory(prefix='stage367-synthetic-mame-') as tmp:
        root = Path(tmp)
        production = root / 'production_guard_only'
        production.mkdir()
        unmodified = production / 'verifyroms.ps1'
        unmodified.write_text(POWERSHELL, encoding='utf-8', newline='\n')
        expect(unmodified, 'good', 3, 'status=public_runner_forbidden')

        testroot = root / 'synthetic_fixture_only'
        testroot.mkdir()
        (testroot / 'roms').mkdir()
        source = testroot / 'synthetic_stub.cs'
        source.write_text(SOURCE, encoding='utf-8')
        exe = testroot / 'mame0106.exe'
        csc = csc_path()
        if not csc.is_file():
            raise SyntheticSmokeError('csharp_compiler_unavailable')
        try:
            build = subprocess.run(
                [str(csc), '/nologo', '/target:exe', '/out:' + str(exe), str(source)],
                cwd=testroot, capture_output=True, timeout=75, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SyntheticSmokeError('synthetic_stub_build_failed') from exc
        if build.returncode != 0 or not exe.is_file():
            raise SyntheticSmokeError('synthetic_stub_build_failed')
        rom = testroot / 'roms' / 'dino.zip'
        rom.write_bytes(FAKE_ROM)
        exe_sha, rom_sha = sha(exe.read_bytes()), sha(FAKE_ROM)
        xml_sha = sha(b'STAGE367 synthetic no XML or real driver involved')
        ps = testroot / 'verifyroms.ps1'
        ps.write_text(synthetic_copy(exe_sha, rom_sha, xml_sha), encoding='utf-8', newline='\n')
        files = {}
        for relpath in ('mame0106.exe', 'roms/dino.zip', 'verifyroms.ps1'):
            value = (testroot / relpath).read_bytes()
            files[relpath] = {'size': len(value), 'sha256': sha(value)}
        manifest = {
            'schema': SCHEMA, 'game': 'dino',
            'execution_status': 'not_executed',
            'recording_playback': 'not_executed',
            'historical_driver_xml_sha256': xml_sha,
            'files': files,
        }
        manifest_path = testroot / 'capsule.json'
        manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding='utf-8')
        expect(ps, 'good', 0, 'status=synthetic_runner_branch_only')
        for mode in ('missing_summary','bad_marker','not_found','nonzero','silent','stderr_only'):
            expect(ps, mode, 2, 'status=native_verification_failed')
        expect(ps, 'oversized', 2, 'status=private_verification_refused')
        rom.write_bytes(FAKE_ROM + b'synthetic mutation')
        expect(ps, 'good', 2, 'status=private_verification_refused')
        rom.write_bytes(FAKE_ROM)
        forged = json.loads(manifest_path.read_text(encoding='utf-8'))
        forged['files']['mame0106.exe']['sha256'] = '0' * 64
        manifest_path.write_text(json.dumps(forged), encoding='utf-8')
        expect(ps, 'good', 2, 'status=private_verification_refused')
    return {
        'schema': 'stage367-windows-powershell-synthetic-only-v1',
        'status': 'synthetic_windows_powershell_branch_tests_passed',
        'synthetic_cases': 11,
        'real_rom_content_used': False,
        'real_mame_binary_executed': False,
        'historical_mame_verifyroms_verified': False,
        'recording_playback_verified': False,
    }


def main() -> int:
    try:
        print(json.dumps(run(), sort_keys=True))
        return 0
    except SyntheticSmokeError as exc:
        print('status=synthetic_windows_powershell_smoke_failed')
        print('failure_class=' + str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
