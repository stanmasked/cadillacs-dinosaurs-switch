"""Stage312 synthetic-only checker tests; never claim a constructed log is real."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools import verify_nexium_synthetic_scene_guest_312 as checker
from tools import cps1_synthetic_gfx_fixture_308 as gfx
from tools import cps1_private_scene_compositor_parity as scenes
from tools import cps1_frame


class Stage312SceneGuestWitnessValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        graphics, _ = gfx.build()
        data = [checker.HEADER]
        for i, name in enumerate(scenes.CASES):
            snapshot = scenes.synthetic_scene(name)
            reference = cps1_frame.render_frame(
                graphics,[tuple(x) for x in snapshot["palette_rgb"]],snapshot)
            scene_hash = checker.fnv64(reference)
            # Arbitrary test-only screen sample! This NEVER means a
            # fake local witness proves emulator execution.
            screen_hash = 0x6100000000000000 + i
            data.append("FRAME_SUBMITTED,{},{:016X},{:016X}".format(
                i,scene_hash,screen_hash))
        cls.local_mock_trace = data

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stage312-mock-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_parser_reference_consistency_not_guest_provenance(self):
        result = checker.validate_text("\n".join(self.local_mock_trace)+"\n")
        self.assertEqual(result["native_guest_scene_hashes_matched_independent_python"],14)
        self.assertFalse(result["host_visible_display_capture_verified"])
        self.assertFalse(result["physical_nintendo_switch_execution_verified"])
        self.assertFalse(result["original_cps1_frame_capture_verified"])

    def test_reject_incomplete_or_duplicate_scene(self):
        for source in (
                "\n".join(self.local_mock_trace[:-1]),
                "\n".join(self.local_mock_trace+[self.local_mock_trace[-1]]),
                "\n".join(self.local_mock_trace[:2] +
                          self.local_mock_trace[1:14])):
            with self.subTest(case=len(source)):
                with self.assertRaises(ValueError):
                    checker.validate_text(source)

    def test_guest_scene_checksum_poison_is_rejected(self):
        broken = self.local_mock_trace.copy()
        cols = broken[3].split(",")
        cols[2] = "0000000000000000"
        broken[3] = ",".join(cols)
        with self.assertRaises(ValueError):
            checker.validate_text("\n".join(broken))

    def test_empty_screen_or_inert_frames_fail(self):
        broken = self.local_mock_trace.copy()
        cols = broken[8].split(",")
        cols[3] = "0000000000000000"
        broken[8] = ",".join(cols)
        with self.assertRaises(ValueError):
            checker.validate_text("\n".join(broken))
        flattened = []
        for row in self.local_mock_trace[1:]:
            cols = row.split(",")
            cols[3] = "F000000000000000"
            flattened.append(",".join(cols))
        with self.assertRaises(ValueError):
            checker.validate_text("\n".join([checker.HEADER]+flattened))

    def test_out_of_order_or_unknown_events_are_rejected(self):
        for wrong in ("FRAME_SUBMITTED,14,", "FAKE_SUBMITTED,0,"):
            broken = self.local_mock_trace.copy()
            broken[1] = wrong + broken[1].split(",", 2)[2]
            with self.subTest(wrong=wrong):
                with self.assertRaises(ValueError):
                    checker.validate_text("\n".join(broken))

    def test_no_guest_file_fails_with_minimal_bounded_summary(self):
        missing = self.root / "never-created-by-any-emulator.csv"
        out = self.root / "status.json"
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            rc = checker.main(["--guest-trace",str(missing),
                               "--summary",str(out)])
        self.assertEqual(rc,2)
        self.assertIn(checker.BLOCKED,stream.getvalue())
        record = json.loads(out.read_text())
        self.assertNotIn(str(self.root),out.read_text())
        self.assertFalse(record["complete_sequence_verified"])

    def test_symlink_guest_evidence_is_refused(self):
        real = self.root / "possible-witness.csv"
        real.write_text("\n".join(self.local_mock_trace)+"\n")
        link = self.root / "witness-link.csv"
        link.symlink_to(real)
        result = self.root / "status.json"
        rc = checker.main(["--guest-trace",str(link),"--summary",str(result)])
        self.assertEqual(rc,2)
        self.assertEqual(json.loads(result.read_text())["status"],checker.BLOCKED)


if __name__ == "__main__":
    unittest.main()
