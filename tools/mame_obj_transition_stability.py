"""Leave-one-transition-out robustness check for private CPS-1 frame diagnostics.

This reuses the same registers as the primary audit, so it is not an
independent confirmation of original video timing, VBlank, or pixel parity.
The removed observation is one *transition pair* at a fixed render index;
frames are NEVER spliced or assigned new frame numbers.
"""

try:
    from tools.mame_obj_transition_evidence import _change_masks, transition_diagnostic
except ModuleNotFoundError:
    from mame_obj_transition_evidence import _change_masks, transition_diagnostic


def transition_leave_one_out(render, lua, frame_step, max_offset_steps=2):
    """Check whether a proposed transition offset survives every omitted pair.

    The primary analysis validates input shapes and sets the original
    conditional offset. Re-run candidate scoring after excluding each of
    the n-1 render transition *indices* in turn. All candidates use the
    same omitted index; no data points are shifted or synthesized.
    """
    base = transition_diagnostic(render, lua, frame_step, max_offset_steps)
    target = base['transition_best_offset_steps']
    if target is None:
        return {
            'leave_one_out_applicable': False,
            'leave_one_out_trial_count': 0,
            'leave_one_out_consistent_trials': 0,
            'leave_one_out_unstable_indices': [],
            'leave_one_out_stable': False,
            'leave_one_out_reason': 'BASE_HYPOTHESIS_INCONCLUSIVE',
            'leave_one_out_diagnostic_only': True,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        }
    src = _change_masks(render)
    dst = _change_masks(lua)
    total = len(src)
    stable_count = 0
    unstable = []
    for omitted in range(total):
        candidates = []
        for offset in range(-max_offset_steps, max_offset_steps + 1):
            pairs = [(src[i], dst[i + offset]) for i in range(total)
                     if i != omitted and 0 <= i + offset < total]
            # max_offset_steps <= len(render)-3 guarantees at least one
            # overlap even after dropping one render transition.
            matches = [a for a, b in pairs if a and a == b]
            candidates.append({
                'offset_steps': offset,
                'matched': len(matches),
                'distinct': len(set(matches)),
                'overlap': len(pairs),
                'fraction': len(matches) / len(pairs),
                'coverage_sufficient': len(pairs) * 4 >= (total - 1) * 3,
            })
        highest = max(row['fraction'] for row in candidates)
        tied = [row for row in candidates if row['fraction'] == highest]
        winner = tied[0] if len(tied) == 1 else None
        valid = (winner is not None and
                 winner['offset_steps'] == target and
                 winner['coverage_sufficient'] and
                 winner['matched'] >= 3 and winner['distinct'] >= 2)
        if valid:
            stable_count += 1
        else:
            unstable.append(omitted)

    return {
        'leave_one_out_applicable': True,
        'leave_one_out_trial_count': total,
        'leave_one_out_consistent_trials': stable_count,
        'leave_one_out_unstable_indices': unstable,
        'leave_one_out_stable': stable_count == total,
        'leave_one_out_reason': (
            'ALL_OMISSIONS_PRESERVE_DIAGNOSTIC_OFFSET'
            if stable_count == total else 'SENSITIVE_TO_OMITTED_TRANSITIONS'),
        'leave_one_out_diagnostic_only': True,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
