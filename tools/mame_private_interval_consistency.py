#!/usr/bin/env python3
"""Fail closed on contradictory nominal six-frame private MAME metadata.

This is a second-pass check on already validated, same-process observations.
No original ROM/RGB/OBJ bytes, session token or local paths are read or emitted.
Numerically consistent metadata is NOT VBlank, gameplay or pixel parity proof.
"""

MAX_U64 = (1 << 64) - 1


def _series(report, key, count, upper):
    values = report.get(key)
    if (not isinstance(values, (list, tuple)) or len(values) != count or
            any(type(value) is not int or not 0 <= value <= upper
                for value in values)):
        raise ValueError('Private latch interval metadata has invalid numeric series')
    return list(values)


def private_nominal_interval_consistency(frame_report, interval_report,
                                         first_frame=900, frame_step=2,
                                         frame_count=6):
    """Cross-check cumulative latch counts, derived deltas and OBJ intervals.

    Run only *after* the original CRC32, V2/FNV, RGB, and session-label gates.
    This validates the internal report, not real physical callback timing.
    """
    if (type(first_frame) is not int or not 0 <= first_frame <= 99999999 or
            type(frame_step) is not int or not 1 <= frame_step <= 120 or
            type(frame_count) is not int or not 4 <= frame_count <= 24 or
            first_frame + (frame_count - 1) * frame_step > 99999999):
        raise ValueError('Private latch interval bounds are invalid')
    if not isinstance(frame_report, dict) or not isinstance(interval_report, dict):
        raise ValueError('Private latch interval reports are invalid')
    obj = frame_report.get('obj_buffer_evidence')
    latch = frame_report.get('obj_latch_count_evidence')
    if not isinstance(obj, dict) or not isinstance(latch, dict):
        raise ValueError('Private latch interval sources are incomplete')

    frames = [first_frame + i * frame_step for i in range(frame_count)]
    if any(report.get('nominal_frame_labels') != frames
           for report in (obj, latch, interval_report)):
        raise ValueError('Private latch interval frame labels disagree')
    if (latch.get('sidecar_format_version') != 2 or
            latch.get('obj_byte_fingerprint_binding') != 'FNV1A64_ALL_SAMPLES_MATCHED' or
            latch.get('obj_byte_fingerprint_verified_count') != frame_count or
            latch.get('capture_session_tagged_samples') != frame_count or
            latch.get('capture_session_label_consistent') is not True):
        raise ValueError('Private latch intervals require complete V2 session binding')
    if any(report.get('frame_sync_verified') is not False or
           report.get('pixel_parity_eligible') is not False
           for report in (frame_report, obj, latch, interval_report)):
        raise ValueError('Private latch interval parity claims must remain false')
    if any(report.get('diagnostic_only') is not True
           for report in (obj, latch, interval_report)):
        raise ValueError('Private latch interval provenance must be diagnostic-only')

    count = frame_count - 1
    counts = _series(latch, 'observed_latch_callback_counts', frame_count, MAX_U64)
    deltas = _series(latch, 'inter_sample_callback_deltas', count, MAX_U64)
    changed = _series(obj, 'changed_obj_slots_per_interval', count, 256)
    words = _series(obj, 'changed_register_words_per_interval', count, 64)
    if deltas != [after - before for before, after in zip(counts, counts[1:])]:
        raise ValueError('Private latch cumulative counts and interval deltas disagree')

    expected_zero = [frames[i+1] for i, delta in enumerate(deltas) if delta == 0]
    expected_multi = [frames[i+1] for i, delta in enumerate(deltas) if delta > 1]
    expected_obj_without = [
        frames[i+1] for i, (delta, slots) in enumerate(zip(deltas, changed))
        if delta == 0 and slots > 0]
    for field, expected in (
        ('zero_callback_delta_frames', expected_zero),
        ('multiple_callback_delta_frames', expected_multi),
        ('obj_changed_without_observed_latch_frames', expected_obj_without),
    ):
        values = latch.get(field)
        if (not isinstance(values, (list, tuple)) or
                list(values) != expected or
                any(type(value) is not int for value in values)):
            raise ValueError('Private latch annotated frame intervals disagree')

    intervals = interval_report.get('intervals')
    if not isinstance(intervals, (list, tuple)) or len(intervals) != count:
        raise ValueError('Private combined interval count is invalid')
    rgb_count = obj_count = latch_count = rgb_obj_count = rgb_obj_latch_count = 0
    for i, item in enumerate(intervals):
        if not isinstance(item, dict):
            raise ValueError('Private combined interval entry is invalid')
        pixels = item.get('changed_reference_pixels')
        if type(pixels) is not int or not 0 <= pixels <= 384 * 224:
            raise ValueError('Private combined RGB interval count is invalid')
        rgb = pixels > 0
        obj_change = changed[i] > 0
        callback = deltas[i] > 0
        expected = {
            'from_nominal_frame': frames[i],
            'to_nominal_frame': frames[i+1],
            'changed_obj_slots': changed[i],
            'changed_register_words': words[i],
            'observed_latch_callback_delta': deltas[i],
            'rgb_changed': rgb,
            'obj_changed': obj_change,
            'latch_count_increased': callback,
            'rgb_and_obj_changed': rgb and obj_change,
            'obj_changed_without_latch_increment': obj_change and not callback,
            'latch_increment_without_obj_change': callback and not obj_change,
        }
        for key, expected_value in expected.items():
            if type(item.get(key)) is not type(expected_value) or item[key] != expected_value:
                raise ValueError('Private combined interval observations disagree')
        rgb_count += rgb
        obj_count += obj_change
        latch_count += callback
        rgb_obj_count += rgb and obj_change
        rgb_obj_latch_count += rgb and obj_change and callback

    totals = {
        'rgb_change_intervals': rgb_count,
        'obj_change_intervals': obj_count,
        'latch_increment_intervals': latch_count,
        'rgb_obj_cochange_intervals': rgb_obj_count,
        'rgb_obj_latch_cochange_intervals': rgb_obj_latch_count,
        'obj_change_without_latch_increment_intervals': len(expected_obj_without),
        'latch_increment_without_obj_change_intervals': sum(
            delta > 0 and slots == 0 for delta, slots in zip(deltas, changed)),
    }
    if any(type(interval_report.get(key)) is not int or
           interval_report[key] != value for key, value in totals.items()):
        raise ValueError('Private combined interval totals disagree')

    return {
        'status': 'PRIVATE_NOMINAL_COUNTER_CONSISTENCY_ONLY',
        'diagnostic_only': True,
        'nominal_frame_samples_checked': frame_count,
        'nominal_intervals_checked': count,
        'cumulative_latch_deltas_match': True,
        'source_interval_annotations_match': True,
        'cross_stream_interval_fields_match': True,
        'zero_callback_intervals': len(expected_zero),
        'multiple_callback_intervals': len(expected_multi),
        'obj_change_without_callback_intervals': len(expected_obj_without),
        'original_game_authenticity_verified': False,
        'active_gameplay_verified': False,
        'hardware_vblank_observed': False,
        'obj_latch_age_verified': False,
        'frame_sync_verified': False,
        'pixel_parity_eligible': False,
    }
