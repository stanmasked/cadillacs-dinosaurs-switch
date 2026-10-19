"""ROM-free regressions for complete, privacy-safe capture triage."""
import json
import unittest

from test_mame_multistream_interval_evidence import synthetic_metadata
from tools.mame_multistream_interval_evidence import multistream_interval_evidence
from tools.mame_private_capture_triage import private_capture_triage
from tools.mame_private_interval_consistency import private_nominal_interval_consistency


def inputs(*, obj_slots=None, latch_deltas=None, rgb_pixels=None,
           unique_colors=None, nonblack=None):
    base, rgb = synthetic_metadata()
    obj = base['obj_buffer_evidence']
    latch = base['obj_latch_count_evidence']
    if obj_slots is not None:
        obj['changed_obj_slots_per_interval'] = list(obj_slots)
    if latch_deltas is not None:
        latch['inter_sample_callback_deltas'] = list(latch_deltas)
    if rgb_pixels is not None:
        rgb['changed_pixel_counts_per_interval'] = list(rgb_pixels)
    if unique_colors is not None:
        rgb['exact_unique_rgb_colors_per_frame'] = list(unique_colors)
    if nonblack is not None:
        rgb['nonblack_pixel_counts_per_frame'] = list(nonblack)
    rgb['changed_reference_intervals'] = sum(
        x > 0 for x in rgb['changed_pixel_counts_per_interval'])
    rgb['static_reference_sequence'] = rgb['changed_reference_intervals'] == 0
    rgb['all_black_reference_sequence'] = all(
        value == 0 for value in rgb['nonblack_pixel_counts_per_frame'])
    rgb['all_frames_single_color'] = all(
        value == 1 for value in rgb['exact_unique_rgb_colors_per_frame'])
    obj['obj_changed_intervals'] = sum(
        value > 0 for value in obj['changed_obj_slots_per_interval'])
    deltas = latch['inter_sample_callback_deltas']
    counts = [10]
    for delta in deltas:
        counts.append(counts[-1] + delta)
    labels = [900, 902, 904, 906, 908, 910]
    latch.update({
        'observed_latch_callback_counts': counts,
        'zero_callback_delta_frames': [
            labels[i+1] for i, delta in enumerate(deltas) if delta == 0],
        'multiple_callback_delta_frames': [
            labels[i+1] for i, delta in enumerate(deltas) if delta > 1],
        'obj_changed_without_observed_latch_frames': [
            labels[i+1] for i, (delta, changed) in enumerate(
                zip(deltas, obj['changed_obj_slots_per_interval']))
            if delta == 0 and changed > 0],
        'capture_session_tagged_samples': 6,
        'capture_session_label_consistent': True,
    })
    combined = multistream_interval_evidence(base, rgb, 900, 2, 6)
    return (
        rgb,
        combined,
        {
            'status': 'SAME_LAUNCHER_SESSION_LABEL_OBSERVED',
            'diagnostic_only': True,
            'shared_session_label_consistent': True,
            'lua_manifest_session_samples': 6,
            'cpp_latch_session_samples': 6,
            'label_is_authenticated_game_provenance': False,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        },
        private_nominal_interval_consistency(base, combined),
        {
            'source_files_checked': 54,
            'source_files_unchanged_during_audit': True,
            'hash_algorithm': 'SHA256_LOCAL_ONLY_NO_DIGESTS_PUBLISHED',
            'diagnostic_only': True,
            'frame_sync_verified': False,
            'pixel_parity_eligible': False,
        },
    )


