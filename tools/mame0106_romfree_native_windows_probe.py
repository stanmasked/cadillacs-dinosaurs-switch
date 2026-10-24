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


# Independent owner-verified SHA-256 pins from immutable ROM-free artifact
# 12461451785 (run 39859311511), ZIP SHA256:
# 5a495bdcbe832dbe1261fc935ef0f8db2f36c7eb21ad3c0be19385d87da5781a
# This is public technical source and executable data, not a game ROM.
FROZEN_COMPONENT_SHA256 = {
    "dino-driver.xml": "b6a89430b5e982ad533ea96faa53084506b4ca62f0f63ea6cdedd74324dda4c8",
    "MAME-0106-LICENSE.txt": "1af19840b4175b49f3b84fe019afd8f5120afe57426e68eb0ffdc72c338230c5",
    "mame0106-build-compat.patch": "eb407faa838fa18043ef04f427c2e4a2b5f8383391b2d4bfc265832d102e4666",
    "mame0106-help.txt": "aa2ddb031f0bdf9980881259ed6c9ceb477806609a7213e7e45c890b64f49cc6",
    "mame0106-inprocess-count-trace-combined.patch": "bc48717ff1290ab64f233bff8ac1af800d0ffcda4a23e3b7a006e4fbc518cdff",
    "mame0106-showconfig.txt": "3ac48b4ecf0a34e309837998e1dadb7070388383c48d11f312983fb29360feda",
    "mame0106-source.zip": "ec0811d8f3e651d1004909127416886e1a0ac7609094c14eea1de0b9d7383f94",
    "mame0106-windowed-mng-capture.patch": "4c8ad3ee01c8970780bbc8645ad038b849f1f8998d330c58f4307997b6e8f34e",
    "mame0106.exe": "a3b0526056c2ecd10415a5757f0085aa6977992feddbb232ca60c7c446f81d44",
    "runtime-status.txt": "90db48f6ba82218e41590f6d5bf8cbbcb1afcdf42a8176c45f64071aa130616f",
    "SHA256SUMS.txt": "80c09b332634075210c93fddb852f84de80eeda793571950a7b9fc6d81e1bc70",
    "source-pin.txt": "dff258c5191b2d0052df3b45f9c602da068e720799748d7002e84afc0fb8010f",
}


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


def verify_frozen_components(root: Path, expected_hashes=None) -> int:
    """Check every byte of the exact ROM-free technical artifact, not just
    self-consistent SHA256SUMS.txt. Public fixtures may supply synthetic pins.
    """
    expected = FROZEN_COMPONENT_SHA256 if expected_hashes is None else expected_hashes
    if not expected or any(not re.fullmatch(r"[a-f0-9]{64}", digest)
                           for digest in expected.values()):
        raise ProbeError("invalid_frozen_pins")
    if any("/" in name or "\\" in name or name in (".", "..")
           for name in expected):
        raise ProbeError("invalid_frozen_inventory")
    try:
        contents = list(root.iterdir())
    except OSError as exc:
        raise ProbeError("artifact_directory_unavailable") from exc
    if {item.name for item in contents} != set(expected):
        raise ProbeError("frozen_inventory_mismatch")
    for name, expected_sha in expected.items():
        file = root / name
        if not file.is_file() or file.is_symlink():
            raise ProbeError("frozen_member_type")
        if sha256_file(file) != expected_sha:
            raise ProbeError("frozen_component_mismatch")
    return len(expected)


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
        report.append(f"frozen_components_verified={verify_frozen_components(root)}")
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
