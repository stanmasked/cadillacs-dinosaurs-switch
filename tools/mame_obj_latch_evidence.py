#!/usr/bin/env python3
"""Read optional MAME 0.289 dino OBJ latch call counters (NOT VBlank proof).

The counter comes from a private instrumented cps1_objram_latch(state)
callback and is sampled by a separate video update hook. Event counts
alone cannot verify the displayed frame, latch age, or raster parity.
"""
from pathlib import Path
import re

PREFIX_V1 = b'CPS1_DINO_LATCH_V1 '
LINE_RE_V1 = re.compile(rb'CPS1_DINO_LATCH_V1 (0|[1-9][0-9]*)\n\Z')
LINE_RE_V2 = re.compile(
    rb'CPS1_DINO_LATCH_V2 (0|[1-9][0-9]*) ([0-9a-f]{16})\n\Z')
MAX_COUNT = (1 << 64) - 1
MAX_LINE_BYTES = 80
FNV_OFFSET = 14695981039346656037
FNV_PRIME = 1099511628211


def obj_fnv1a64(blob):
    """Hash the exact 2048 serialized big-endian OBJ bytes in C++ order."""
    if type(blob) is not bytes or len(blob) != 2048:
        raise ValueError('FNV binding requires exactly 2048 OBJ bytes')
    h = FNV_OFFSET
    for byte in blob:
        h = ((h ^ byte) * FNV_PRIME) & MAX_COUNT
    return f'{h:016x}'


def latch_counter_diagnostic(directory, first_frame, frame_count, frame_step,
                             changed_obj_slots=None, obj_frames=None):
    """Return monotonically increasing observations from every nominal sample.

    This is opt-in: if any sidecar is absent, the entire diagnostic fails,
    rather than treating missing samples as zero callbacks. Count differences
    cover frame_step nominal frame labels; they are NOT latch age or timings.
    """
    if (type(first_frame) is not int or first_frame < 0 or
            type(frame_count) is not int or not 4 <= frame_count <= 24 or
            type(frame_step) is not int or not 1 <= frame_step <= 120 or
            first_frame + (frame_count - 1) * frame_step > 99999999):
        raise ValueError('Invalid OBJ latch-counter capture bounds')
    if changed_obj_slots is not None and (
            not isinstance(changed_obj_slots, (list, tuple)) or
            len(changed_obj_slots) != frame_count - 1 or
            any(type(x) is not int or not 0 <= x <= 256
                for x in changed_obj_slots)):
        raise ValueError('OBJ change series does not match capture intervals')
    if obj_frames is not None and (
            not isinstance(obj_frames, (tuple, list)) or
            len(obj_frames) != frame_count or
            any(type(x) is not bytes or len(x) != 2048 for x in obj_frames)):
        raise ValueError('OBJ fingerprint series must contain complete probes')

    root = Path(directory)
    frames = [first_frame + i * frame_step for i in range(frame_count)]
    counts = []
    versions = []
    for index, frame in enumerate(frames):
        path = root / (f'frame-{frame:08d}.obj-latch-count.txt')
        with path.open('rb') as source:
            line = source.read(MAX_LINE_BYTES + 1)
        if len(line) > MAX_LINE_BYTES:
            raise ValueError(f'{path.name}: oversized latch-counter sidecar')
        match_v2 = LINE_RE_V2.fullmatch(line)
        match_v1 = LINE_RE_V1.fullmatch(line) if match_v2 is None else None
        if match_v2:
            version = 2
            if obj_frames is None:
                raise ValueError(f'{path.name}: V2 requires original OBJ sidecar bytes')
            declared_fnv = match_v2.group(2).decode('ascii')
            actual_fnv = obj_fnv1a64(obj_frames[index])
            if declared_fnv != actual_fnv:
                raise ValueError(f'{path.name}: buffered OBJ fingerprint mismatch')
            value = int(match_v2.group(1))
        elif match_v1:
            version = 1
            value = int(match_v1.group(1))
        else:
            raise ValueError(f'{path.name}: malformed latch-counter sidecar')
        if versions and version != versions[0]:
            raise ValueError(f'{path.name}: mixed V1/V2 counter series')
        if value > MAX_COUNT:
            raise ValueError(f'{path.name}: latch counter exceeds uint64 range')
        if counts and value < counts[-1]:
            raise ValueError(f'{path.name}: latch counter decreased; possible MAME reset')
        versions.append(version)
        counts.append(value)

    differences = [after - before for before, after in zip(counts, counts[1:])]
    changes_without_latch = (
        [frames[i+1] for i, (diff, changed) in enumerate(
            zip(differences, changed_obj_slots)) if diff == 0 and changed > 0]
        if changed_obj_slots is not None else None
    )
    return {
        'status': 'LATCH_CALLBACK_COUNTS_UNVERIFIED',
        'diagnostic_only': True,
        'sidecar_format_version': versions[0],
        'obj_byte_fingerprint_binding': (
            'FNV1A64_ALL_SAMPLES_MATCHED' if versions[0] == 2
            else 'LEGACY_V1_NOT_BOUND'),
        'obj_byte_fingerprint_verified_count': (
            frame_count if versions[0] == 2 else 0),
        'obj_byte_fingerprint_is_cryptographic': False,
        'capture_source': 'MAME_0289_CPP_CPS1_OBJRAM_LATCH_CALL_COUNTER',
        'nominal_frame_labels': frames,
        'observed_latch_callback_counts': counts,
        'inter_sample_callback_deltas': differences,
        'zero_callback_delta_frames': [
            frames[i+1] for i, delta in enumerate(differences) if delta == 0],
        'multiple_callback_delta_frames': [
            frames[i+1] for i, delta in enumerate(differences) if delta > 1],
        'obj_changed_without_observed_latch_frames': changes_without_latch,
        'obj_latch_age_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
        'warning': (
            'These are MAME emulator callback counts, not independent hardware '
            'VBlank pulses. Sampled after video update begins; nominal frame '
            'numbers, callback deltas and OBJ changes do not prove which '
            'VBlank buffered the displayed sprites, or original pixel parity.'
        ),
    }
