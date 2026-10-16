"""Check CRC-32 of each private MAME capture component before import.

CRC-32 detects accidental damage or mixups among same-size files; it is not
cryptographic authentication. Real game assets must remain local.
"""
import re
import zlib

CAPTURE_FILES = (
    'gfxram-be.bin',
    'cps-a-be.bin',
    'cps-b-be.bin',
    'palette-rgb24.bin',
    'reference-rgb24.bin',
)
_CRC_HEX = re.compile(r'[0-9a-f]{8}\Z')


def capture_checksums(files):
    """Return eight-digit lowercase CRC-32 values for the five raw binaries."""
    if not isinstance(files, dict) or set(files) != set(CAPTURE_FILES):
        raise ValueError('Expected exactly five MAME capture binaries')
    result = {}
    for name in CAPTURE_FILES:
        data = files[name]
        if not isinstance(data, bytes):
            raise ValueError(f'{name}: capture data must be bytes')
        result[name] = f'{zlib.crc32(data) & 0xffffffff:08x}'
    return result


def validate_capture_checksums(manifest, files):
    """Require complete manifests and verify every input before decoding."""
    if not isinstance(manifest, dict):
        raise ValueError('MAME capture manifest must be an object')
    declared = manifest.get('file_crc32')
    if not isinstance(declared, dict) or set(declared) != set(CAPTURE_FILES):
        raise ValueError('MAME capture requires five file_crc32 entries')
    for name in CAPTURE_FILES:
        value = declared[name]
        if not isinstance(value, str) or _CRC_HEX.fullmatch(value) is None:
            raise ValueError(f'{name}: invalid file_crc32 field')
    actual = capture_checksums(files)
    for name in CAPTURE_FILES:
        if actual[name] != declared[name]:
            raise ValueError(f'{name}: CRC32 mismatch in MAME capture')
    return actual
