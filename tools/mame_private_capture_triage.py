#!/usr/bin/env python3
"""Privacy-preserving next-investigation suggestions for local dino captures.

Works only on post-audit nominal-frame metadata. The fixed vocabulary is
intended to help humans decide what to inspect privately, not certify
authentic gameplay, independently timed VBlank, or Nintendo Switch parity.
"""


def _number(report, key, maximum):
    value = report.get(key)
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError('Private capture triage interval totals are invalid')
    return value


def private_capture_triage(reference_activity, intervals, session,
                           consistency, stability, *, frame_count=6):
    """Generate fixed-code low-information and timing-study guidance only."""
    reports = (reference_activity, intervals, session, consistency, stability)
    if type(frame_count) is not int or not 4 <= frame_count <= 24:
        raise ValueError('Invalid private triage frame count')
    if any(not isinstance(report, dict) for report in reports):
        raise ValueError('Private triage requires five complete reports')
    if any(report.get('diagnostic_only') is not True or
           report.get('frame_sync_verified') is not False or
           report.get('pixel_parity_eligible') is not False
           for report in reports):
        raise ValueError('Private triage requires explicitly conservative reports')

    if (session.get('status') != 'SAME_LAUNCHER_SESSION_LABEL_OBSERVED' or
            session.get('shared_session_label_consistent') is not True or
            session.get('lua_manifest_session_samples') != frame_count or
            session.get('cpp_latch_session_samples') != frame_count or
            session.get('label_is_authenticated_game_provenance') is not False or
            stability.get('source_files_checked') != frame_count * 9 or
            stability.get('source_files_unchanged_during_audit') is not True or
            stability.get('hash_algorithm') != 'SHA256_LOCAL_ONLY_NO_DIGESTS_PUBLISHED' or
            consistency.get('status') != 'PRIVATE_NOMINAL_COUNTER_CONSISTENCY_ONLY' or
            consistency.get('nominal_frame_samples_checked') != frame_count or
            consistency.get('nominal_intervals_checked') != frame_count - 1 or
            any(consistency.get(k) is not True for k in (
                'cumulative_latch_deltas_match',
                'source_interval_annotations_match',
                'cross_stream_interval_fields_match'))):
        raise ValueError('Private triage requires all completed capture integrity gates')

    span = frame_count - 1
    totals = {
        key: _number(intervals, key, span)
        for key in (
            'rgb_change_intervals',
            'obj_change_intervals',
            'latch_increment_intervals',
            'rgb_obj_cochange_intervals',
            'rgb_obj_latch_cochange_intervals',
            'obj_change_without_latch_increment_intervals',
            'latch_increment_without_obj_change_intervals',
        )
    }
    if (reference_activity.get('changed_reference_intervals') !=
            totals['rgb_change_intervals']):
        raise ValueError('Private triage RGB totals disagree')
    if any(type(reference_activity.get(key)) is not bool for key in (
        'all_black_reference_sequence',
        'static_reference_sequence',
        'all_frames_single_color',
    )):
        raise ValueError('Private triage RGB classifications are invalid')
    if (reference_activity['static_reference_sequence'] !=
            (totals['rgb_change_intervals'] == 0)):
        raise ValueError('Private triage static RGB flag disagrees with intervals')
    if (reference_activity['all_black_reference_sequence'] and
            not reference_activity['all_frames_single_color']):
        raise ValueError('Private triage black RGB classification disagrees')

    next_steps = []
    # All guidance is built from fixed literal codes, never filenames,
    # digest strings, ROM content, tokens, or user-provided warnings.
    if reference_activity['all_black_reference_sequence']:
        next_steps.append('CHECK_PRIVATE_VIDEO_CAPTURE_BLACK_FRAMES')
    elif totals['rgb_change_intervals'] == 0:
        next_steps.append('CHECK_PRIVATE_VIDEO_CAPTURE_STATIC_FRAMES')
    if reference_activity['all_frames_single_color']:
        next_steps.append('INSPECT_PRIVATE_SINGLE_COLOR_FRAMES')
    if totals['obj_change_intervals'] == 0:
        next_steps.append('INSPECT_PRIVATE_OBJ_ACTIVITY')
    if totals['latch_increment_intervals'] == 0:
        next_steps.append('INSPECT_PRIVATE_LATCH_CALLBACK_ACTIVITY')
    if totals['obj_change_without_latch_increment_intervals']:
        next_steps.append('INVESTIGATE_OBJ_CHANGES_WITHOUT_LATCH_INCREMENTS')
    if totals['latch_increment_without_obj_change_intervals']:
        next_steps.append('INVESTIGATE_LATCH_INCREMENTS_WITH_STATIC_OBJ')
    if (totals['rgb_change_intervals'] and totals['obj_change_intervals'] and
            not totals['rgb_obj_cochange_intervals']):
        next_steps.append('COMPARE_NONOVERLAPPING_RGB_OBJ_INTERVALS')
    if not next_steps:
        next_steps.append('OBTAIN_INDEPENDENT_VBLANK_TIMING_REFERENCE')

    if not (totals['rgb_change_intervals'] and
            totals['obj_change_intervals'] and
            totals['latch_increment_intervals']):
        status = 'LOW_INFORMATION_FOR_PRIVATE_CAPTURE_TRIAGE'
    elif (totals['obj_change_without_latch_increment_intervals'] or
          totals['latch_increment_without_obj_change_intervals'] or
          not totals['rgb_obj_cochange_intervals']):
        status = 'DIVERGENT_NOMINAL_STREAMS_REQUIRE_INSPECTION'
    else:
        status = 'CO_VARIATION_OBSERVED_WITHOUT_TIMING_PROOF'

    return {
        'status': status,
        'diagnostic_only': True,
        'nominal_frame_count': frame_count,
        'nominal_intervals_checked': span,
        'session_and_file_integrity_checked': True,
        'rgb_change_intervals': totals['rgb_change_intervals'],
        'obj_change_intervals': totals['obj_change_intervals'],
        'latch_increment_intervals': totals['latch_increment_intervals'],
        'rgb_obj_cochange_intervals': totals['rgb_obj_cochange_intervals'],
        'next_local_investigation_codes': next_steps,
        'original_game_authenticity_verified': False,
        'active_gameplay_verified': False,
        'hardware_vblank_observed': False,
        'obj_latch_age_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
