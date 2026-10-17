"""Diagnostic CPS-1 register *change-mask* alignment across MAME capture hooks.

The masks encode which of 64 16-bit CPS-A/B registers changed between
successive sampled frames. Values, game imagery and RAM are not emitted.
Matching changes do not prove that the underlying frames are synchronized.
"""


def _change_masks(frames):
    changes = []
    for first, second in zip(frames, frames[1:]):
        mask = 0
        for word in range(64):
            i = word * 2
            if first[i:i+2] != second[i:i+2]:
                mask |= 1 << word
        changes.append(mask)
    return changes


def transition_diagnostic(render, lua, frame_step, max_offset_steps=2):
    """Search bounded sample shifts and reject flat/repeated transition patterns.

    A candidate offset k compares transition render(i -> i+1) with
    lua(i+k -> i+k+1); only genuinely changed, equal masks count as
    supporting observations. A unique candidate also needs at least
    three matching changes with two distinct changed-register patterns.
    """
    if (not isinstance(render, (list, tuple)) or
            not isinstance(lua, (list, tuple)) or
            len(render) != len(lua) or not 4 <= len(render) <= 24 or
            type(frame_step) is not int or not 1 <= frame_step <= 120 or
            type(max_offset_steps) is not int or
            not 0 <= max_offset_steps <= min(4, len(render)-3)):
        raise ValueError('Invalid CPS-1 transition series bounds')
    for frames in (render, lua):
        if any(type(frame) is not bytes or len(frame) != 128 for frame in frames):
            raise ValueError('Each CPS-1 register state must be exactly 128 bytes')

    render_changes = _change_masks(render)
    lua_changes = _change_masks(lua)
    n = len(render)
    candidates = []
    for offset in range(-max_offset_steps, max_offset_steps + 1):
        pairs = [(render_changes[i], lua_changes[i+offset])
                 for i in range(n - 1) if 0 <= i+offset < n-1]
        matched = [a for a, b in pairs if a and a == b]
        inactive = sum(a == b == 0 for a, b in pairs)
        candidates.append({
            'offset_steps': offset,
            'offset_nominal_frames': offset * frame_step,
            'overlapping_transitions': len(pairs),
            'matching_active_transitions': len(matched),
            'distinct_matching_change_masks': len(set(matched)),
            'matching_inactive_transitions_non_evidence': inactive,
            'active_transition_match_fraction': len(matched) / len(pairs),
        })

    highest = max(row['active_transition_match_fraction'] for row in candidates)
    tied = [row for row in candidates
            if row['active_transition_match_fraction'] == highest]
    winner = tied[0] if len(tied) == 1 else None
    informative = (
        winner is not None and winner['matching_active_transitions'] >= 3
        and winner['distinct_matching_change_masks'] >= 2
        and len(set(render_changes)) >= 2 and len(set(lua_changes)) >= 2
    )
    return {
        'transition_candidates': candidates,
        'transition_best_offset_steps': winner['offset_steps'] if informative else None,
        'transition_best_offset_nominal_frames': (
            winner['offset_nominal_frames'] if informative else None),
        'transition_hypothesis_informative': bool(informative),
        'transition_ambiguous_best_offsets': (
            [row['offset_steps'] for row in tied] if len(tied) > 1 else []),
        'render_active_transitions': sum(mask != 0 for mask in render_changes),
        'lua_active_transitions': sum(mask != 0 for mask in lua_changes),
        'transition_diagnostic_only': True,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
        'transition_warning': (
            'Equal changed-register masks can recur or occur on different '
            'MAME frames; they do not certify original VBlank/frame timing.'
        ),
    }
