#!/usr/bin/env python3
"""ROM-free structural activity diagnostics for *private* MAME RGB captures.

These observations cannot identify the game, active gameplay, original
VBlank age, original/HD pixel parity, or Nintendo Switch rendering.
Reference RGB bytes stay private; returned metadata contains no pixels.
"""
from pathlib import Path

REF_W = 384
REF_H = 224
PIXELS = REF_W * REF_H
REFERENCE_BYTES = PIXELS * 3


def reference_activity_diagnostic(directory, first_frame, frame_count, frame_step):
    """Read bounded raw RGB24 reference frames and compare nominal samples.

    Call this AFTER the existing five-file CRC32 audit has passed. The
    dimensions are fixed to CPS-1 dino's native reference capture.
    """
    if (type(first_frame) is not int or not 0 <= first_frame <= 99999999 or
            type(frame_count) is not int or not 4 <= frame_count <= 24 or
            type(frame_step) is not int or not 1 <= frame_step <= 120 or
            first_frame + (frame_count - 1) * frame_step > 99999999):
        raise ValueError('Invalid bounded reference RGB frame interval')
    root = Path(directory)
    labels = [first_frame + frame_step * n for n in range(frame_count)]
    previous = None
    per_frame_color_counts = []
    nonblack_counts = []
    changed_pixels = []
    for frame in labels:
        path = root / f'frame-{frame:08d}.reference-rgb24.bin'
        with path.open('rb') as stream:
            blob = stream.read(REFERENCE_BYTES + 1)
        if len(blob) != REFERENCE_BYTES:
            raise ValueError(f'frame-{frame:08d}: incomplete or oversized RGB reference')
        # Count exact RGB colors; never retain color values beyond this step,
        # and never publish the RGB bytes or any original-game screenshot.
        per_frame_color_counts.append(
            len(set(blob[offset:offset + 3]
                    for offset in range(0, REFERENCE_BYTES, 3))))
        nonblack_counts.append(sum(
            blob[offset:offset + 3] != b'\x00\x00\x00'
            for offset in range(0, REFERENCE_BYTES, 3)))
        if previous is not None:
            changed_pixels.append(sum(
                blob[offset:offset + 3] != previous[offset:offset + 3]
                for offset in range(0, REFERENCE_BYTES, 3)))
        previous = blob
    static = not any(changed_pixels)
    all_black = all(count == 0 for count in nonblack_counts)
    single_color = all(count <= 1 for count in per_frame_color_counts)
    return {
        'status': (
            'ALL_BLACK_REFERENCE_SEQUENCE' if all_black else
            'STATIC_REFERENCE_SEQUENCE' if static else
            'REFERENCE_BYTES_CHANGED_UNVERIFIED'),
        'diagnostic_only': True,
        'nominal_frame_labels': labels,
        'reference_width': REF_W,
        'reference_height': REF_H,
        'exact_unique_rgb_colors_per_frame': per_frame_color_counts,
        'nonblack_pixel_counts_per_frame': nonblack_counts,
        'changed_pixel_counts_per_interval': changed_pixels,
        'changed_reference_intervals': sum(x > 0 for x in changed_pixels),
        'static_reference_sequence': static,
        'all_black_reference_sequence': all_black,
        'all_frames_single_color': single_color,
        'active_gameplay_verified': False,
        'reference_capture_provenance_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
        'warning': (
            'RGB changes or nonblack pixels are structural byte observations '
            'only. A title screen, service screen, attract mode or synthetic '
            'scene may produce changes. Static frames may be authentic. '
            'Neither activity nor integrity proves original gameplay, '
            'VBlank alignment or Nintendo Switch pixel parity.'
        ),
    }
