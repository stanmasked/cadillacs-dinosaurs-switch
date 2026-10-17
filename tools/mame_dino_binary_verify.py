#!/usr/bin/env python3
"""ROM-free, fail-closed verification of an actual built MAME dino subtarget.

Checks the original driver XML, session-aware cps1_v.o in the MAME build
tree, and the same probe strings in the actual linked dino executable.
This is build identity evidence, not original-game or VBlank parity.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

MAX_XML_BYTES = 2 * 1024 * 1024
MAX_OBJECT_BYTES = 64 * 1024 * 1024
MAX_BINARY_BYTES = 2 * 1024 * 1024 * 1024
SCAN_CHUNK_BYTES = 1024 * 1024
PROBE_COMPILED_MARKER = b'CPS1_DINO_LATCH_V2'
SESSION_COMPILED_MARKER = b'CPS1_DINO_SESSION'
SESSION_ENV_COMPILED_MARKER = b'CPS1_DINO_CAPTURE_SESSION'
OBJECT_BASENAME = 'cps1_v.o'
EXPECTED_DRIVER = 'dino'
EXPECTED_SOURCE = 'capcom/cps1.cpp'


def validate_dino_xml(data):
    """Accept exactly one runnable original dino in a bounded MAME listxml."""
    if type(data) is not bytes or len(data) == 0 or len(data) > MAX_XML_BYTES:
        raise ValueError('MAME listxml is empty, too large or not raw bytes')
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError('MAME -listxml dino produced invalid XML') from exc
    build = root.get('build', '')
    if (root.tag != 'mame' or
            not (build == '0.289' or build.startswith('0.289 '))):
        raise ValueError('Unexpected MAME version or listxml root')
    # Actual MAME -listxml includes additional *non-runnable* device
    # entries after the selected driver. Reject other runnable games or
    # malformed device entries, but do not mistake legitimate sound/video
    # device metadata for a second original arcade game.
    machines = root.findall('machine')
    games = [m for m in machines if m.get('isdevice') != 'yes']
    devices = [m for m in machines if m.get('isdevice') == 'yes']
    if len(games) != 1 or games[0].get('name') != EXPECTED_DRIVER:
        raise ValueError('Expected exactly one original dino game driver')
    if any(d.get('runnable') != 'no' or not d.get('name') or
           not d.get('sourcefile') for d in devices):
        raise ValueError('Unexpected runnable or malformed MAME device')
    machine = games[0]
    if (machine.get('sourcefile') != EXPECTED_SOURCE or
            machine.get('runnable', 'yes') != 'yes' or
            machine.get('isbios', 'no') != 'no'):
        raise ValueError('dino metadata missing original runnable CPS-1 driver')
    description = machine.find('description')
    if description is None or not (description.text or '').strip():
        raise ValueError('dino driver metadata lacks a description')
    return {
        'mame_build': root.get('build'),
        'driver': EXPECTED_DRIVER,
        'driver_sourcefile': EXPECTED_SOURCE,
        'runnable': True,
        'listxml_validated': True,
        'auxiliary_device_entries': len(devices),
        'real_game_run': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }


def verify_compiled_cps1_video_object(directory):
    """Verify this Linux MAME build emitted a regular nonempty ELF .o file."""
    root = Path(directory)
    if not root.is_dir():
        raise ValueError('MAME build directory is missing')
    objects = sorted(path for path in root.rglob(OBJECT_BASENAME)
                     if path.is_file() and not path.is_symlink())
    if len(objects) != 1:
        raise ValueError('Expected exactly one real cps1_v.o in MAME build tree')
    path = objects[0]
    size = path.stat().st_size
    if size < 64 or size > MAX_OBJECT_BYTES:
        raise ValueError('Compiled cps1_v.o is truncated or oversized')
    with path.open('rb') as file:
        data = file.read(MAX_OBJECT_BYTES + 1)
    if not data.startswith(b'\x7fELF'):
        raise ValueError('Compiled cps1_v.o is not a Linux ELF object')
    if PROBE_COMPILED_MARKER not in data:
        raise ValueError('Compiled cps1_v.o lacks the generated latch V2 format')
    if SESSION_COMPILED_MARKER not in data:
        raise ValueError('Compiled cps1_v.o lacks the new session label sidecar format')
    if SESSION_ENV_COMPILED_MARKER not in data:
        raise ValueError('Compiled cps1_v.o lacks the session environment lookup')
    return {
        'compiled_cps1_video_object': True,
        'compiled_instrumented_latch_v2_format': True,
        'compiled_session_label_probe_marker': True,
        'compiled_session_environment_probe_marker': True,
        'compiled_cps1_video_object_bytes': path.stat().st_size,
        'compiled_cps1_video_object_relative_path': path.relative_to(root).as_posix(),
        'instrumentation_runtime_verified': False,
    }


def verify_linked_probe_markers(binary):
    """Require all three C++ probe strings in the linked ELF, not just .o.

    Read the executable incrementally; it can be much larger than the .o.
    This is a ROM-free *static* link-consistency check, not proof the
    instrumented video hook executed at runtime or observed VBlank.
    """
    path = Path(binary)
    if not path.is_file() or path.is_symlink():
        raise ValueError('Linked MAME executable is missing or symlinked')
    size = path.stat().st_size
    if not 64 <= size <= MAX_BINARY_BYTES:
        raise ValueError('Linked MAME executable size is invalid')
    markers = (PROBE_COMPILED_MARKER, SESSION_COMPILED_MARKER,
               SESSION_ENV_COMPILED_MARKER)
    found = set()
    overlap = b''
    carry = max(map(len, markers)) - 1
    with path.open('rb') as source:
        if source.read(4) != b'\x7fELF':
            raise ValueError('Linked MAME executable is not ELF')
        source.seek(0)
        while True:
            chunk = source.read(SCAN_CHUNK_BYTES)
            if not chunk:
                break
            window = overlap + chunk
            found.update(marker for marker in markers if marker in window)
            overlap = window[-carry:]
    if len(found) != len(markers):
        raise ValueError('Linked MAME executable lacks session-aware V2 probe markers')
    return {
        'linked_dino_executable_probe_markers': True,
        'linked_latch_v2_probe_marker': True,
        'linked_session_label_probe_marker': True,
        'linked_session_environment_probe_marker': True,
        'linked_probe_runtime_verified': False,
    }


def inspect_binary(binary, build_dir, timeout_seconds=90):
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 120:
        raise ValueError('Invalid ROM-free listxml timeout')
    file = Path(binary)
    if not file.is_file() or file.is_symlink():
        raise ValueError('MAME dino executable path is missing or a symlink')
    if not Path(build_dir).is_dir():
        raise ValueError('MAME root directory is missing')
    # MAME may emit a large XML and verbose diagnostics. Keep both
    # streams in disposable disk-backed files, *not* unbounded PIPEs.
    # Read at most MAX_XML_BYTES + 1 into memory after process exit.
    with tempfile.TemporaryFile(mode='w+b') as xml_output, \
            tempfile.TemporaryFile(mode='w+b') as diagnostics:
        try:
            process = subprocess.run(
                [str(file.resolve()), '-listxml', EXPECTED_DRIVER],
                stdin=subprocess.DEVNULL, stdout=xml_output,
                stderr=diagnostics, timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError('MAME ROM-free driver metadata command failed') from exc
        if process.returncode != 0:
            raise ValueError('MAME ROM-free driver metadata command exited nonzero')
        xml_output.seek(0, 2)
        length = xml_output.tell()
        if not 0 < length <= MAX_XML_BYTES:
            raise ValueError('MAME ROM-free listxml exceeded the allowed size')
        xml_output.seek(0)
        data = xml_output.read(MAX_XML_BYTES + 1)
    result = validate_dino_xml(data)
    result.update(verify_compiled_cps1_video_object(build_dir))
    result.update(verify_linked_probe_markers(file))
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mame_dino_binary', type=Path)
    parser.add_argument('mame_source_tree', type=Path)
    args = parser.parse_args(argv)
    try:
        result = inspect_binary(args.mame_dino_binary, args.mame_source_tree)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError) as exc:
        print(f'MAME ROM-free binary verification refused: {exc}',
              file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
