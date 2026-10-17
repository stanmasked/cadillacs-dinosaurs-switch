"""ROM-free, privacy-safe private capture interpretation regressions."""
import copy
import json
import unittest

from test_mame_multistream_interval_evidence import synthetic_metadata
from test_mame_private_interval_consistency import fixture
from tools.mame_private_capture_triage import private_capture_triage
from tools.mame_private_interval_consistency import private_nominal_interval_consistency


def inputs():
    base, combined = fixture()
    _, rgb = synthetic_metadata()
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
    def test_divergent_synthetic_streams_have_local_guidance_not_vblank_proof(self):
        output = private_capture_triage(*inputs())
        self.assertEqual(output['status'],
                         'DIVERGENT_NOMINAL_STREAMS_REQUIRE_INSPECTION')
        self.assertEqual(output['rgb_change_intervals'], 3)
        self.assertEqual(output['obj_change_intervals'], 3)
        self.assertEqual(output['latch_increment_intervals'], 3)
        self.assertIn('INVESTIGATE_OBJ_CHANGES_WITHOUT_LATCH_INCREMENTS',
                      output['next_local_investigation_codes'])
        self.assertFalse(output['frame_sync_verified'])
        self.assertFalse(output['active_gameplay_verified'])

    def test_clean_co_variation_is_only_nominal_observation(self):
        reports = list(inputs())
        reports[1] = dict(reports[1],
                          obj_change_without_latch_increment_intervals=0,
                          latch_increment_without_obj_change_intervals=0,
                          rgb_obj_cochange_intervals=3)
        # Coherent metadata is supplied only for triage; the VBlank and
        # original gameplay conclusions must still remain explicitly false.
        output = private_capture_triage(*reports)
        self.assertEqual(output['status'],
                         'CO_VARIATION_OBSERVED_WITHOUT_TIMING_PROOF')
        self.assertEqual(output['next_local_investigation_codes'],
                         ['OBTAIN_INDEPENDENT_VBLANK_TIMING_REFERENCE'])
        self.assertFalse(output['hardware_vblank_observed'])

    def test_low_information_and_single_color_are_not_gameplay(self):
        reports = list(inputs())
        reports[0] = dict(reports[0], all_frames_single_color=True)
        reports[1] = dict(reports[1], obj_change_intervals=0)
        output = private_capture_triage(*reports)
        self.assertEqual(output['status'], 'LOW_INFORMATION_FOR_PRIVATE_CAPTURE_TRIAGE')
        self.assertIn('INSPECT_PRIVATE_SINGLE_COLOR_FRAMES',
                      output['next_local_investigation_codes'])
        self.assertIn('INSPECT_PRIVATE_OBJ_ACTIVITY',
                      output['next_local_investigation_codes'])
        self.assertFalse(output['active_gameplay_verified'])

    def test_all_black_no_rgb_changes_suggests_private_video_inspection(self):
        reports = list(inputs())
        reports[0] = dict(reports[0], all_black_reference_sequence=True,
                          static_reference_sequence=True,
                          all_frames_single_color=True,
                          changed_reference_intervals=0)
        reports[1] = dict(reports[1], rgb_change_intervals=0,
                          rgb_obj_cochange_intervals=0)
        output = private_capture_triage(*reports)
        self.assertIn('CHECK_PRIVATE_VIDEO_CAPTURE_BLACK_FRAMES',
                      output['next_local_investigation_codes'])
        self.assertEqual(output['rgb_change_intervals'], 0)

    def test_fail_closed_if_session_stability_or_consistency_is_missing(self):
        patches = (
            (2, 'shared_session_label_consistent', False),
            (2, 'lua_manifest_session_samples', 5),
            (2, 'label_is_authenticated_game_provenance', True),
            (3, 'cumulative_latch_deltas_match', False),
            (3, 'status', 'UNVERIFIED'),
            (4, 'source_files_checked', 53),
            (4, 'source_files_unchanged_during_audit', False),
        )
        for index, key, value in patches:
            reports = list(inputs())
            reports[index] = dict(reports[index], **{key: value})
            with self.subTest(field=key):
                with self.assertRaisesRegex(ValueError, 'integrity gates'):
                    private_capture_triage(*reports)

    def test_fail_closed_on_bad_totals_parity_and_rgb_classifications(self):
        reports = list(inputs())
        reports[1] = dict(reports[1], rgb_change_intervals=True)
        with self.assertRaisesRegex(ValueError, 'totals'):
            private_capture_triage(*reports)
        reports = list(inputs())
        reports[0] = dict(reports[0], static_reference_sequence=True)
        with self.assertRaisesRegex(ValueError, 'static RGB'):
            private_capture_triage(*reports)
        reports = list(inputs())
        reports[1] = dict(reports[1], pixel_parity_eligible=True)
        with self.assertRaisesRegex(ValueError, 'conservative'):
            private_capture_triage(*reports)
        reports = list(inputs())
        reports[0] = dict(reports[0], changed_reference_intervals=1)
        with self.assertRaisesRegex(ValueError, 'RGB totals'):
            private_capture_triage(*reports)

    def test_no_private_sources_or_untrusted_messages_copied(self):
        reports = list(inputs())
        reports[0]['private_file_path'] = '/secret/roms/dino.zip'
        reports[1]['warning'] = 'PRIVATE_RGB_BYTES'
        reports[2]['capture_session'] = 'a' * 32
        reports[3]['original_sha256'] = 'b' * 64
        output = private_capture_triage(*reports)
        encoded = json.dumps(output)
        for secret in ('/secret/roms', 'PRIVATE_RGB_BYTES', 'a' * 32, 'b' * 64):
            self.assertNotIn(secret, encoded)
        self.assertTrue(output['diagnostic_only'])
        self.assertFalse(output['pixel_parity_eligible'])

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
