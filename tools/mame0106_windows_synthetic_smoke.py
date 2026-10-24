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
    # Bounded diagnostic markers exist ONLY in the disposable fake fixture.
    phases = (
        ("    $manifest = Get-Content", 'read_manifest'),
        ("    $relPaths = @(", 'file_hashes'),
        ("        $file = Join-Path $root $relative", 'member_path'),
        ("        if (-not [System.IO.File]::Exists($file))", 'check_file_exists'),
        ("        $fileInfo = Get-Item -LiteralPath $file", 'get_file_metadata'),
        ("        if (($fileInfo.Attributes -band", 'check_reparse_point'),
        ("        $entryProperty = $manifest.files.PSObject.Properties[$relative]", 'lookup_json_key'),
        ("        $expected = $entryProperty.Value", 'read_json_entry'),
        ("        $actualHash = Get-CapsuleSha256 -path $file", 'get_file_sha256'),
        ("        if ($fileInfo.Length -ne", 'compare_manifest_digest'),
        ("    $temp = Join-Path", 'private_scratch'),
        ("    $process = [System.Diagnostics.Process]::Start($info)", 'launch_fake_process'),
        ("    $stdout = $outTask.Result", 'read_fake_output'),
    )
    for token, phase in phases:
        if script.count(token) != 1:
            raise SyntheticSmokeError('unexpected_synthetic_phase_marker')
        script = script.replace(token, "    $stage367Phase = '" + phase + "'\n" + token, 1)
    original = "    Write-Output 'status=private_verification_refused'\n    exit 2"
    if script.count(original) != 1:
        raise SyntheticSmokeError('unexpected_synthetic_catch_handler')
    diagnostic = """    Write-Output 'status=private_verification_refused'
    $allowedReasons = @('bad_manifest', 'untrusted_component_pin',
        'missing_capsule_member', 'linked_capsule_member', 'missing_capsule_digest',
        'wrong_capsule_digest', 'staged_content_changed', 'native_timeout',
        'oversized_mame_output')
    $reason = [String]$_.Exception.Message
    if ($allowedReasons -ccontains $reason) {
        Write-Output ('synthetic_failure_class=' + $reason + '_at_' + $stage367Phase)
    } else {
        # All inputs here are synthetic. Emit only type tokens, never an
        # exception message, stack trace, raw path or child process output.
        $kind = [String]$_.Exception.GetType().Name
        if (-not [regex]::IsMatch($kind, '^[A-Za-z]{2,64}$')) {
            $kind = 'Other'
        }
        $member = 'unknown'
        if ($relative -ceq 'mame0106.exe') { $member = 'exe' }
        if ($relative -ceq 'roms/dino.zip') { $member = 'rom' }
        if ($relative -ceq 'verifyroms.ps1') { $member = 'script' }
        Write-Output ('synthetic_failure_class=unclassified_at_' + $stage367Phase + '_type_' + $kind + '_member_' + $member)
    }
    exit 2"""
    script = script.replace(original, diagnostic, 1)
    # Instrument ONLY synthetic negative gate, never production runner.
    original_bad = "    Write-Output 'status=native_verification_failed'\n    exit 2"
    synthetic_bad = """    Write-Output 'status=native_verification_failed'
    if ($env:STAGE367_SYNTHETIC_MODE -eq 'good') {
        $okExit = [int]($process.ExitCode -eq 0)
        $okFirst = [int]$hasRomset
        $okSecond = [int]$hasSummary
        $hasNegative = [int]$negative
        $exitValue = 'null'
        if ($null -ne $process.ExitCode) {
            $numExit = [int]$process.ExitCode
            if ($numExit -ge -100000 -and $numExit -le 100000) {
                $exitValue = [String]$numExit
            } else {
                $exitValue = 'outofrange'
            }
        }
        $kind = [String]$process.GetType().Name
        if (-not [regex]::IsMatch($kind, '^[A-Za-z]{2,64}$')) { $kind = 'Other' }
        $hasExited = [int]$process.HasExited
        $explicitCode = 'null'
        try {
            $boxedProcess = [System.Diagnostics.Process]$process
            $boxedProcess.Refresh()
            $value = $boxedProcess.ExitCode
            if ($null -ne $value) { $explicitCode = [String]$value }
        } catch {
            $explicitCode = 'exception'
        }
        $refCode = 'null'
        try {
            $property = [System.Diagnostics.Process].GetProperty('ExitCode')
            if ($null -ne $property) {
                $observed = $property.GetValue($process, $null)
                if ($null -ne $observed) { $refCode = [String]$observed }
            }
        } catch { $refCode = 'exception' }
        Write-Output ('synthetic_failure_class=runtime_gate_exit_' + $okExit + '_first_' + $okFirst + '_second_' + $okSecond + '_negative_' + $hasNegative + '_code_' + $exitValue + '_ptype_' + $kind + '_exited_' + $hasExited + '_explicit_' + $explicitCode + '_reflection_' + $refCode)
    }
    exit 2"""
    if script.count(original_bad) != 1:
        raise SyntheticSmokeError('unexpected_synthetic_result_gate')
    script = script.replace(original_bad, synthetic_bad, 1)
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
    if p.returncode != 0 and not p.stdout.strip():
        # Fixed classification only; never expose raw PowerShell stderr.
        diagnostic = p.stderr.decode('utf-8', errors='replace')
        category = ('ParserError' if 'ParserError' in diagnostic else
                    'UnexpectedToken' if 'UnexpectedToken' in diagnostic else
                    'MissingEndCurlyBrace' if 'MissingEndCurlyBrace' in diagnostic else
                    'powershell_no_status')
        raise SyntheticSmokeError('synthetic_powershell_' + category)
    # No path, raw child-process output, or private-data-like string is logged.
    return p.returncode, p.stdout.decode('utf-8', errors='replace').strip().splitlines()


def expect(script: Path, mode: str, code: int, status: str) -> None:
    ret, lines = invoke(script, mode)
    expected_lines = ([status, 'game=dino', 'recording_playback=not_executed']
                      if code == 0 else [status])
    # A second line is accepted only from a generated synthetic-only catch,
    # and it can contain ONLY predeclared class and phase labels.
    synthetic_diag = (len(lines) == 2 and
        lines[1].startswith('synthetic_failure_class=') and
        all(ch.isascii() and (ch.isalnum() or ch in '=_') for ch in lines[1]))
    if (ret == code == 2 and status == 'status=private_verification_refused' and
            lines[0] == status and synthetic_diag):
        return
    if ret != code or lines != expected_lines:
        allowed = {'status=public_runner_forbidden',
                   'status=synthetic_runner_branch_only',
                   'status=native_verification_failed',
                   'status=private_verification_refused'}
        actual_status = lines[0] if lines and lines[0] in allowed else 'unknown'
        # Only fixed status/phase/class; no raw child output or local paths.
        reason = '_' + lines[1] if synthetic_diag else ''
        raise SyntheticSmokeError(
            'synthetic_case_' + mode + '_rc_' + str(ret) +
            '_lines_' + str(len(lines)) + '_status_' + actual_status.replace('status=', '') + reason)


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
