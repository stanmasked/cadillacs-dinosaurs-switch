"""ROM-free Windows probe of the source-pinned historical MAME 0.106 binary."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

EXE_SHA = "a3b0526056c2ecd10415a5757f0085aa6977992feddbb232ca60c7c446f81d44"
SOURCE_PIN = "source_commit=0a83d596c83b4d1a72cb3a7b1d2835b809206f2f"
FILES = frozenset((
    "mame0106.exe", "mame0106-source.zip", "mame0106-build-compat.patch",
    "mame0106-windowed-mng-capture.patch",
    "mame0106-inprocess-count-trace-combined.patch", "dino-driver.xml",
    "mame0106-help.txt", "mame0106-showconfig.txt",
))
REQUIRED = (b"playback", b"frames_to_run", b"mngwrite", b"mngstartframe",
            b"mngframes", b"mngcounttrace", b"throttle")


class ProbeError(Exception):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for piece in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(piece)
    return digest.hexdigest()


def verify_bundle(root: Path, expected_exe_sha: str = EXE_SHA) -> int:
    """Verify public technical provenance with no original game files."""
    manifest_path, pin_path = root / "SHA256SUMS.txt", root / "source-pin.txt"
    if any(not p.is_file() or p.is_symlink() for p in (manifest_path, pin_path)):
        raise ProbeError("manifest_missing")
    manifest = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64}) [ *]([A-Za-z0-9_.-]+)", line)
        if not match:
            raise ProbeError("manifest_format")
        digest, name = match.groups()
        if name in manifest or name not in FILES:
            raise ProbeError("manifest_inventory")
        manifest[name] = digest.lower()
    if set(manifest) != FILES or manifest["mame0106.exe"] != expected_exe_sha:
        raise ProbeError("manifest_pin")
    if SOURCE_PIN not in pin_path.read_text(encoding="utf-8").splitlines():
        raise ProbeError("upstream_pin")
    for name, expected in manifest.items():
        file = root / name
        if not file.is_file() or file.is_symlink() or sha256_file(file) != expected:
            raise ProbeError("digest_mismatch")
    exe = (root / "mame0106.exe").read_bytes()
    if len(exe) < 0x40 or exe[:2] != b"MZ":
        raise ProbeError("dos_header")
    offset = struct.unpack_from("<I", exe, 0x3C)[0]
    if offset + 6 > len(exe) or exe[offset:offset + 6] != b"PE\x00\x00\x4c\x01":
        raise ProbeError("pe32_i386_header")
    return len(manifest)


def contains(path: Path, marker: bytes) -> bool:
    tail = b""
    with path.open("rb") as inp:
        for chunk in iter(lambda: inp.read(65536), b""):
            part = tail + chunk
            if marker in part:
                return True
            tail = part[-(len(marker) - 1):]
    return False


def run_probe(exe: Path, root: Path, opt: str, stdout: Path, stderr: Path, seconds: int) -> int:
    try:
        with stdout.open("wb") as out, stderr.open("wb") as err:
            proc = subprocess.run((str(exe), opt), cwd=root, stdin=subprocess.DEVNULL,
                                  stdout=out, stderr=err, timeout=seconds, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ProbeError("command_start_or_timeout") from exc
    if proc.returncode != 0:
        raise ProbeError("command_exit")
    size = stdout.stat().st_size
    if size <= 0 or size > 128 * 1024 * 1024:
        raise ProbeError("command_output_size")
    return size


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    report = ["schema=mame0106-native-windows-romfree-v1", "private_data_used=no"]
    phase = "verify_bundle"
    code = 1
    try:
        root = args.artifact_dir.resolve(strict=True)
        report.append(f"technical_hashes_verified={verify_bundle(root)}")
        exe = root / "mame0106.exe"
        with tempfile.TemporaryDirectory(prefix="mame0106-native-romfree-") as temp:
            scratch = Path(temp)
            phase = "help"
            path = scratch / "help.out"
            size = run_probe(exe, root, "-help", path, scratch / "help.err", 45)
            if not contains(path, b"M.A.M.E. v0.106"):
                raise ProbeError("help_signature")
            report.extend(("help=pass", f"help_bytes={size}"))
            phase = "showconfig"
            path = scratch / "config.out"
            size = run_probe(exe, root, "-showconfig", path, scratch / "config.err", 45)
            conf = path.read_bytes().lower()
            if any(option not in conf for option in REQUIRED):
                raise ProbeError("required_options")
            report.extend(("showconfig=pass", f"showconfig_bytes={size}"))
            phase = "listxml"
            path = scratch / "listxml.out"
            size = run_probe(exe, root, "-listxml", path, scratch / "listxml.err", 90)
            if not contains(path, b'<?xml') or not contains(path, b'<game name="dino"'):
                raise ProbeError("dino_driver")
            report.extend(("listxml=pass", "dino_driver_present=yes", f"listxml_bytes={size}"))
        code = 0
        report.append("result=pass")
    except (ProbeError, OSError, ValueError, UnicodeError) as exc:
        report.extend(("result=fail", f"failure_phase={phase}", f"failure_type={type(exc).__name__}"))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    return code


if __name__ == "__main__":
    sys.exit(main())
