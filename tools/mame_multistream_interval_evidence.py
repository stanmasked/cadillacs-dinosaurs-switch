#!/usr/bin/env python3
"""Compare *nominal* RGB / buffered OBJ / CPS register / latch intervals.

Input is already-validated, metadata-only reports; NO original RGB,
OBJ words, ROM data or game screenshots are returned. Co-changes at a
shared frame label are NOT independent proof of VBlank or frame age.
"""
from tools.mame_reference_activity import PIXELS


def _bounded_series(report, key, count, maximum, *, minimum=0):
    values = report.get(key)
    if (not isinstance(values, (tuple, list)) or len(values) != count or
            any(type(x) is not int or not minimum <= x <= maximum
                for x in values)):
        raise ValueError(f'Invalid {key} observation series')
    return list(values)


def _labels(report, expected):
    values = report.get('nominal_frame_labels')
    if (not isinstance(values, (tuple, list)) or
            list(values) != expected or
            any(type(v) is not int for v in values)):
        raise ValueError('Cross-stream nominal frame labels do not agree')


def multistream_interval_evidence(frame_report, reference_activity,
                                  first_frame, frame_step, frame_count):
    """Validate complete evidence and summarize 4 observational sources.

    Call only after the independent CRC32, FNV V2 and RGB-size gates.
    Do not equate consecutive nominal labels with synchronous callbacks.
    """
    if (type(first_frame) is not int or not 0 <= first_frame <= 99999999 or
            type(frame_step) is not int or not 1 <= frame_step <= 120 or
            type(frame_count) is not int or not 4 <= frame_count <= 24 or
            first_frame + (frame_count - 1) * frame_step > 99999999):
        raise ValueError('Invalid bounded cross-stream frame selection')
    if not isinstance(frame_report, dict) or not isinstance(reference_activity, dict):
        raise ValueError('Cross-stream diagnostics must be dictionaries')

    obj = frame_report.get('obj_buffer_evidence')
    latch = frame_report.get('obj_latch_count_evidence')
    if not isinstance(obj, dict) or not isinstance(latch, dict):
        raise ValueError('OBJ and latch diagnostics are required')
    reports = (frame_report, obj, latch, reference_activity)
    if any(report.get('frame_sync_verified') is not False or
           report.get('pixel_parity_eligible') is not False
           for report in reports):
        raise ValueError('Unverified frame/parity flags must remain explicitly false')
    if any(report.get('diagnostic_only') is not True
           for report in (obj, latch, reference_activity)):
        raise ValueError('Input reports must be diagnostic-only')
    if (latch.get('sidecar_format_version') != 2 or
            latch.get('obj_byte_fingerprint_binding') != 'FNV1A64_ALL_SAMPLES_MATCHED' or
            type(latch.get('obj_byte_fingerprint_verified_count')) is not int or
            latch['obj_byte_fingerprint_verified_count'] != frame_count or
            reference_activity.get('reference_width') != 384 or
            reference_activity.get('reference_height') != 224):
        raise ValueError('Full V2 OBJ binding and RGB dimensions are required')

    frames = [first_frame + i * frame_step for i in range(frame_count)]
    for report in (obj, latch, reference_activity):
        _labels(report, frames)
    if (type(frame_report.get('first_frame')) is not int or
            frame_report['first_frame'] != first_frame or
            type(frame_report.get('sample_count')) is not int or
            frame_report['sample_count'] != frame_count or
            type(frame_report.get('frame_step')) is not int or
            frame_report['frame_step'] != frame_step):
        raise ValueError('Base multiframe report does not match capture labels')

    span = frame_count - 1
    rgb_pixels = _bounded_series(reference_activity,
                                 'changed_pixel_counts_per_interval', span, PIXELS)
    obj_slots = _bounded_series(obj, 'changed_obj_slots_per_interval', span, 256)
    register_words = _bounded_series(obj, 'changed_register_words_per_interval',
                                     span, 64)
    latch_deltas = _bounded_series(latch, 'inter_sample_callback_deltas',
                                   span, (1 << 64) - 1)
    colors = _bounded_series(reference_activity,
                             'exact_unique_rgb_colors_per_frame', frame_count,
                             PIXELS, minimum=1)
    _bounded_series(reference_activity, 'nonblack_pixel_counts_per_frame',
                    frame_count, PIXELS)
    if (type(reference_activity.get('all_black_reference_sequence')) is not bool or
            type(reference_activity.get('static_reference_sequence')) is not bool or
            type(reference_activity.get('all_frames_single_color')) is not bool):
        raise ValueError('Missing conservative RGB classification flags')
    if (reference_activity.get('changed_reference_intervals') !=
            sum(value > 0 for value in rgb_pixels) or
            obj.get('obj_changed_intervals') !=
            sum(value > 0 for value in obj_slots)):
        raise ValueError('Source-specific transition totals disagree')
    if any(report.get('active_gameplay_verified') is not False
           for report in (reference_activity,)):
        raise ValueError('RGB activity must never assert active gameplay')

    intervals = []
    for i in range(span):
        rgb = rgb_pixels[i] > 0
        obj_changed = obj_slots[i] > 0
        latch_observed = latch_deltas[i] > 0
        intervals.append({
            'from_nominal_frame': frames[i],
            'to_nominal_frame': frames[i+1],
            'changed_reference_pixels': rgb_pixels[i],
            'changed_obj_slots': obj_slots[i],
            'changed_register_words': register_words[i],
            'observed_latch_callback_delta': latch_deltas[i],
            'rgb_changed': rgb,
            'obj_changed': obj_changed,
            'latch_count_increased': latch_observed,
            'rgb_and_obj_changed': rgb and obj_changed,
            'obj_changed_without_latch_increment': obj_changed and not latch_observed,
            'latch_increment_without_obj_change': latch_observed and not obj_changed,
        })
    rgb_intervals = sum(i['rgb_changed'] for i in intervals)
    obj_intervals = sum(i['obj_changed'] for i in intervals)
    latch_intervals = sum(i['latch_count_increased'] for i in intervals)
    reasons = []
    if reference_activity['all_black_reference_sequence']:
        reasons.append('ALL_BLACK_REFERENCE')
    elif reference_activity['static_reference_sequence']:
        reasons.append('STATIC_REFERENCE')
    if reference_activity['all_frames_single_color']:
        reasons.append('SINGLE_COLOR_FRAMES')
    if not obj_intervals:
        reasons.append('NO_OBJ_CHANGES_OBSERVED')
    if not latch_intervals:
        reasons.append('NO_LATCH_COUNT_INCREMENTS')
    if any(i['obj_changed_without_latch_increment'] for i in intervals):
        reasons.append('OBJ_CHANGED_WITHOUT_COUNT_INCREMENT')
    if not any(i['rgb_and_obj_changed'] for i in intervals):
        reasons.append('NO_RGB_OBJ_COCHANGES')
    return {
        'status': ('MULTISTREAM_VARIATION_OBSERVED_UNVERIFIED'
                   if rgb_intervals and obj_intervals and latch_intervals
                   else 'LOW_INFORMATION_FOR_MULTISTREAM_STUDY'),
        'diagnostic_only': True,
        'nominal_frame_labels': frames,
        'intervals': intervals,
        'rgb_change_intervals': rgb_intervals,
        'obj_change_intervals': obj_intervals,
        'latch_increment_intervals': latch_intervals,
        'rgb_obj_cochange_intervals': sum(i['rgb_and_obj_changed']
                                         for i in intervals),
        'rgb_obj_latch_cochange_intervals': sum(
            i['rgb_and_obj_changed'] and i['latch_count_increased']
            for i in intervals),
        'obj_change_without_latch_increment_intervals': sum(
            i['obj_changed_without_latch_increment'] for i in intervals),
        'latch_increment_without_obj_change_intervals': sum(
            i['latch_increment_without_obj_change'] for i in intervals),
        'observational_cautions': reasons,
        'original_game_authenticity_verified': False,
        'active_gameplay_verified': False,
        'hardware_vblank_observed': False,
        'obj_latch_age_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
        'warning': (
            'All four streams originate from one instrumented MAME process '
            'with nominal frame labels. Apparent simultaneity is not '
            'independent timing evidence, and no co-change is proof of '
            'original game frame age, gameplay or raster pixel parity.'
        ),
    }
