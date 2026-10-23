"""Offline-only Windows MAME 0.106 ROM verification capsule builder.

The capsule DOES include owner-held game ROMs. Never attach it to a public
repository, GitHub Actions artifacts, issues, or any public cloud service.
Build and validation commands report no game bytes or private paths.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import zipfile

from tools.mame0106_private_verifyroms import (
    PINNED_ROM_SHA256, PINNED_XML_SHA256, EXE_SHA,
    offline_audit, verify_executable,
)

SCHEMA = 'mame0106-private-windows-capsule-v1'
MEMBERS = ('mame0106.exe', 'roms/dino.zip', 'verifyroms.ps1', 'capsule.json')
MAX_OUTPUT_BYTES = 55 * 1024 * 1024
MAX_EXE_BYTES = 130 * 1024 * 1024
MAX_ROM_BYTES = 8 * 1024 * 1024
SHA256 = re.compile(r'[a-f0-9]{64}\Z')
REPO_ROOT = Path(__file__).resolve().parents[1]


class CapsuleError(Exception):
    """Use fixed refusal classes: never inject private paths or content."""


def guard_private() -> None:
    if os.environ.get('GITHUB_ACTIONS', '').lower() == 'true':
        raise CapsuleError('public_runner_forbidden')


def hashfile(file: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with file.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
            size += len(part)
    return digest.hexdigest(), size


def require_private_file(file: Path, cap: int) -> None:
    if file.is_symlink() or not file.is_file() or not 0 < file.stat().st_size <= cap:
        raise CapsuleError('unsafe_private_input')
    resolved = file.resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise CapsuleError('source_inside_public_repo')


# Self-contained Windows PowerShell v5.1 runner (not yet run on Windows).
# No Python installation required. No raw emulator output or private paths are printed.
POWERSHELL = r'''# Owner-private, offline-only historical MAME 0.106 verification.
# This script has not itself been executed on a Windows host by the builder.
$ErrorActionPreference = 'Stop'
$schema = 'mame0106-private-windows-run-v1'
if ($env:GITHUB_ACTIONS -eq 'true') { Write-Output 'status=public_runner_forbidden'; exit 3 }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$temp = $null
try {
    $manifest = Get-Content -LiteralPath (Join-Path $root 'capsule.json') -Raw | ConvertFrom-Json
    if ($manifest.schema -ne 'mame0106-private-windows-capsule-v1' -or
        $manifest.execution_status -ne 'not_executed' -or
        $manifest.game -ne 'dino') { throw 'bad_manifest' }
    # This independent code pin prevents self-consistent but substituted
    # executable/ROM/manifest files from claiming historical MAME verification.
    # The private ZIP's SHA-256 must also be checked against the owner manifest
    # before extraction; this script is not a signature of its own contents.
    if ([String]$manifest.files.'mame0106.exe'.sha256 -cne
            'a3b0526056c2ecd10415a5757f0085aa6977992feddbb232ca60c7c446f81d44' -or
        [String]$manifest.files.'roms/dino.zip'.sha256 -cne
            '66fb8ad8e1f419b40bdfdaa250e86c865939178e7e732d49327854cb6ccdc8dd' -or
        [String]$manifest.historical_driver_xml_sha256 -cne
            'b6a89430b5e982ad533ea96faa53084506b4ca62f0f63ea6cdedd74324dda4c8') {
        throw 'untrusted_component_pin'
    }
    $relPaths = @('mame0106.exe', 'roms/dino.zip', 'verifyroms.ps1')
    foreach ($relative in $relPaths) {
        $file = Join-Path $root $relative
        if (-not [System.IO.File]::Exists($file)) { throw 'missing_capsule_member' }
        $fileInfo = Get-Item -LiteralPath $file
        if (($fileInfo.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'linked_capsule_member'
        }
        # JSON keys include 'roms/dino.zip': resolve by literal property name.
        $entryProperty = $manifest.files.PSObject.Properties[$relative]
        if ($null -eq $entryProperty) { throw 'missing_capsule_digest' }
        $expected = $entryProperty.Value
        $digestRecord = Get-FileHash -LiteralPath $file -Algorithm SHA256 -ErrorAction Stop
        if ($null -eq $digestRecord -or $null -eq $digestRecord.Hash) {
            throw 'missing_file_sha256'
        }
        $actualHash = ([String]$digestRecord.Hash).ToLowerInvariant()
        if ($fileInfo.Length -ne [Int64]$expected.size -or
            $actualHash -cne [String]$expected.sha256) { throw 'wrong_capsule_digest' }
    }
    $temp = Join-Path $env:TEMP ('mame0106-private-' + [Guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $temp)
    $roms = Join-Path $temp 'roms'
    [void](New-Item -ItemType Directory -Path $roms)
    $exe = Join-Path $temp 'mame0106.exe'
    Copy-Item -LiteralPath (Join-Path $root 'mame0106.exe') -Destination $exe
    $privateZip = Join-Path $roms 'dino.zip'
    Copy-Item -LiteralPath (Join-Path $root 'roms/dino.zip') -Destination $privateZip
    if ((Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant() -cne
            [String]$manifest.files.'mame0106.exe'.sha256 -or
        (Get-FileHash $privateZip -Algorithm SHA256).Hash.ToLowerInvariant() -cne
            [String]$manifest.files.'roms/dino.zip'.sha256) { throw 'staged_content_changed' }
    $out = Join-Path $temp 'mame-stdout.private.txt'
    $err = Join-Path $temp 'mame-stderr.private.txt'
    $argsMame = @('dino', '-verifyroms', '-rompath', ('"' + $roms + '"'), '-noreadconfig')
    $process = Start-Process -FilePath $exe -ArgumentList $argsMame -WorkingDirectory $temp `
        -NoNewWindow -PassThru -RedirectStandardOutput $out -RedirectStandardError $err
    if (-not $process.WaitForExit(90000)) {
        $process.Kill()
        $process.WaitForExit()
        throw 'native_timeout'
    }
    if ((Get-Item -LiteralPath $out).Length -gt 131072 -or
        (Get-Item -LiteralPath $err).Length -gt 131072) { throw 'oversized_mame_output' }
    $stdout = [System.IO.File]::ReadAllText($out)
    $hasRomset = [regex]::IsMatch($stdout, '(?im)^romset dino is good\s*$')
    $hasSummary = [regex]::IsMatch($stdout, '(?im)^1 romsets found, 1 were OK\.\s*$')
    $negative = [regex]::IsMatch($stdout, '(?i)is bad|not found|not supported')
    if ($process.ExitCode -eq 0 -and $hasRomset -and $hasSummary -and -not $negative) {
        Write-Output 'status=native_verified'
        Write-Output 'game=dino'
        Write-Output 'recording_playback=not_executed'
        exit 0
    }
    Write-Output 'status=native_verification_failed'
    exit 2
} catch {
    # No private error strings or local paths leave this owner-controlled session.
    Write-Output 'status=private_verification_refused'
    exit 2
} finally {
    if ($null -ne $temp -and [System.IO.Directory]::Exists($temp)) {
        Remove-Item -LiteralPath $temp -Recurse -Force -ErrorAction SilentlyContinue
    }
}
'''


def _entry(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o100600 << 16
    info.create_system = 3
    return info


def _write_file(z: zipfile.ZipFile, name: str, source: Path) -> None:
    with source.open('rb') as reader, z.open(_entry(name), 'w', force_zip64=True) as dest:
        shutil.copyfileobj(reader, dest, length=1024 * 1024)


def validate_capsule(archive: Path, *, archive_sha: str, rom_sha: str,
                     exe_sha: str, xml_sha: str) -> dict[str, object]:
    guard_private()
    require_private_file(archive, MAX_OUTPUT_BYTES)
    digest, size = hashfile(archive)
    if not SHA256.fullmatch(archive_sha) or digest != archive_sha:
        raise CapsuleError('capsule_archive_digest_mismatch')
    try:
        with zipfile.ZipFile(archive) as z:
            infos = z.infolist()
            if len(infos) != len(MEMBERS) or {x.filename for x in infos} != set(MEMBERS):
                raise CapsuleError('capsule_inventory_mismatch')
            if any(x.is_dir() or x.flag_bits & 1 or
                   stat.S_IFMT(x.external_attr >> 16) == stat.S_IFLNK for x in infos):
                raise CapsuleError('unsafe_capsule_member')
            manifest_raw = z.read('capsule.json')
            config = json.loads(manifest_raw.decode('utf-8'))
            if (config.get('schema') != SCHEMA or
                    config.get('execution_status') != 'not_executed' or
                    config.get('game') != 'dino' or
                    config.get('historical_driver_xml_sha256') != xml_sha or
                    set(config.get('files', {})) != set(MEMBERS) - {'capsule.json'}):
                raise CapsuleError('invalid_capsule_manifest')
            for name, expected_sha in (
                ('mame0106.exe', exe_sha), ('roms/dino.zip', rom_sha),
                ('verifyroms.ps1', hashlib.sha256(POWERSHELL.encode('utf-8')).hexdigest())
            ):
                info = z.getinfo(name)
                if info.file_size > (MAX_EXE_BYTES if name.endswith('.exe') else
                                     MAX_ROM_BYTES if name.endswith('.zip') else 100000):
                    raise CapsuleError('oversize_capsule_member')
                payload = z.read(name)
                record = config['files'][name]
                if (record['sha256'] != expected_sha or
                        record['size'] != len(payload) or
                        hashlib.sha256(payload).hexdigest() != expected_sha):
                    raise CapsuleError('capsule_member_digest_mismatch')
            if z.testzip() is not None:
                raise CapsuleError('capsule_crc_mismatch')
    except (zipfile.BadZipFile, OSError, UnicodeError, ValueError, TypeError, KeyError,
            RuntimeError) as exc:
        raise CapsuleError('invalid_capsule_zip') from exc
    return {'schema':SCHEMA, 'status':'offline_capsule_integrity_pass',
            'archive_bytes':size, 'member_count':len(MEMBERS),
            'native_mame_execution':'not_executed',
            'recording_playback':'not_executed'}


def build(exe: Path, rom: Path, xml: Path, output: Path, *,
          exe_sha: str = EXE_SHA, rom_sha: str = PINNED_ROM_SHA256,
          xml_sha: str = PINNED_XML_SHA256,
          audit=offline_audit, exe_check=verify_executable) -> dict[str, object]:
    guard_private()
    for path, max_bytes in ((exe,MAX_EXE_BYTES), (rom,MAX_ROM_BYTES), (xml,40*1024*1024)):
        require_private_file(path, max_bytes)
    for pin in (exe_sha, rom_sha, xml_sha):
        if not SHA256.fullmatch(pin):
            raise CapsuleError('invalid_input_hash_pin')
    if (output.exists() or output.is_symlink() or not output.parent.is_dir() or
            not (output.parent.resolve() != REPO_ROOT and
                 REPO_ROOT not in output.parent.resolve().parents)):
        raise CapsuleError('unsafe_output_location')
    pending = Path(str(output)+'.pending')
    if pending.exists() or pending.is_symlink():
        raise CapsuleError('pending_output_exists')
    if hashfile(exe)[0] != exe_sha or hashfile(rom)[0] != rom_sha or hashfile(xml)[0] != xml_sha:
        raise CapsuleError('input_sha_mismatch')
    try:
        exe_check(exe, exe_sha)
        audit(rom, xml, rom_sha=rom_sha, xml_sha=xml_sha)
    except Exception as exc:
        raise CapsuleError('offline_preflight_failed') from exc
    files = {
        'mame0106.exe':{'sha256':exe_sha, 'size':exe.stat().st_size},
        'roms/dino.zip':{'sha256':rom_sha, 'size':rom.stat().st_size},
        'verifyroms.ps1':{
            'sha256':hashlib.sha256(POWERSHELL.encode('utf-8')).hexdigest(),
            'size':len(POWERSHELL.encode('utf-8'))},
    }
    config = {'schema':SCHEMA, 'game':'dino',
              'execution_status':'not_executed',
              'recording_playback':'not_executed',
              'historical_driver_xml_sha256':xml_sha,
              'files':files}
    config_bytes=(json.dumps(config,sort_keys=True,indent=2)+'\n').encode('utf-8')
    # .pending is intentionally retained after an interrupted write; no
    # pre-existing backup or partially written archive is ever overwritten.
    with zipfile.ZipFile(pending, 'x', compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6, allowZip64=True) as z:
        _write_file(z, 'mame0106.exe', exe)
        _write_file(z, 'roms/dino.zip', rom)
        z.writestr(_entry('verifyroms.ps1'), POWERSHELL.encode('utf-8'),compress_type=zipfile.ZIP_DEFLATED)
        z.writestr(_entry('capsule.json'), config_bytes,compress_type=zipfile.ZIP_DEFLATED)
    capsule_sha, capsule_size=hashfile(pending)
    if capsule_size>MAX_OUTPUT_BYTES:
        raise CapsuleError('output_too_large')
    validate_capsule(pending,archive_sha=capsule_sha,rom_sha=rom_sha,
                     exe_sha=exe_sha,xml_sha=xml_sha)
    os.link(pending, output)
    pending.unlink()
    return {'schema':SCHEMA,'status':'offline_capsule_ready_not_executed',
            'archive_sha256':capsule_sha,'archive_bytes':capsule_size,
            'member_count':len(MEMBERS),
            'native_mame_execution':'not_executed','recording_playback':'not_executed'}


def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--driver-xml', type=Path,required=True)
    parser.add_argument('--out', type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        result=build(args.exe,args.rom,args.driver_xml,args.out)
        for key,value in result.items():print(f'{key}={value}')
        return 0
    except (CapsuleError, OSError):
        print('status=offline_capsule_refused')
        return 2

if __name__=='__main__':
    sys.exit(main())
