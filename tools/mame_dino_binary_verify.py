#!/usr/bin/env python3
"""ROM-free, fail-closed verification of an actual built MAME dino subtarget.

Checks the original driver XML and that a nonempty ELF object for
instrumented cps1_v.cpp exists in the *freshly built* MAME build tree.
This is build identity evidence, not original-game or VBlank parity.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

MAX_XML_BYTES = 2 * 1024 * 1024
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
    if root.tag != 'mame' or not root.get('build', '').startswith('0.289'):
        raise ValueError('Unexpected MAME version or listxml root')
    machines = root.findall('machine')
    if len(machines) != 1 or machines[0].get('name') != EXPECTED_DRIVER:
        raise ValueError('Expected exactly one original dino driver')
    machine = machines[0]
    if (machine.get('sourcefile') != EXPECTED_SOURCE or
            machine.get('runnable') != 'yes' or
            machine.get('isbios') == 'yes' or
            machine.get('isdevice') == 'yes'):
        raise ValueError('dino metadata missing original runnable CPS-1 driver')
    if machine.find('description') is None:
        raise ValueError('dino driver metadata lacks a description')
    return {
        'mame_build': root.get('build'),
        'driver': EXPECTED_DRIVER,
        'driver_sourcefile': EXPECTED_SOURCE,
        'runnable': True,
        'listxml_validated': True,
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
    if path.stat().st_size < 64:
        raise ValueError('Compiled cps1_v.o is empty or truncated')
    with path.open('rb') as file:
        if file.read(4) != b'\x7fELF':
            raise ValueError('Compiled cps1_v.o is not a Linux ELF object')
    return {
        'compiled_cps1_video_object': True,
        'compiled_cps1_video_object_bytes': path.stat().st_size,
        'compiled_cps1_video_object_relative_path': path.relative_to(root).as_posix(),
        'instrumentation_runtime_verified': False,
    }


def inspect_binary(binary, build_dir, timeout_seconds=90):
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 120:
        raise ValueError('Invalid ROM-free listxml timeout')
    file = Path(binary)
    if not file.is_file() or file.is_symlink():
        raise ValueError('MAME dino executable path is missing or a symlink')
    if not Path(build_dir).is_dir():
        raise ValueError('MAME root directory is missing')
    try:
        process = subprocess.run(
            [str(file.resolve()), '-listxml', EXPECTED_DRIVER],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError('MAME ROM-free driver metadata command failed') from exc
    if process.returncode != 0:
        raise ValueError('MAME ROM-free driver metadata command exited nonzero')
    result = validate_dino_xml(process.stdout)
    result.update(verify_compiled_cps1_video_object(build_dir))
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
