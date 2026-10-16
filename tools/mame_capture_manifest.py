"""Validate local MAME dino frame identity before reading capture binaries.

A valid manifest describes a coherent set of files; it cannot prove that
uncaptured VBlank-latched sprite state was present or pixels match MAME.
"""
import re

_FRAME_NAME = re.compile(r'frame-([0-9]{8})\Z')

# Numeric constants are the exact dino QSound CPS-1 / MAME visible aperture.
_EXPECTED = {
    'game': 'dino',
    'capture_hook': 'frame_done',
    'gfxram_bytes': 0x30000,
    'cps_a_bytes': 64,
    'cps_b_bytes': 64,
    'palette_bytes': 3072 * 3,
    'reference_width': 384,
    'reference_height': 224,
    'reference_rgb_bytes': 384 * 224 * 3,
    'raw_word_endianness': 'big',
    'palette_source': 'MAME_effective_pen_color',
    'obj_latch': 'NOT_CAPTURED',
    'pixel_parity_eligible': False,
}


def validate_frame_stem(frame_stem):
    """Reject path traversal and non-canonical frame names before any I/O."""
    if not isinstance(frame_stem, str):
        raise ValueError('MAME capture frame name must be a string')
    match = _FRAME_NAME.fullmatch(frame_stem)
    if match is None:
        raise ValueError('MAME frame name must be frame- followed by eight digits')
    return int(match.group(1))


def validate_capture_manifest(manifest, frame_stem):
    """Reject mismatched file names, frame numbers and capture provenance."""
    frame = validate_frame_stem(frame_stem)
    if not isinstance(manifest, dict):
        raise ValueError('MAME capture manifest must be an object')
    if type(manifest.get('frame')) is not int or manifest['frame'] != frame:
        raise ValueError('MAME capture frame number does not match file name')
    for key, expected in _EXPECTED.items():
        actual = manifest.get(key)
        if type(actual) is not type(expected) or actual != expected:
            raise ValueError(f'Unsupported MAME capture manifest field: {key}')
    return frame
