"""Stage291 synthetic-only dual video/counter overlap tests; no real game data."""
import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import wolfmame0106_private_dual_trace_consistency as dual
from tools import wolfmame0106_private_mng_capture as capture
from tools import wolfmame0106_private_mng_audit as mng


def chunk(tag, payload=b""):
    return (struct.pack(">I", len(payload)) + tag + payload +
            struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))


def candidate_movie(start, n=40, tamper=None):
    mhdr = struct.pack(">7I", 2, 2, 60, 0, 0, 0, 0x41)
    pngs = []
    for frame in range(start, start + n):
        colour = (frame % 251, (frame * 3) % 253, (frame * 7) % 239)
        if frame == tamper:
            colour = (255, 255, 255)
        scanlines = (b"\x00" + bytes(colour) * 2) * 2
        raw = (mng.png.PNG_SIG +
               chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) +
               chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND"))
        pngs.append(raw[len(mng.png.PNG_SIG):])
    return mng.MNG_SIGNATURE + chunk(b"MHDR", mhdr) + b"".join(pngs) + chunk(b"MEND")


def counter_value(frame, static=False):
    if static:
        # Static throughout 116..139; increases before and after.
        n = (frame + 1) if frame < 116 else (117 if frame < 140 else frame - 22)
    else:
        n = frame + 1
    return n, n * 31


class DualCaptureCountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dino291-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a = self.root / "first.mng"
        self.b = self.root / "second.mng"
        self.ar = self.root / "first.json"
        self.br = self.root / "second.json"
        self.at = self.root / "first.csv"
        self.bt = self.root / "second.csv"
        self.write()

    def _capture(self, movie, receipt, trace, start, *,
                 tamper=None, static=False, shift=None):
        movie.write_bytes(candidate_movie(start, tamper=tamper))
        csv = ["callback_index,first_port_reads,playback_words"]
        for frame in range(start, start+40):
            port0, words = counter_value(frame, static=static)
            if frame == shift:
                # A one-record mismatch that still preserves monotonicity.
                port0 += 1
                words += 31
            csv.append(f"{frame},{port0},{words}")
        trace.write_bytes(("\n".join(csv) + "\n").encode("ascii"))
        data = capture._empty_report(40, start)
        data.update({
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
            "process_timed_out": False,
            "process_exit_code": 0,
            "recorded_input_records": 500,
            "candidate_video_frames": 40,
            "capture_mng_sha256": hashlib.sha256(movie.read_bytes()).hexdigest(),
            "capture_mng_byte_count": movie.stat().st_size,
            "candidate_count_trace_retained_privately": True,
            "candidate_count_trace_sha256": hashlib.sha256(trace.read_bytes()).hexdigest(),
            "candidate_count_trace_byte_count": trace.stat().st_size,
            "private_inp_sha256": "1" * 64,
            "private_wlf_sha256": "2" * 64,
        })
        receipt.write_text(json.dumps(data), encoding="utf-8")

    def write(self, *, first_static=False, second_static=False,
              video_tamper=None, counter_shift=None):
        self._capture(self.a, self.ar, self.at, 100, static=first_static)
        self._capture(self.b, self.br, self.bt, 116, tamper=video_tamper,
                      static=second_static, shift=counter_shift)

    def replace_receipt(self, path, **changes):
        obj = json.loads(path.read_text())
        obj.update(changes)
        path.write_text(json.dumps(obj), encoding="utf-8")

    def check(self, **kwargs):
        return dual.compare(
            kwargs.get("a", self.a), kwargs.get("ar", self.ar),
            kwargs.get("at", self.at), kwargs.get("b", self.b),
            kwargs.get("br", self.br), kwargs.get("bt", self.bt),
            minimum_overlap=kwargs.get("min_overlap", 16))

    def test_identical_dynamic_pixels_and_counters_are_candidate_only(self):
        result = self.check()
        self.assertEqual(result["status"], dual.MATCH)
        self.assertEqual(result["overlap_callback_frames"], 24)
        self.assertEqual(result["matching_port0_read_counts"], 24)
        self.assertEqual(result["matching_total_playback_word_counts"], 24)
        self.assertTrue(result["overlap_counter_values_change"])
        self.assertTrue(result["same_private_inp_and_wlf_hashes"])
        self.assertFalse(result["input_record_video_frame_alignment_verified"])
        self.assertFalse(result["independent_emulator_executions_authenticated"])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("sha256", json.dumps(result))

    def test_slight_counter_divergence_is_detected_even_if_pixels_match(self):
        self.write(counter_shift=130)
        result = self.check()
        self.assertEqual(result["status"], dual.MISMATCH)
        self.assertEqual(result["first_counter_mismatch_callback_index"], 130)
        self.assertEqual(result["mismatching_port0_read_counts"], 1)
        self.assertEqual(result["mismatching_total_playback_word_counts"], 1)

    def test_static_overlap_counters_do_not_count_as_positive(self):
        self.write(first_static=True, second_static=True)
        result = self.check()
        self.assertEqual(result["status"], dual.STATIC)
        self.assertFalse(result["overlap_counter_values_change"])

    def test_mng_pixel_mismatch_blocks_a_counter_confirmation(self):
        self.write(video_tamper=130)
        result = self.check()
        self.assertEqual(result["status"], dual.NO_PIXELS)
        self.assertFalse(result["dynamic_pixel_overlap_matching"])
        self.assertEqual(result["matching_port0_read_counts"], 0)

    def test_tampered_trace_without_matching_receipt_fails(self):
        self.bt.write_bytes(self.bt.read_bytes().replace(b"130,131,4061", b"130,132,4092"))
        with self.assertRaisesRegex(ValueError, "mismatch|hash"):
            self.check()

    def test_different_private_input_or_wlf_rejected(self):
        self.replace_receipt(self.br, private_inp_sha256="a"*64)
        with self.assertRaisesRegex(ValueError, "absent or unequal"):
            self.check()
        self.write()
        self.replace_receipt(self.ar, private_wlf_sha256=None)
        with self.assertRaisesRegex(ValueError, "absent or unequal"):
            self.check()

    def test_unverified_or_nonclean_capture_rejected(self):
        self.replace_receipt(self.br, process_exit_code=1)
        with self.assertRaises(ValueError):
            self.check()
        self.write()
        self.replace_receipt(self.br, candidate_count_trace_retained_privately=False)
        with self.assertRaises(ValueError):
            self.check()

    def test_same_trace_file_and_symlink_rejected(self):
        with self.assertRaisesRegex(ValueError, "distinct"):
            self.check(bt=self.at)
        alias = self.root / "alias.csv"
        alias.symlink_to(self.at)
        with self.assertRaises(ValueError):
            self.check(at=alias)

    def test_insufficient_overlap_does_not_claim_equality(self):
        result = self.check(min_overlap=30)
        self.assertEqual(result["status"], dual.NO_PIXELS)
        self.assertFalse(result["dynamic_pixel_overlap_matching"])

    def test_cli_exclusive_private_output_and_mismatch_exit_code(self):
        out = self.root / "comparison.json"
        args = [
            "--first-mng", str(self.a), "--first-receipt", str(self.ar),
            "--first-trace", str(self.at),
            "--second-mng", str(self.b), "--second-receipt", str(self.br),
            "--second-trace", str(self.bt), "--out", str(out),
        ]
        self.assertEqual(dual.main(args), 0)
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(out.read_text())["status"], dual.MATCH)
        self.assertNotIn(str(self.root), out.read_text())
        with self.assertRaises(FileExistsError):
            dual.main(args)
        self.write(counter_shift=130)
        bad = self.root / "mismatch.json"
        self.assertEqual(dual.main(args[:-2] + ["--out", str(bad)]), 2)
        self.assertEqual(json.loads(bad.read_text())["status"], dual.MISMATCH)

    def test_missing_legacy_private_hash_rejected(self):
        self.replace_receipt(self.ar, private_wlf_sha256=None)
        with self.assertRaises(ValueError):
            self.check()


if __name__ == "__main__":
    unittest.main()
