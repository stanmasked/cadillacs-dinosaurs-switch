"""Conservative summary of three correlated, ROM-free MAME frame-offset checks.

All signals originate from the SAME CPS-A/B register capture stream.
Agreement is diagnostic consistency, not independently verified frame timing,
original data provenance, framebuffer pixels or the VBlank-latched OBJ age.
"""


def _flag(mapping, key):
    value = mapping.get(key)
    if type(value) is not bool:
        raise ValueError(f'Expected explicit boolean {key}')
    return value


def _offset(mapping, key, informative):
    value = mapping.get(key)
    if not informative:
        if value is not None:
            # Stage 44 may retain a tentative exact offset when its evidence
            # is insufficient; never use it as a supported observation.
            return None
        return None
    if type(value) is not int or abs(value) > 4:
        raise ValueError(f'Informative {key} must be an integer from -4 to +4')
    return value


def diagnostic_verdict(exact, transition, stability):
    """Classify *diagnostic* consistency without granting parity eligibility."""
    if not all(isinstance(value, dict)
               for value in (exact, transition, stability)):
        raise ValueError('Expected three diagnostic report objects')
    for name, report in (('exact', exact), ('transition', transition),
                         ('stability', stability)):
        if report.get('frame_sync_verified') is not False:
            raise ValueError(f'{name} incorrectly claims synchronized frames')
        if report.get('pixel_parity_eligible') is not False:
            raise ValueError(f'{name} incorrectly claims original pixel parity')

    exact_ok = _flag(exact, 'offset_hypothesis_informative')
    transition_ok = _flag(transition, 'transition_hypothesis_informative')
    applicable = _flag(stability, 'leave_one_out_applicable')
    stable = _flag(stability, 'leave_one_out_stable')
    if (_flag(exact, 'word_distance_diagnostic_only') is not True or
            _flag(transition, 'transition_diagnostic_only') is not True or
            _flag(stability, 'leave_one_out_diagnostic_only') is not True):
        raise ValueError('Diagnostic-only provenance must be explicitly preserved')
    if applicable != transition_ok or (stable and not applicable):
        raise ValueError('Stability metadata conflicts with transition assessment')
    trials = stability.get('leave_one_out_trial_count')
    consistent = stability.get('leave_one_out_consistent_trials')
    unstable = stability.get('leave_one_out_unstable_indices')
    if (type(trials) is not int or type(consistent) is not int or
            not isinstance(unstable, list) or
            any(type(index) is not int for index in unstable)):
        raise ValueError('Invalid leave-one-out trial counters')
    if not applicable:
        if trials != 0 or consistent != 0 or unstable:
            raise ValueError('Inapplicable leave-one-out report cannot have trials')
    elif (not 3 <= trials <= 23 or not 0 <= consistent <= trials or
            len(unstable) != trials - consistent or
            sorted(set(unstable)) != unstable or
            any(not 0 <= index < trials for index in unstable)):
        raise ValueError('Inconsistent leave-one-out trial accounting')
    if stable and (consistent != trials or unstable):
        raise ValueError('Stable label requires all bounded trials to pass')
    if applicable and not stable and consistent == trials:
        raise ValueError('All passing trials must be labeled stable')

    exact_offset = _offset(exact, 'best_offset_steps', exact_ok)
    transition_offset = _offset(
        transition, 'transition_best_offset_steps', transition_ok)
    # A full Stage 49 CLI report supplies the original sample count, the
    # nominal frame step, and per-offset candidate evidence. Recheck those
    # relationships here so a stale or mixed diagnostic object cannot be
    # promoted merely by setting its boolean conclusion fields to True.
    if 'sample_count' in exact or 'frame_step' in exact:
        count = exact.get('sample_count')
        step = exact.get('frame_step')
        if (type(count) is not int or not 4 <= count <= 24 or
                type(step) is not int or not 1 <= step <= 120):
            raise ValueError('Invalid or incomplete frame-series metadata')
        if applicable and trials != count - 1:
            raise ValueError('LOO trial count disagrees with source frame count')
        if exact_ok and exact.get('best_offset_nominal_frames') != exact_offset * step:
            raise ValueError('Exact offset uses inconsistent nominal frame units')
        if (transition_ok and
                transition.get('transition_best_offset_nominal_frames') !=
                transition_offset * step):
            raise ValueError('Transition offset uses inconsistent nominal frame units')

    def require_support(report, key, offset, kind):
        rows = report.get(key)
        if rows is None:
            return  # Legacy focused caller without candidate rows.
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError(f'Malformed {kind} candidate evidence')
        selected = [row for row in rows if row.get('offset_steps') == offset]
        if len(selected) != 1:
            raise ValueError(f'{kind} candidate offset absent or ambiguous')
        row = selected[0]
        if kind == 'exact':
            if (type(row.get('exact_equal_pairs')) is not int or
                    row['exact_equal_pairs'] < 3 or
                    type(row.get('distinct_equal_register_states')) is not int or
                    row['distinct_equal_register_states'] < 2):
                raise ValueError('Exact candidate lacks required register evidence')
        else:
            if (row.get('overlap_sufficient') is not True or
                    type(row.get('matching_active_transitions')) is not int or
                    row['matching_active_transitions'] < 3 or
                    type(row.get('distinct_matching_change_masks')) is not int or
                    row['distinct_matching_change_masks'] < 2):
                raise ValueError('Transition candidate lacks required active evidence')

    if exact_ok:
        require_support(exact, 'candidates', exact_offset, 'exact')
    if transition_ok:
        require_support(transition, 'transition_candidates',
                        transition_offset, 'transition')
    if 'leave_one_out_reason' in stability:
        expected = ('BASE_HYPOTHESIS_INCONCLUSIVE' if not applicable else
                    'ALL_OMISSIONS_PRESERVE_DIAGNOSTIC_OFFSET' if stable else
                    'SENSITIVE_TO_OMITTED_TRANSITIONS')
        if stability['leave_one_out_reason'] != expected:
            raise ValueError('LOO reason conflicts with trial results')

    both = exact_ok and transition_ok
    agreement = exact_offset == transition_offset if both else None

    if both and not agreement:
        status = 'CONFLICTING_REGISTER_DIAGNOSTICS'
        candidate = None
        reason = ('Exact register values and transition masks favor '
                  'different capture offsets')
    elif both and stable:
        status = 'CONSISTENT_BUT_UNVERIFIED'
        candidate = exact_offset
        reason = ('Exact register values, changed-register masks and '
                  'all leave-one-out trials prefer the same offset')
    elif both:
        status = 'FRAGILE_REGISTER_DIAGNOSTIC'
        candidate = None
        reason = ('Two register methods agree but the candidate did not '
                  'survive every leave-one-out transition trial')
    elif exact_ok:
        status = 'EXACT_ONLY_UNCORROBORATED'
        candidate = None
        reason = 'Transition masks provided no informative matching offset'
    elif transition_ok:
        status = 'TRANSITION_ONLY_UNCORROBORATED'
        candidate = None
        reason = 'No informative whole-register-set offset agrees'
    else:
        status = 'INSUFFICIENT_REGISTER_EVIDENCE'
        candidate = None
        reason = 'Neither exact values nor transition masks are informative'
    return {
        'status': status,
        'diagnostic_candidate_offset_steps': candidate,
        'exact_transition_offsets_agree': agreement,
        'leave_one_out_stable': stable,
        'source_signal_count': 3,
        'independent_physical_measurement_count': 0,
        'reason': reason,
        'next_requirement': (
            'Run instrumented MAME 0.289 on private authentic game data; '
            'verify callback order, VBlank OBJ latch age and pixel frames.'),
        'diagnostic_only': True,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
