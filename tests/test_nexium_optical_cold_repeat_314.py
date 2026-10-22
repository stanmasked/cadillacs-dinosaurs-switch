"""Stage314 comparator mutation tests: generated JSON is NOT guest evidence."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools import verify_nexium_optical_cold_repeat_314 as checker


def mock_success(min_points=24):
    return {
        "schema": checker.STAGE313_SCHEMA,
        "status": checker.STAGE313_PASS,
        "synthetic_guest_and_host_frames_bound": 14,
        "host_optical_frame_identity_all_14": True,
        "host_visible_scene_pixels_verified": True,
        "native_guest_reference_scene_parity": True,
        "host_scene_pixel_sample_min_matched": min_points,
        "original_rom_or_gameplay_used": False,
        "original_gameplay_frame_display_verified": False,
        "physical_switch_display_verified": False,
        "private_host_screenshots_uploaded": False,
        "host_gpu_scanout_timing_verified": False,
    }


class Stage314ColdBootComparatorTests(unittest.TestCase):
    def setUp(self):
        self.private = tempfile.TemporaryDirectory(prefix="stage314-mock-")
        self.addCleanup(self.private.cleanup)
        self.root = Path(self.private.name)
        self.a = self.root / "boot-a.json"
        self.b = self.root / "boot-b.json"
        self.write(self.a, mock_success())
        self.write(self.b, mock_success(23))

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    def test_good_mock_only_tests_schema_contract(self):
        # Synthetic summary tests never establish a real guest boot.
        outcome=checker.compare(self.a, self.b)
        self.assertEqual(outcome["status"], checker.PASS)
        self.assertEqual(outcome["minimum_matched_host_scene_pixels_across_both_runs"],23)
        self.assertEqual(outcome["independently_started_isolated_guest_jobs"],2)
        self.assertFalse(outcome["physical_switch_display_verified"])

    def test_missing_second_boot_blocks_entire_pair(self):
        self.b.unlink()
        with self.assertRaises(ValueError):
            checker.compare(self.a,self.b)

    def test_same_file_cannot_count_as_two_cold_boots(self):
        with self.assertRaises(ValueError):
            checker.compare(self.a,self.a)

    def test_bad_fields_fail_closed_for_either_boot(self):
        mutations = {
            "status": checker.BLOCKED,
            "schema": "mock",
            "synthetic_guest_and_host_frames_bound": 13,
            "host_optical_frame_identity_all_14": False,
            "host_visible_scene_pixels_verified": False,
            "native_guest_reference_scene_parity": False,
            "host_scene_pixel_sample_min_matched": 9,
            "original_rom_or_gameplay_used": True,
            "original_gameplay_frame_display_verified": True,
            "physical_switch_display_verified": True,
            "private_host_screenshots_uploaded": True,
            "host_gpu_scanout_timing_verified": True,
        }
        for file in (self.a,self.b):
            for key,value in mutations.items():
                with self.subTest(file=file.name,key=key):
                    original=mock_success() if file==self.a else mock_success(23)
                    original[key]=value
                    self.write(file,original)
                    with self.assertRaises(ValueError):
                        checker.compare(self.a,self.b)
                    self.write(file,mock_success() if file==self.a else mock_success(23))

    def test_reject_boolean_in_integer_field_and_missing_fields(self):
        for bad in (True, 100, -1, None, 1.5):
            doc=mock_success()
            doc["host_scene_pixel_sample_min_matched"]=bad
            self.write(self.a,doc)
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                checker.compare(self.a,self.b)
        self.write(self.a,mock_success())
        bad=mock_success()
        del bad["native_guest_reference_scene_parity"]
        self.write(self.b,bad)
        with self.assertRaises(ValueError):
            checker.compare(self.a,self.b)

    def test_refuse_symlink_and_non_json_evidence(self):
        self.b.unlink()
        self.b.symlink_to(self.a)
        with self.assertRaises(ValueError):
            checker.compare(self.a,self.b)
        self.b.unlink()
        self.b.write_text("{malformed")
        with self.assertRaises(json.JSONDecodeError):
            checker.compare(self.a,self.b)

    def test_cli_blocked_summary_only_does_not_expose_paths(self):
        out=self.root/"combined.json"
        self.b.unlink()
        with contextlib.redirect_stdout(io.StringIO()):
            rc=checker.main(["--boot-a",str(self.a),"--boot-b",str(self.b),
                             "--out",str(out)])
        self.assertEqual(rc,2)
        s=out.read_text()
        self.assertNotIn(str(self.root),s)
        record=json.loads(s)
        self.assertEqual(record["status"],checker.BLOCKED)
        self.assertFalse(record["host_visible_synthetic_scenes_reproduced"])


if __name__=="__main__":
    unittest.main()
