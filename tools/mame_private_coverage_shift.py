#!/usr/bin/env python3
"""Conservative size-only Lua/C++ nominal-label coverage hypotheses.

Use only metadata obtained from the read-only private capture directory scan.
Off-label overlap is NOT evidence of sprite age, execution order, CPS-1 VBlank
or original-game pixel parity. Never read ROMs, framebuffer or OBJ data.
"""

SHIFTS = (-2, -1, 0, 1, 2)
LUA_FILES_PER_FRAME = 6
CPP_FILES_PER_FRAME = 3


def nominal_coverage_shift_hypotheses(rows, *, first_frame=900, frame_step=2):
    """Return bounded, unverified overlap scores for six expected frame labels.

    Shift +1 means: Lua set at frame label i and C++ set at *next*
    nominal sampled label i+1. This is an index comparison only; it
    deliberately does not infer when MAME actually emitted either file.
    """
    if (type(first_frame) is not int or not 0 <= first_frame <= 99999999 or
            type(frame_step) is not int or not 1 <= frame_step <= 120 or
            not isinstance(rows, (tuple, list)) or len(rows) != 6 or
            first_frame + 5 * frame_step > 99999999):
        raise ValueError('Private coverage shift selection is invalid')

    lua, cpp = [], []
    for i, row in enumerate(rows):
        if not isinstance(row, dict) or type(row.get('nominal_frame')) is not int or (
                row['nominal_frame'] != first_frame + i * frame_step):
            raise ValueError('Private coverage shift frame labels are invalid')
        lua_count = row.get('lua_valid_sized_files')
        cpp_count = row.get('cpp_valid_sized_files')
        if (type(lua_count) is not int or not 0 <= lua_count <= LUA_FILES_PER_FRAME or
                type(cpp_count) is not int or not 0 <= cpp_count <= CPP_FILES_PER_FRAME):
            raise ValueError('Private coverage shift counts are invalid')
        lua_complete = lua_count == LUA_FILES_PER_FRAME
        cpp_complete = cpp_count == CPP_FILES_PER_FRAME
        if (row.get('lua_size_only_state') !=
                ('COMPLETE_SIZE_ONLY' if lua_complete else
                 'ABSENT' if row.get('lua_files_present') == 0
                 else 'INCOMPLETE_SIZE_ONLY') or
                row.get('cpp_size_only_state') !=
                ('COMPLETE_SIZE_ONLY' if cpp_complete else
                 'ABSENT' if row.get('cpp_files_present') == 0
                 else 'INCOMPLETE_SIZE_ONLY')):
            raise ValueError('Private coverage shift source states disagree')
        lua.append(lua_complete)
        cpp.append(cpp_complete)

    pairs = {
        shift: sum(lua[i] and cpp[i + shift]
                   for i in range(6) if 0 <= i + shift < 6)
        for shift in SHIFTS
    }
    zero = pairs[0]
    candidates = [shift for shift in SHIFTS if shift != 0]
    high = max(pairs[shift] for shift in candidates)
    winners = [shift for shift in candidates if pairs[shift] == high]
    if min(sum(lua), sum(cpp)) < 3:
        status = 'INSUFFICIENT_COMPLETE_SOURCE_FRAMES'
        hypothesis = None
    elif high < 3 or high <= zero:
        status = 'NO_OFF_LABEL_COVERAGE_ADVANTAGE'
        hypothesis = None
    elif len(winners) != 1:
        status = 'AMBIGUOUS_OFF_LABEL_COVERAGE'
        hypothesis = None
    else:
        status = 'OFF_LABEL_COVERAGE_HYPOTHESIS_ONLY'
        hypothesis = winners[0]

    return {
        'status': status,
        'diagnostic_only': True,
        'shift_offsets_in_nominal_samples': list(SHIFTS),
        'paired_full_size_only_frames_per_shift': [pairs[k] for k in SHIFTS],
        'same_nominal_label_complete_pairs': zero,
        'lua_full_size_only_frames': sum(lua),
        'cpp_full_size_only_frames': sum(cpp),
        'candidate_cpp_relative_to_lua_shift_samples': hypothesis,
        'candidate_cpp_relative_to_lua_shift_nominal_frames': (
            hypothesis * frame_step if hypothesis is not None else None),
        'hypothesis_verified': False,
        'original_game_authenticity_verified': False,
        'active_gameplay_verified': False,
        'hardware_vblank_observed': False,
        'obj_latch_age_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
