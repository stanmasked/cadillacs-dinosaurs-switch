"""Stage292 synthetic-only private experiment tests: no original ROM/INP/WLF."""
import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import wolfmame0106_private_two_window_experiment as experiment
from tools import wolfmame0106_private_mng_audit as mng
from tools import wolfmame0106_private_mng_capture as capture
from tools import wolfmame0106_private_dual_trace_consistency as dual


def chunk(tag, body=b""):
    return (struct.pack(">I", len(body)) + tag + body +
            struct.pack(">I", zlib.crc32(tag + body) & 0xffffffff))


def make_synthetic_mng(start, n, *, tamper_at=None):
    header = struct.pack(">7I", 2, 2, 60, 0, 0, 0, 0x41)
    frames = []
    for i in range(start, start + n):
        color = ((i % 251), ((i * 3) % 253), ((i * 7) % 239))
        if i == tamper_at:
            color = (255, 255, 255)
        scanlines = (b"\x00" + bytes(color) * 2) * 2
        png = (mng.png.PNG_SIG +
               chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) +
               chunk(b"IDAT", zlib.compress(scanlines)) +
               chunk(b"IEND"))
        frames.append(png[len(mng.png.PNG_SIG):])
    return mng.MNG_SIGNATURE + chunk(b"MHDR", header) + b"".join(frames) + chunk(b"MEND")


class TwoWindowPrivateExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dino292-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.destination = self.root / "fresh-capture-folder"
        self.calls = []
        self.fail_start = None
        self.tamper_pixel = False
        self.tamper_counter = False

    def fake_capture(self, _exe, _roms, _inp, _wlf, *,
                     frames, start_frame, seconds, capture_out, trace_out):
        self.calls.append(start_frame)
        report = capture._empty_report(frames, start_frame)
        if self.fail_start == start_frame:
            report["status"] = "CAPTURE_FILE_NOT_CREATED"
            return report
        byte_mng = make_synthetic_mng(
            start_frame, frames,
            tamper_at=(start_frame + 12 if
                       self.tamper_pixel and start_frame == 120 else None))
        Path(capture_out).write_bytes(byte_mng)
        lines = ["callback_index,first_port_reads,playback_words"]
        for frame in range(start_frame, start_frame + frames):
            p0 = frame + 1
            words = p0 * 31
            if self.tamper_counter and start_frame == 120 and frame == 130:
                p0 += 1
                words += 31
            lines.append(f"{frame},{p0},{words}")
        data = ("\n".join(lines) + "\n").encode("ascii")
        Path(trace_out).write_bytes(data)
        report.update({
            "status": "CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED",
            "capture_window_within_recording": True,
            "capture_frame_count_matches_request": True,
            "candidate_mng_found": True,
            "candidate_mng_integrity_verified": True,
            "candidate_capture_retained_privately": True,
            "candidate_count_trace_retained_privately": True,
            "private_input_staging_byte_identical": True,
            "recording_wolfmame_family_0_106": True,
            "emulator_help_reports_mame_0_106": True,
            "dino_rom_verifyroms_passed": True,
            "emulator_process_spawned": True,
            "process_timed_out": False,
            "process_exit_code": 0,
            "recorded_input_records": 500,
            "candidate_video_frames": frames,
            "capture_mng_sha256": hashlib.sha256(byte_mng).hexdigest(),
            "capture_mng_byte_count": len(byte_mng),
            "candidate_count_trace_sha256": hashlib.sha256(data).hexdigest(),
            "candidate_count_trace_byte_count": len(data),
            "private_inp_sha256": "1" * 64,
            "private_wlf_sha256": "2" * 64,
        })
        return report

    def run_fake(self, *, out=None, compare_fn=dual.compare,
                 frames=40, shift=20, start=100):
        return experiment.run_experiment(
            "fake.exe", "fake-rom-dir", "fake.inp", "fake.wlf",
            out or self.destination, first_start=start, frames=frames,
            shift=shift, seconds=15,
            metadata_fn=lambda _inp, _wlf: (500, "0.106 test", 10),
            capture_fn=self.fake_capture, compare_fn=compare_fn)

    def test_complete_two_candidate_captures_compare_and_remain_private(self):
        result = self.run_fake()
        self.assertEqual(result["status"], experiment.MATCH)
        self.assertEqual(self.calls, [100, 120])
        self.assertEqual(result["overlap_callbacks_compared"], 20)
        self.assertEqual(result["overlap_port0_count_mismatches"], 0)
        self.assertEqual(result["overlap_word_count_mismatches"], 0)
        self.assertTrue(result["first_capture_complete"])
        self.assertTrue(result["second_capture_complete"])
        self.assertTrue(result["cross_capture_evidence_checked"])
        for key in ("original_inp_playback_verified",
                    "independent_emulator_runs_authenticated",
                    "exact_input_record_to_video_callback_mapping_verified",
                    "physical_nintendo_switch_tested"):
            self.assertFalse(result[key])
        content = (self.destination / "stage292-summary.json").read_text()
        self.assertNotIn(str(self.root), content)
        self.assertNotIn("sha256", content)
        self.assertNotIn("private_inp_sha256", content)
        self.assertEqual(
            (self.destination / "stage292-summary.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(list(self.destination.iterdir())), 7)

    def test_first_capture_failure_stops_before_second_and_writes_summary(self):
        self.fail_start = 100
        result = self.run_fake()
        self.assertEqual(result["status"], experiment.BLOCKED_FIRST)
        self.assertEqual(self.calls, [100])
        self.assertFalse((self.destination / "second-receipt.json").exists())
        self.assertEqual(json.loads((self.destination / "first-receipt.json").read_text())["status"],
                         "CAPTURE_FILE_NOT_CREATED")
        self.assertTrue((self.destination / "stage292-summary.json").exists())

    def test_second_capture_failure_keeps_first_candidate_private(self):
        self.fail_start = 120
        result = self.run_fake()
        self.assertEqual(result["status"], experiment.BLOCKED_SECOND)
        self.assertEqual(self.calls, [100, 120])
        self.assertTrue((self.destination / "first.mng").exists())
        self.assertFalse((self.destination / "second.mng").exists())
        self.assertFalse(result["second_capture_complete"])

    def test_pixel_mismatch_is_nonzero_candidate_without_leak(self):
        self.tamper_pixel = True
        result = self.run_fake()
        self.assertEqual(result["status"], experiment.NONMATCH)
        self.assertEqual(result["dual_check_status"], dual.NO_PIXELS)
        self.assertEqual(result["overlap_callbacks_compared"], 20)
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_counter_mismatch_is_nonzero_even_with_equal_pixels(self):
        self.tamper_counter = True
        result = self.run_fake()
        self.assertEqual(result["status"], experiment.NONMATCH)
        self.assertEqual(result["dual_check_status"], dual.MISMATCH)
        self.assertEqual(result["overlap_port0_count_mismatches"], 1)
        self.assertEqual(result["overlap_word_count_mismatches"], 1)

    def test_comparison_exception_is_fail_closed(self):
        def broken_compare(*args, **kwargs):
            raise ValueError("private full path C:\\sensitive\\roms")
        report = self.run_fake(compare_fn=broken_compare)
        self.assertEqual(report["status"], experiment.BLOCKED_COMPARE)
        self.assertTrue(report["privately_retained_input_video_receipts"])
        self.assertNotIn("sensitive", (self.destination / "stage292-summary.json").read_text())

    def test_counterfeit_success_status_without_valid_evidence_is_rejected(self):
        def fake_positive(*args, **kwargs):
            return {"status": dual.MATCH, "overlap_callback_frames": 20}
        result = self.run_fake(compare_fn=fake_positive)
        self.assertEqual(result["status"], experiment.NONMATCH)
        self.assertEqual(result["dual_check_status"], dual.MATCH)

    def test_invalid_windows_fail_before_creating_output_folder(self):
        for start, frames, shift in (
            (-1, 40, 20), (100, 40, 15), (100, 40, 25),
            (490, 40, 20), (True, 40, 20), (100, 3602, 20),
        ):
            with self.subTest((start, frames, shift)):
                with self.assertRaises(ValueError):
                    self.run_fake(start=start, frames=frames, shift=shift)
                self.assertFalse(self.destination.exists())

    def test_existing_private_folder_is_not_overwritten(self):
        self.destination.mkdir()
        marker = self.destination / "keep-me.txt"
        marker.write_text("unrelated")
        with self.assertRaises(ValueError):
            self.run_fake()
        self.assertEqual(marker.read_text(), "unrelated")

    def test_parent_symlink_is_rejected(self):
        parent_link = self.root / "link"
        parent_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.run_fake(out=parent_link / "candidate")
        self.assertFalse((self.root / "candidate").exists())

    def test_capture_exception_does_not_escape_in_private_receipt(self):
        def broken_capture(*args, **kwargs):
            raise OSError("private file /home/user/secret-rom.zip")
        report = experiment.run_experiment(
            "exe", "roms", "inp", "wlf", self.destination,
            first_start=100, frames=40, shift=20, seconds=30,
            metadata_fn=lambda x,y: (500, "0.106 source", 5),
            capture_fn=broken_capture)
        self.assertEqual(report["status"], experiment.BLOCKED_FIRST)
        self.assertNotIn("secret-rom", (self.destination / "first-receipt.json").read_text())
        self.assertNotIn("secret-rom", (self.destination / "stage292-summary.json").read_text())

    def test_cli_status_is_not_misreported(self):
        args = ["--emulator", "fake", "--rom-dir", "fake",
                "--inp", "fake", "--wlf", "fake",
                "--out-dir", str(self.destination)]
        self.assertEqual(
            experiment.main(args, experiment=lambda *a, **k: {"status": experiment.MATCH}), 0)
        self.assertEqual(
            experiment.main(args, experiment=lambda *a, **k: {"status": experiment.NONMATCH}), 2)
        self.assertEqual(
            experiment.main(args, experiment=lambda *a, **k: (_ for _ in ()).throw(
                ValueError("private detail"))), 2)


if __name__ == "__main__":
    unittest.main()
