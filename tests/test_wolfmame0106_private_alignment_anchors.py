"""Stage289 synthetic-only input/visual anchor calibration tests."""
import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import wolfmame0106_dino_input_reference as inp_ref
from tools import wolfmame0106_private_alignment_anchors as calibration
from tools import wolfmame0106_private_mng_audit as mng
from tools import wolfmame0106_private_mng_capture as capture
from tools import wolfmame0106_private_window_overlap as overlap


def chunk(kind, body=b""):
    return (struct.pack(">I", len(body)) + kind + body +
            struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff))


def fake_mng(start, count=120, still=False):
    mhdr = struct.pack(">7I", 2, 2, 60, 0, 0, 0, 0x41)
    frames = []
    for i in range(start, start + count):
        col = (30, 30, 30) if still else (i % 251, (i*3) % 253, (i*7) % 239)
        scanlines = (b"\x00" + bytes(col) * 2) * 2
        frame = (mng.png.PNG_SIG +
                 chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) +
                 chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND"))
        frames.append(frame[len(mng.png.PNG_SIG):])
    return mng.MNG_SIGNATURE + chunk(b"MHDR", mhdr) + b"".join(frames) + chunk(b"MEND")


class ManualOffsetAnchorsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dino289-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inp, self.wlf = self.root / "dino.inp", self.root / "dino.wlf"
        self.a, self.b = self.root / "a.mng", self.root / "b.mng"
        self.ar, self.br = self.root / "a.json", self.root / "b.json"
        self.events = self.root / "visual-annotations.json"
        self._write_inp_wlf()
        self._write_videos()
        self._write_annotations()

    def _write_inp_wlf(self):
        n = 256
        header = bytearray(32)
        header[:4] = b"dino"
        header[16:20] = b"demo"
        rows = [bytearray(b"\xff" * inp_ref.FRAME_BYTES) for _ in range(n)]
        self.onsets = [("p1.attack_button1", 120, 19, 4),
                       ("p1.jump_button2", 155, 19, 5),
                       ("system.start1", 190, 3, 4)]
        for _name, frame, byte, bit in self.onsets:
            rows[frame][byte] &= ~(1 << bit)
        self.inp.write_bytes(bytes(header) + b"".join(rows))
        companion = bytearray(598)
        companion[:4] = b"WLF\x00"
        struct.pack_into("<I", companion, 4, 9)
        companion[148:157] = b"dino\x00\x00\x00\x00\x00"
        companion[157:167] = b"0.106 demo"
        companion[248:252] = b"demo"
        struct.pack_into("<II", companion, 256, 0, 5)
        struct.pack_into("<I", companion, 264, n)
        self.wlf.write_bytes(companion)

    def _receipt(self, path, out, start):
        count = 120
        receipt = capture._empty_report(count, start)
        receipt.update({
            "status": "CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED",
            "capture_window_within_recording": True,
            "capture_frame_count_matches_request": True,
            "candidate_mng_found": True,
            "candidate_mng_integrity_verified": True,
            "candidate_capture_retained_privately": True,
            "private_input_staging_byte_identical": True,
            "recording_wolfmame_family_0_106": True,
            "emulator_help_reports_mame_0_106": True,
            "dino_rom_verifyroms_passed": True,
            "emulator_process_spawned": True,
            "process_exit_code": 0,
            "process_timed_out": False,
            "recorded_input_records": 256,
            "candidate_video_frames": count,
            "capture_mng_byte_count": path.stat().st_size,
            "capture_mng_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "private_inp_sha256": hashlib.sha256(self.inp.read_bytes()).hexdigest(),
            "private_wlf_sha256": hashlib.sha256(self.wlf.read_bytes()).hexdigest(),
        })
        out.write_text(json.dumps(receipt))

    def _write_videos(self, still=False):
        self.a.write_bytes(fake_mng(100, still=still))
        self.b.write_bytes(fake_mng(116, still=still))
        self._receipt(self.a, self.ar, 100)
        self._receipt(self.b, self.br, 116)

    def _write_annotations(self, lags=(3, 3, 3), values=None):
        items = values if values is not None else [
            {"signal": name, "input_record_index": frame,
             "video_callback_index": frame + lag}
            for (name, frame, _, _), lag in zip(self.onsets, lags)
        ]
        self.events.write_text(json.dumps({
            "schema": calibration.ANNOTATION_SCHEMA, "anchors": items,
        }))

    def _update_receipt(self, path, **data):
        obj = json.loads(path.read_text())
        obj.update(data)
        path.write_text(json.dumps(obj))

    def check(self):
        return calibration.calibrate(self.inp, self.wlf, self.events,
                                     self.a, self.b, self.ar, self.br)

    def test_three_confirmed_input_edges_yield_only_offset_candidate(self):
        result = self.check()
        self.assertEqual(result["status"],
                         "CONSISTENT_MANUALLY_ANNOTATED_OFFSET_HYPOTHESIS_ONLY")
        self.assertEqual(result["offset_median_callback_minus_record"], 3)
        self.assertEqual(result["offset_spread"], 0)
        self.assertEqual(result["checked_input_press_edges"], 3)
        self.assertTrue(result["private_inp_wlf_bytes_match_capture_receipts"])
        self.assertTrue(result["overlap_dynamic_and_receipted"])
        self.assertFalse(result["manual_visual_annotations_independently_verified"])
        self.assertFalse(result["input_record_to_video_callback_alignment_verified"])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("sha256", json.dumps(result))

    def test_small_jitter_retains_bounded_hypothesis(self):
        self._write_annotations(lags=(4, 3, 5))
        result = self.check()
        self.assertEqual(result["offset_spread"], 2)
        self.assertEqual(result["offset_median_callback_minus_record"], 4)
        self.assertEqual(result["status"],
                         "CONSISTENT_MANUALLY_ANNOTATED_OFFSET_HYPOTHESIS_ONLY")

    def test_disperse_events_do_not_yield_stable_offset(self):
        self._write_annotations(lags=(3, 6, 13))
        result = self.check()
        self.assertEqual(result["status"], "DISPERSED_MANUAL_OFFSETS_NOT_CALIBRATED")
        self.assertEqual(result["offset_spread"], 10)

    def test_visual_index_outside_verified_overlap_refused(self):
        self._write_annotations(lags=(3, 3, 35))
        with self.assertRaisesRegex(ValueError, "outside input/overlap"):
            self.check()

    def test_event_not_a_rising_press_edge_is_refused(self):
        values = [{"signal": "p1.attack_button1", "input_record_index": 121,
                   "video_callback_index": 123}] + [
                      {"signal": name, "input_record_index": frame,
                       "video_callback_index": frame+3}
                      for name, frame, _, _ in self.onsets[1:]]
        self._write_annotations(values=values)
        with self.assertRaisesRegex(ValueError, "confirmed press edge"):
            self.check()

    def test_transposed_or_mismatched_inp_wlf_hash_refused(self):
        self._update_receipt(self.ar, private_inp_sha256="a" * 64)
        with self.assertRaisesRegex(ValueError, "content does not match"):
            self.check()
        self._write_videos()
        self._update_receipt(self.br, private_wlf_sha256="f" * 64)
        with self.assertRaisesRegex(ValueError, "content does not match"):
            self.check()

    def test_legacy_capture_receipts_lacking_input_hash_refused(self):
        self._update_receipt(self.ar, private_inp_sha256=None)
        with self.assertRaises(ValueError):
            self.check()

    def test_duplicate_or_closely_spaced_anchors_refused(self):
        duplicate = [
            {"signal": name, "input_record_index": frame,
             "video_callback_index": frame+3}
            for name, frame, _, _ in self.onsets]
        duplicate[2] = dict(duplicate[0])
        self._write_annotations(values=duplicate)
        with self.assertRaisesRegex(ValueError, "repeated manual annotation"):
            self.check()
        nearby = [dict(item) for item in duplicate]
        nearby[2] = {"signal": "p1.attack_button1",
                     "input_record_index": 125, "video_callback_index": 128}
        self._write_annotations(values=nearby)
        with self.assertRaisesRegex(ValueError, "widely spaced"):
            self.check()

    def test_malformed_or_nonprivate_annotations_refused(self):
        self._write_annotations(values=[])
        with self.assertRaisesRegex(ValueError, "number"):
            self.check()
        self._write_annotations(values=[{"signal": "not.valid", "input_record_index": 120,
                                         "video_callback_index": 123}] * 3)
        with self.assertRaisesRegex(ValueError, "invalid signal"):
            self.check()
        self._write_annotations()
        alias = self.root / "alias.json"
        alias.symlink_to(self.events)
        with self.assertRaisesRegex(ValueError, "private ordinary"):
            calibration.calibrate(self.inp, self.wlf, alias, self.a, self.b,
                                  self.ar, self.br)

    def test_static_overlap_is_not_calibration_evidence(self):
        self._write_videos(still=True)
        with self.assertRaisesRegex(ValueError, "exact dynamic"):
            self.check()

    def test_missing_or_bad_receipt_blocks_audit(self):
        self._update_receipt(self.br, status="CANDIDATE_MNG_VALID_BUT_PROCESS_TIMED_OUT")
        with self.assertRaises(ValueError):
            self.check()

    def test_output_is_exclusive_private_and_contains_no_events(self):
        dest = self.root / "stage289.json"
        args = [
            "--inp", str(self.inp), "--wlf", str(self.wlf),
            "--annotations", str(self.events),
            "--first-mng", str(self.a), "--second-mng", str(self.b),
            "--first-receipt", str(self.ar), "--second-receipt", str(self.br),
            "--out", str(dest),
        ]
        self.assertEqual(calibration.main(args), 0)
        data = dest.read_text()
        self.assertEqual(dest.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.root), data)
        self.assertNotIn("p1.attack", data)
        self.assertNotIn("private_inp_sha256", data)
        self.assertEqual(json.loads(data)["offset_spread"], 0)
        with self.assertRaises(FileExistsError):
            calibration.main(args)


if __name__ == "__main__":
    unittest.main()