class PrivateCaptureTriageTests(unittest.TestCase):
    def test_divergent_streams_have_local_guidance_not_vblank_proof(self):
        out = private_capture_triage(*inputs())
        self.assertEqual(out['status'], 'DIVERGENT_NOMINAL_STREAMS_REQUIRE_INSPECTION')
        self.assertEqual(out['rgb_change_intervals'], 3)
        self.assertEqual(out['obj_change_intervals'], 3)
        self.assertEqual(out['latch_increment_intervals'], 3)
        self.assertIn('INVESTIGATE_OBJ_CHANGES_WITHOUT_LATCH_INCREMENTS',
                      out['next_local_investigation_codes'])
        self.assertFalse(out['frame_sync_verified'])

    def test_clean_co_variation_remains_unverified(self):
        reports = inputs(obj_slots=[1, 2, 3, 0, 0],
                         latch_deltas=[1, 1, 1, 0, 0],
                         rgb_pixels=[10, 12, 2, 0, 0])
        out = private_capture_triage(*reports)
        self.assertEqual(out['status'], 'CO_VARIATION_OBSERVED_WITHOUT_TIMING_PROOF')
        self.assertEqual(out['next_local_investigation_codes'],
                         ['OBTAIN_INDEPENDENT_VBLANK_TIMING_REFERENCE'])
        self.assertFalse(out['hardware_vblank_observed'])

    def test_low_information_and_single_color_do_not_imply_gameplay(self):
        reports = inputs(obj_slots=[0] * 5, unique_colors=[1] * 6)
        out = private_capture_triage(*reports)
        self.assertEqual(out['status'], 'LOW_INFORMATION_FOR_PRIVATE_CAPTURE_TRIAGE')
        self.assertIn('INSPECT_PRIVATE_SINGLE_COLOR_FRAMES',
                      out['next_local_investigation_codes'])
        self.assertIn('INSPECT_PRIVATE_OBJ_ACTIVITY',
                      out['next_local_investigation_codes'])
        self.assertFalse(out['active_gameplay_verified'])

    def test_all_black_static_reference_suggests_private_inspection(self):
        reports = inputs(rgb_pixels=[0] * 5, unique_colors=[1] * 6,
                         nonblack=[0] * 6)
        out = private_capture_triage(*reports)
        self.assertEqual(out['rgb_change_intervals'], 0)
        self.assertIn('CHECK_PRIVATE_VIDEO_CAPTURE_BLACK_FRAMES',
                      out['next_local_investigation_codes'])

    def test_missing_session_stability_or_counter_gate_fails_closed(self):
        patches = ((2, 'shared_session_label_consistent', False),
                   (2, 'lua_manifest_session_samples', 5),
                   (2, 'label_is_authenticated_game_provenance', True),
                   (3, 'cumulative_latch_deltas_match', False),
                   (3, 'status', 'UNVERIFIED'),
                   (4, 'source_files_checked', 53),
                   (4, 'source_files_unchanged_during_audit', False))
        for i, key, val in patches:
            reports = list(inputs())
            reports[i] = dict(reports[i], **{key: val})
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'integrity gates'):
                    private_capture_triage(*reports)

    def test_forged_aggregate_totals_cannot_change_recommendation(self):
        for key in ('rgb_change_intervals', 'obj_change_intervals',
                    'latch_increment_intervals', 'rgb_obj_cochange_intervals',
                    'rgb_obj_latch_cochange_intervals',
                    'obj_change_without_latch_increment_intervals',
                    'latch_increment_without_obj_change_intervals'):
            reports = list(inputs())
            reports[1][key] = 0 if reports[1][key] else 1
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'detailed interval totals'):
                    private_capture_triage(*reports)

    def test_forged_per_interval_booleans_and_counts_fail_closed(self):
        for key in ('changed_reference_pixels', 'rgb_changed', 'obj_changed',
                    'latch_count_increased', 'rgb_and_obj_changed',
                    'obj_changed_without_latch_increment',
                    'latch_increment_without_obj_change',
                    'from_nominal_frame', 'to_nominal_frame'):
            reports = list(inputs())
            row = reports[1]['intervals'][0]
            old = row[key]
            row[key] = not old if type(old) is bool else old + 1
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'detailed interval'):
                    private_capture_triage(*reports)

    def test_missing_rows_invalid_values_and_nominal_labels_fail_closed(self):
        for mutation in ('missing', 'bad_obj', 'bad_delta', 'bad_frame'):
            reports = list(inputs())
            if mutation == 'missing':
                reports[1]['intervals'].pop()
            elif mutation == 'bad_obj':
                reports[1]['intervals'][0]['changed_obj_slots'] = 257
            elif mutation == 'bad_delta':
                reports[1]['intervals'][0]['observed_latch_callback_delta'] = True
            else:
                reports[1]['nominal_frame_labels'][4] = 907
            with self.subTest(mutation=mutation):
                with self.assertRaisesRegex(ValueError, 'interval|labels'):
                    private_capture_triage(*reports)

    def test_rgb_pixel_color_and_nonblack_source_must_agree(self):
        changes = (
            ('changed_pixel_counts_per_interval', [0] * 5),
            ('exact_unique_rgb_colors_per_frame', [1] * 6),
            ('nonblack_pixel_counts_per_frame', [0] * 6),
            ('reference_width', 385),
        )
        for field, value in changes:
            reports = list(inputs())
            reports[0][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, 'RGB|interval'):
                    private_capture_triage(*reports)

    def test_rgb_classifications_and_reported_totals_fail_closed(self):
        for key, val in (
            ('all_black_reference_sequence', True),
            ('static_reference_sequence', True),
            ('all_frames_single_color', True),
            ('changed_reference_intervals', 2),
        ):
            reports = list(inputs())
            reports[0][key] = val
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'RGB classifications'):
                    private_capture_triage(*reports)
        reports = list(inputs())
        reports[1]['pixel_parity_eligible'] = True
        with self.assertRaisesRegex(ValueError, 'conservative'):
            private_capture_triage(*reports)

    def test_forged_counter_consistency_summary_fails_closed(self):
        for key in ('zero_callback_intervals', 'multiple_callback_intervals',
                    'obj_change_without_callback_intervals'):
            reports = list(inputs())
            reports[3][key] += 1
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, 'counter summary'):
                    private_capture_triage(*reports)

    def test_no_private_input_values_are_copied_to_output(self):
        reports = list(inputs())
        reports[0]['private_file_path'] = '/secret/roms/dino.zip'
        reports[1]['warning'] = 'PRIVATE_RGB_BYTES'
        reports[2]['capture_session'] = 'a' * 32
        reports[3]['original_sha256'] = 'b' * 64
        out = private_capture_triage(*reports)
        encoded = json.dumps(out)
        for secret in ('/secret/roms', 'PRIVATE_RGB_BYTES', 'a' * 32, 'b' * 64):
            self.assertNotIn(secret, encoded)
        self.assertTrue(out['diagnostic_only'])
        self.assertFalse(out['pixel_parity_eligible'])

    def test_rejects_bad_frame_count_and_missing_reports(self):
        for count in (True, 3, 25):
            with self.subTest(count=count):
                with self.assertRaisesRegex(ValueError, 'frame count'):
                    private_capture_triage(*inputs(), frame_count=count)
        reports = list(inputs())
        reports[4] = None
        with self.assertRaisesRegex(ValueError, 'five complete reports'):
            private_capture_triage(*reports)


if __name__ == '__main__':
    unittest.main()
