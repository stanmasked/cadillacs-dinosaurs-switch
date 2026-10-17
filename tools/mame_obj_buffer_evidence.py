#!/usr/bin/env python3
"""Summarize *unverified* buffered CPS-1 OBJ changes from private MAME probes.

C++ m_buffered_obj samples can reveal scene changes and sprite end markers;
they cannot establish VBlank latch age, Lua/render callback order, or parity.
No original OBJ words are returned or persisted in the diagnostic metadata.
"""
import hashlib

try:
    from tools.mame_obj_probe_import import decode_probe
except ModuleNotFoundError:
    from mame_obj_probe_import import decode_probe

OBJ_BYTES = 2048
REGISTER_BYTES = 128
OBJ_SLOT_BYTES = 8


def obj_buffer_diagnostic(register_frames, obj_frames, first_frame, frame_step):
    """Compare corresponding nominal samples without claiming they are in sync.

    An OBJ entry is four big-endian 16-bit words (8 bytes); adjacent
    changed-slot counts measure raw byte differences, not active sprites.
    A marker is the first slot whose fourth word has high byte 0xff.
    """
    if (type(first_frame) is not int or not 0 <= first_frame <= 99999999 or
            type(frame_step) is not int or not 1 <= frame_step <= 120 or
            not isinstance(register_frames, (tuple, list)) or
            not isinstance(obj_frames, (tuple, list)) or
            len(register_frames) != len(obj_frames) or
            not 4 <= len(obj_frames) <= 24 or
            first_frame + (len(obj_frames)-1)*frame_step > 99999999):
        raise ValueError('Invalid OBJ frame series or nominal capture interval')
    if any(type(blob) is not bytes or len(blob) != REGISTER_BYTES
           for blob in register_frames):
        raise ValueError('OBJ diagnostic requires 128-byte register sidecars')
    if any(type(blob) is not bytes or len(blob) != OBJ_BYTES
           for blob in obj_frames):
        raise ValueError('OBJ diagnostic requires 2048-byte buffered probes')

    marks = [decode_probe(blob)[1] for blob in obj_frames]
    hashes = [hashlib.sha256(blob).hexdigest() for blob in obj_frames]
    changed_obj = [
        sum(a[pos:pos+OBJ_SLOT_BYTES] != b[pos:pos+OBJ_SLOT_BYTES]
            for pos in range(0, OBJ_BYTES, OBJ_SLOT_BYTES))
        for a, b in zip(obj_frames, obj_frames[1:])
    ]
    changed_registers = [
        sum(a[pos:pos+2] != b[pos:pos+2]
            for pos in range(0, REGISTER_BYTES, 2))
        for a, b in zip(register_frames, register_frames[1:])
    ]
    frame_labels = [first_frame + idx*frame_step
                    for idx in range(len(obj_frames))]
    return {
        'diagnostic_only': True,
        'buffered_obj_source': 'MAME_0289_CPP_OBJ_PROBE_UNSYNCED',
        'nominal_frame_labels': frame_labels,
        'obj_probe_sha256': hashes,
        'distinct_obj_buffer_states': len(set(hashes)),
        'changed_obj_slots_per_interval': changed_obj,
        'changed_register_words_per_interval': changed_registers,
        'obj_changed_intervals': sum(value > 0 for value in changed_obj),
        'obj_unchanged_intervals': sum(value == 0 for value in changed_obj),
        'first_end_marker_slots': marks,
        'nominal_frames_without_end_marker': [
            frame for frame, marker in zip(frame_labels, marks) if marker is None],
        'obj_static_while_registers_change_intervals': [
            frame_labels[idx+1] for idx, (obj, reg) in enumerate(
                zip(changed_obj, changed_registers)) if obj == 0 and reg > 0],
        'obj_and_register_change_cooccurrence_intervals': sum(
            obj > 0 and reg > 0
            for obj, reg in zip(changed_obj, changed_registers)),
        'obj_latch_age_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
        'warning': (
            'OBJ state changes, matching nominal frame labels, and end-marker '
            'positions are correlated diagnostics only. Original VBlank latch '
            'age, render/Lua callback timing, pixel parity and Switch visuals '
            'remain unverified.'
        ),
    }
