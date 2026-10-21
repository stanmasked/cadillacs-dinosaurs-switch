"""Stage287 synthetic-only cross-window MNG tests; no game frames or ROM."""
import json
import os
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import wolfmame0106_private_mng_audit as mng
from tools import wolfmame0106_private_mng_overlap as overlap


def _chunk(kind, body=b""):
    return (struct.pack(">I", len(body)) + kind + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff))


def _png(shade, *, width=2, height=2, compression=6):
    rgb = bytes((shade, shade + 1, shade + 2))
    scanline = b"\x00" + rgb * width
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (mng.png.PNG_SIG + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(scanline * height, compression))
            + _chunk(b"IEND"))


def _mng(shades, *, width=2, height=2, ticks=60, compression=6):
    mhdr = struct.pack(">7I", width, height, ticks, 0, 0, 0, 0x41)
    frames = [_png(s, width=width, height=height, compression=compression)
              for s in shades]
    return (mng.MNG_SIGNATURE + _chunk(b"MHDR", mhdr)
            + b"".join(p[len(mng.png.PNG_SIG):] for p in frames)
            + _chunk(b"MEND"))


class PrivateMNGOverlapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="stage287-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.first = self.root / "run_a.mng"
        self.second = self.root / "run_b.mng"

    def store(self, a=(10, 20, 30, 40, 50), b=(30, 40, 50, 60), **kwargs):
        self.first.write_bytes(_mng(a))
        self.second.write_bytes(_mng(b, **kwargs))

    def test_equal_overlap_finds_exact_video_indices(self):
        self.store()
        result = overlap.compare(self.first, 100, self.second, 102)
        self.assertEqual(result["status"], overlap.MATCH)
        self.assertEqual(result["overlap_start_candidate_frame"], 102)
        self.assertEqual(result["overlap_end_candidate_frame_exclusive"], 105)
        self.assertEqual(result["overlap_frame_count"], 3)
        self.assertEqual(result["matching_decoded_pixel_frames"], 3)
        self.assertEqual(result["mismatching_decoded_pixel_frames"], 0)
        self.assertTrue(result["overlap_has_frame_to_frame_changes"])
        self.assertTrue(result["all_overlap_decoded_pixels_equal"])
        self.assertTrue(result["candidate_formats_match"])
        self.assertTrue(result["both_candidate_mngs_valid"])
        self.assertFalse(result["capture_from_independent_runs_verified"])
        self.assertFalse(result["input_video_alignment_verified"])
        self.assertFalse(result["original_gameplay_parity_verified"])

    def test_first_mismatch_is_absolute_candidate_video_position(self):
        self.store(b=(30, 41, 50, 60))
        result = overlap.compare(self.first, 100, self.second, 102)
        self.assertEqual(result["status"], overlap.MISMATCH)
        self.assertEqual(result["first_mismatched_candidate_frame"], 103)
        self.assertEqual(result["matching_decoded_pixel_frames"], 2)
        self.assertEqual(result["mismatching_decoded_pixel_frames"], 1)
        self.assertFalse(result["all_overlap_decoded_pixels_equal"])

    def test_compressed_differently_but_same_pixels_equal(self):
        self.store()
        self.second.write_bytes(_mng((30, 40, 50, 60), compression=9))
        self.assertEqual(overlap.compare(self.first, 100, self.second, 102)["status"],
                         overlap.MATCH)

    def test_static_identical_overlap_is_inconclusive(self):
        self.store(a=(10, 10, 10, 10), b=(10, 10, 10))
        result = overlap.compare(self.first, 200, self.second, 201)
        self.assertEqual(result["status"], overlap.STATIC)
        self.assertTrue(result["all_overlap_decoded_pixels_equal"])
        self.assertFalse(result["overlap_has_frame_to_frame_changes"])

    def test_static_different_overlap_is_mismatch(self):
        self.store(a=(10, 10, 10, 10), b=(20, 20, 20))
        result = overlap.compare(self.first, 200, self.second, 201)
        self.assertEqual(result["status"], overlap.MISMATCH)
        self.assertEqual(result["mismatching_decoded_pixel_frames"], 3)

    def test_no_shared_window_or_single_shared_frame_is_blocked(self):
        self.store()
        for start in (104, 105, 200):
            with self.subTest(start=start):
                report = overlap.compare(self.first, 100, self.second, start)
                self.assertEqual(report["status"], overlap.BLOCKED)
                self.assertFalse(report["all_overlap_decoded_pixels_equal"])

    def test_bad_offsets_rejected(self):
        self.store()
        for start in (-1, True, "100", 10000001, 2.5):
            with self.subTest(start=start), self.assertRaises(ValueError):
                overlap.compare(self.first, start, self.second, 102)

    def test_same_file_hardlink_and_symlink_refused(self):
        self.store()
        with self.assertRaisesRegex(ValueError, "distinct"):
            overlap.compare(self.first, 100, self.first, 102)
        alias = self.root / "hardlinked.mng"
        try:
            os.link(self.first, alias)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaisesRegex(ValueError, "distinct"):
                overlap.compare(self.first, 100, alias, 102)
        symlink = self.root / "symlink.mng"
        try:
            symlink.symlink_to(self.first)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaisesRegex(ValueError, "private regular"):
                overlap.compare(self.first, 100, symlink, 102)

    def test_frame_dimensions_and_ticks_must_match(self):
        self.store(width=3)
        report = overlap.compare(self.first, 100, self.second, 102)
        self.assertEqual(report["status"], overlap.BLOCKED)
        self.assertTrue(report["both_candidate_mngs_valid"])
        self.assertFalse(report["candidate_formats_match"])
        self.store(ticks=50)
        report = overlap.compare(self.first, 100, self.second, 102)
        self.assertEqual(report["status"], overlap.BLOCKED)
        self.assertFalse(report["candidate_formats_match"])

    def test_corrupt_or_private_path_refused(self):
        self.store()
        raw = bytearray(self.second.read_bytes())
        raw[60] ^= 0xff
        self.second.write_bytes(raw)
        with self.assertRaises(ValueError):
            overlap.compare(self.first, 100, self.second, 102)
        self.store()
        with self.assertRaisesRegex(ValueError, "private regular"):
            overlap.compare(self.first, 100, mng.gate.ROOT / "blocked.mng", 102)

    def test_audit_sink_gets_private_digests_without_receipt_export(self):
        self.store()
        found = []
        report = mng.audit(self.first, frame_sha256_sink=lambda i, digest:
                           found.append((i, digest)))
        self.assertEqual([i for i, _ in found], list(range(5)))
        self.assertTrue(all(isinstance(d, bytes) and len(d) == 32
                            for _, d in found))
        self.assertEqual(report["candidate_frame_dimensions"], [2, 2])
        self.assertNotIn(found[0][1].hex(), json.dumps(report))
        with self.assertRaisesRegex(ValueError, "sink"):
            mng.audit(self.first, frame_sha256_sink=False)

    def test_cli_only_writes_exclusive_aggregate_private_receipt(self):
        self.store()
        destination = self.root / "comparison.json"
        argv = ["--first", str(self.first), "--first-start", "100",
                "--second", str(self.second), "--second-start", "102",
                "--out", str(destination)]
        self.assertEqual(overlap.main(argv), 0)
        report = json.loads(destination.read_text())
        self.assertEqual(report["status"], overlap.MATCH)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.root), destination.read_text())
        self.assertNotIn(".mng", destination.read_text())
        self.assertFalse(report["raw_frames_paths_or_pixel_digests_exported"])
        with self.assertRaises(FileExistsError):
            overlap.main(argv)

    def test_cli_distinguishes_mismatch_static_and_blocked(self):
        self.store(b=(30, 41, 50, 60))
        self.assertEqual(overlap.main([
            "--first", str(self.first), "--first-start", "100",
            "--second", str(self.second), "--second-start", "102",
            "--out", str(self.root / "diff.json")]), 3)
        self.store(a=(20, 20, 20, 20), b=(20, 20, 20))
        self.assertEqual(overlap.main([
            "--first", str(self.first), "--first-start", "100",
            "--second", str(self.second), "--second-start", "101",
            "--out", str(self.root / "static.json")]), 4)
        self.assertEqual(overlap.main([
            "--first", str(self.first), "--first-start", "100",
            "--second", str(self.second), "--second-start", "104",
            "--out", str(self.root / "blocked.json")]), 2)


if __name__ == "__main__":
    unittest.main()
