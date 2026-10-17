#!/usr/bin/env python3
"""Conservative size-only Lua/C++ nominal-label coverage hypotheses.

Use only metadata obtained from the read-only private capture directory scan.
Off-label overlap is NOT evidence of sprite age, execution order, CPS-1 VBlank
or original-game pixel parity. Never read ROMs, framebuffer or OBJ data.
"""

SHIFTS = (-2, -1, 0, 1, 2)
LUA_FILES_PER_FRAME = 6
CPP_FILES_PER_FRAME = 3



def _pair_counts(lua, cpp):
    """Count only existing, fixed-position sample pairs, never relabel gaps."""
    return {
        shift: sum(lua[i] and cpp[i + shift]
                   for i in range(6) if 0 <= i + shift < 6)
        for shift in SHIFTS
    }


def _best_unique_offset(pairs, lua, cpp, *, minimum_samples, minimum_pairs):
    if min(sum(lua), sum(cpp)) < minimum_samples:
        return 'INSUFFICIENT_COMPLETE_SOURCE_FRAMES', None
    high = max(pairs[shift] for shift in SHIFTS if shift != 0)
    zero = pairs[0]
    if high < minimum_pairs or high <= zero:
        return 'NO_OFF_LABEL_COVERAGE_ADVANTAGE', None
    winners = [shift for shift in SHIFTS if shift != 0 and pairs[shift] == high]
    if len(winners) != 1:
        return 'AMBIGUOUS_OFF_LABEL_COVERAGE', None
    return 'OFF_LABEL_COVERAGE_HYPOTHESIS_ONLY', winners[0]


def _single_label_dropout_evidence(lua, cpp, hypothesis, frame_step,
                                   first_frame):
    """Remove both streams' evidence at each nominal label in turn.

    Sample positions are kept fixed. The reduced evidence threshold is
    2 complete source sets and 2 overlapping pairs; this merely tests
    sensitivity to one lost label and does NOT certify synchronization.
    """
    if hypothesis is None:
        return {
            'status': 'NOT_ASSESSED_NO_PRIMARY_OFFSET_CANDIDATE',
            'diagnostic_only': True,
            'evaluated_nominal_label_drops': 0,
            'same_candidate_after_drop_count': 0,
            'different_candidate_after_drop_count': 0,
            'no_unique_candidate_after_drop_count': 0,
            'per_nominal_label_drop': [],
            'size_only_offset_stable_under_all_single_label_drops': False,
            'hypothesis_verified': False,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        }

    observations = []
    same = changed = absent = 0
    for dropped in range(6):
        # A lost *nominal label* removes Lua/C++ evidence at the exact same
        # position. Never shift/reindex the remaining four or five samples.
        reduced_lua = [value and i != dropped for i, value in enumerate(lua)]
        reduced_cpp = [value and i != dropped for i, value in enumerate(cpp)]
        reduced_pairs = _pair_counts(reduced_lua, reduced_cpp)
        _, candidate = _best_unique_offset(
            reduced_pairs, reduced_lua, reduced_cpp,
            minimum_samples=2, minimum_pairs=2)
        if candidate == hypothesis:
            state = 'SAME_OFFSET_RETAINED_SIZE_ONLY'
            same += 1
        elif candidate is not None:
            state = 'DIFFERENT_OFFSET_SIZE_ONLY'
            changed += 1
        else:
            state = 'NO_UNIQUE_OFFSET_AFTER_DROP'
            absent += 1
        observations.append({
            'removed_nominal_frame_label': first_frame + dropped * frame_step,
            'outcome': state,
            'original_offset_pairs_remaining': reduced_pairs[hypothesis],
            'zero_offset_pairs_remaining': reduced_pairs[0],
            'candidate_after_removal_samples': candidate,
        })

    if same + changed + absent != 6:
        raise ValueError('Private dropout diagnostic case count disagrees')
    return {
        'status': ('STABLE_UNDER_ALL_SINGLE_LABEL_DROPS_SIZE_ONLY'
                   if same == 6 else
                   'SENSITIVE_TO_SINGLE_LABEL_DROPS_SIZE_ONLY'),
        'diagnostic_only': True,
        'evaluated_nominal_label_drops': 6,
        'same_candidate_after_drop_count': same,
        'different_candidate_after_drop_count': changed,
        'no_unique_candidate_after_drop_count': absent,
        'per_nominal_label_drop': observations,
        'size_only_offset_stable_under_all_single_label_drops': same == 6,
        'hypothesis_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }

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

    pairs = _pair_counts(lua, cpp)
    zero = pairs[0]
    status, hypothesis = _best_unique_offset(
        pairs, lua, cpp, minimum_samples=3, minimum_pairs=3)
    dropout = _single_label_dropout_evidence(
        lua, cpp, hypothesis, frame_step, first_frame)

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
        'single_nominal_label_dropout_evidence': dropout,
        'hypothesis_verified': False,
        'original_game_authenticity_verified': False,
        'active_gameplay_verified': False,
        'hardware_vblank_observed': False,
        'obj_latch_age_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
