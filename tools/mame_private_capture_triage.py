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




def _vector(report, key, count, maximum, minimum=0):
    values = report.get(key)
    if (not isinstance(values, (list, tuple)) or len(values) != count or
            any(type(v) is not int or not minimum <= v <= maximum
                for v in values)):
        raise ValueError('Private triage source interval series are invalid')
    return list(values)


def _reconcile_intervals(reference_activity, report, consistency, frame_count):
    """Derive every aggregate from detailed rows; never trust copied totals."""
    span = frame_count - 1
    labels = report.get('nominal_frame_labels')
    if (not isinstance(labels, (list, tuple)) or len(labels) != frame_count or
            any(type(v) is not int or not 0 <= v <= 99999999 for v in labels)):
        raise ValueError('Private triage nominal frame labels are invalid')
    step = labels[1] - labels[0]
    if (not 1 <= step <= 120 or
            list(labels) != [labels[0] + i * step for i in range(frame_count)] or
            reference_activity.get('nominal_frame_labels') != list(labels)):
        raise ValueError('Private triage nominal frame labels disagree')

    if (reference_activity.get('reference_width') != 384 or
            reference_activity.get('reference_height') != 224):
        raise ValueError('Private triage RGB dimensions disagree')
    pixels_per_interval = _vector(reference_activity,
                                  'changed_pixel_counts_per_interval',
                                  span, 384 * 224)
    unique_colors = _vector(reference_activity,
                            'exact_unique_rgb_colors_per_frame',
                            frame_count, 384 * 224, 1)
    nonblack = _vector(reference_activity, 'nonblack_pixel_counts_per_frame',
                       frame_count, 384 * 224)
    rows = report.get('intervals')
    if not isinstance(rows, (list, tuple)) or len(rows) != span:
        raise ValueError('Private triage detailed intervals are missing')

    totals = {key: 0 for key in (
        'rgb_change_intervals', 'obj_change_intervals',
        'latch_increment_intervals', 'rgb_obj_cochange_intervals',
        'rgb_obj_latch_cochange_intervals',
        'obj_change_without_latch_increment_intervals',
        'latch_increment_without_obj_change_intervals',
    )}
    zero_delta = multiple_delta = obj_without = 0
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError('Private triage detailed interval is invalid')
        obj = row.get('changed_obj_slots')
        words = row.get('changed_register_words')
        delta = row.get('observed_latch_callback_delta')
        if (type(obj) is not int or not 0 <= obj <= 256 or
                type(words) is not int or not 0 <= words <= 64 or
                type(delta) is not int or not 0 <= delta <= (1 << 64) - 1):
            raise ValueError('Private triage detailed interval values are invalid')
        rgb = pixels_per_interval[i] > 0
        changed = obj > 0
        latch = delta > 0
        expected = {
            'from_nominal_frame': labels[i],
            'to_nominal_frame': labels[i+1],
            'changed_reference_pixels': pixels_per_interval[i],
            'rgb_changed': rgb,
            'obj_changed': changed,
            'latch_count_increased': latch,
            'rgb_and_obj_changed': rgb and changed,
            'obj_changed_without_latch_increment': changed and not latch,
            'latch_increment_without_obj_change': latch and not changed,
        }
        if any(type(row.get(key)) is not type(value) or row[key] != value
               for key, value in expected.items()):
            raise ValueError('Private triage detailed interval observations disagree')
        totals['rgb_change_intervals'] += rgb
        totals['obj_change_intervals'] += changed
        totals['latch_increment_intervals'] += latch
        totals['rgb_obj_cochange_intervals'] += rgb and changed
        totals['rgb_obj_latch_cochange_intervals'] += rgb and changed and latch
        totals['obj_change_without_latch_increment_intervals'] += changed and not latch
        totals['latch_increment_without_obj_change_intervals'] += latch and not changed
        zero_delta += delta == 0
        multiple_delta += delta > 1
        obj_without += changed and not latch

    if any(_number(report, key, span) != value
           for key, value in totals.items()):
        raise ValueError('Private triage detailed interval totals disagree')
    for key, expected in (
        ('zero_callback_intervals', zero_delta),
        ('multiple_callback_intervals', multiple_delta),
        ('obj_change_without_callback_intervals', obj_without),
    ):
        if type(consistency.get(key)) is not int or consistency[key] != expected:
            raise ValueError('Private triage cumulative counter summary disagrees')

    # Never trust summary labels or colors without their actual numeric data.
    if (reference_activity.get('changed_reference_intervals') !=
            totals['rgb_change_intervals'] or
            reference_activity.get('static_reference_sequence') is not
            (totals['rgb_change_intervals'] == 0) or
            reference_activity.get('all_black_reference_sequence') is not
            all(value == 0 for value in nonblack) or
            reference_activity.get('all_frames_single_color') is not
            all(value == 1 for value in unique_colors)):
        raise ValueError('Private triage RGB classifications disagree')
    return totals

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
    totals = _reconcile_intervals(
        reference_activity, intervals, consistency, frame_count)

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
