"""Stage287 synthetic-only MNG overlap tests: no game data or ROM bytes."""
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import wolfmame0106_private_window_overlap as overlap
from tools import wolfmame0106_private_mng_audit as mng


def chunk(kind, payload=b""):
    return (struct.pack(">I", len(payload)) + kind + payload +
            struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))


def png(color, level=6):
    scanlines = (b"\x00" + bytes(color) * 2) * 2
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    return (mng.png.PNG_SIG + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", zlib.compress(scanlines, level)) +
            chunk(b"IEND"))


def make_mng(colors, level=6, ticks=60):
    mhdr = struct.pack(">7I", 2, 2, ticks, 0, 0, 0, 0x41)
    return (mng.MNG_SIGNATURE + chunk(b"MHDR", mhdr) +
            b"".join(png(c, level)[len(mng.png.PNG_SIG):] for c in colors) +
            chunk(b"MEND"))


def color_at(index):
    return (index % 251, (index * 3) % 253, (index * 7) % 239)


class OverlapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dino287-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.first = self.root / "first.mng"
        self.second = self.root / "second.mng"

    def write(self, first_start=100, second_start=132, count=64,
              static=False, tamper=None, ticks=60):
        ca = [(7, 8, 9) if static else color_at(i)
              for i in range(first_start, first_start + count)]
        cb = [(7, 8, 9) if static else color_at(i)
              for i in range(second_start, second_start + count)]
        if tamper is not None:
            cb[tamper] = (255, 255, 255)
        self.first.write_bytes(make_mng(ca, level=1))
        self.second.write_bytes(make_mng(cb, level=9, ticks=ticks))

    def test_matching_dynamic_windows_are_candidate_only(self):
        self.write()
        result = overlap.compare(self.first, self.second, 100, 132)
        self.assertEqual(result["status"], overlap.MATCH_DYNAMIC)
        self.assertEqual(result["overlap_start"], 132)
        self.assertEqual(result["overlap_frame_count"], 32)
        self.assertEqual(result["matching_overlap_frames"], 32)
        self.assertEqual(result["mismatching_overlap_frames"], 0)
        self.assertTrue(result["overlap_has_pixel_changes"])
        for key in ("two_independent_emulator_runs_verified",
                    "original_inp_playback_verified",
                    "exact_input_video_alignment_verified",
                    "original_gameplay_parity_verified"):
            self.assertFalse(result[key])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("sha256", json.dumps(result))
        self.assertNotIn("fingerprint", json.dumps(result))

    def test_changed_frame_detected_at_requested_index(self):
        self.write(tamper=8)
        result = overlap.compare(self.first, self.second, 100, 132)
        self.assertEqual(result["status"],
                         "OVERLAP_PIXEL_MISMATCH_UNAUTHENTICATED")
        self.assertEqual(result["mismatching_overlap_frames"], 1)
        self.assertEqual(result["first_mismatching_callback_index"], 140)

    def test_static_overlap_does_not_count_as_dynamic_confirmation(self):
        self.write(static=True)
        result = overlap.compare(self.first, self.second, 100, 132)
        self.assertEqual(result["status"], "OVERLAP_MATCH_STATIC_UNAUTHENTICATED")
        self.assertFalse(result["overlap_has_pixel_changes"])

    def test_short_or_disjoint_windows_are_not_accepted(self):
        self.write(first_start=0, second_start=60)
        result = overlap.compare(self.first, self.second, 0, 60)
        self.assertEqual(result["overlap_frame_count"], 4)
        self.assertEqual(result["status"], "INSUFFICIENT_REQUESTED_WINDOW_OVERLAP")
        self.assertEqual(result["matching_overlap_frames"], 0)
        self.write(first_start=0, second_start=100)
        result = overlap.compare(self.first, self.second, 0, 100)
        self.assertEqual(result["overlap_frame_count"], 0)
        self.assertEqual(result["status"], "INSUFFICIENT_REQUESTED_WINDOW_OVERLAP")

    def test_incompatible_timing_is_not_compared(self):
        self.write(ticks=50)
        result = overlap.compare(self.first, self.second, 100, 132)
        self.assertEqual(result["status"], "INCOMPATIBLE_CANDIDATE_MNG_LAYOUT")
        self.assertFalse(result["candidate_layout_compatible"])

    def test_same_file_and_symlink_refused(self):
        self.write()
        with self.assertRaisesRegex(ValueError, "distinct"):
            overlap.compare(self.first, self.first, 100, 132)
        alias = self.root / "alias.mng"
        alias.symlink_to(self.second)
        with self.assertRaisesRegex(ValueError, "private regular"):
            overlap.compare(self.first, alias, 100, 132)

    def test_invalid_offsets_or_overlap_refused(self):
        self.write()
        for a, b, n in ((-1, 132, 16), (True, 132, 16),
                        (100, 10_000_001, 16), (100, 132, 1),
                        (100, 132, True)):
            with self.subTest(a=a, b=b, n=n), self.assertRaises(ValueError):
                overlap.compare(self.first, self.second, a, b, minimum_overlap=n)

    def test_bad_container_refused_and_no_receipt_paths(self):
        self.write()
        self.second.write_bytes(b"not-a-mng")
        with self.assertRaises(ValueError):
            overlap.compare(self.first, self.second, 100, 132)

    def test_digest_sink_does_not_change_public_audit_report(self):
        self.write()
        ephemeral = []
        result = mng.audit(self.first, _private_frame_digests=ephemeral)
        self.assertEqual(len(ephemeral), result["candidate_frame_count"])
        self.assertTrue(all(type(item) is bytes and len(item) == 32
                            for item in ephemeral))
        self.assertNotIn("frame_digests", result)
        self.assertNotIn("fingerprints", result)

    def test_private_exclusive_receipt_and_cli_status(self):
        self.write()
        output = self.root / "receipt.json"
        args = ["--first-mng", str(self.first), "--second-mng", str(self.second),
                "--first-start", "100", "--second-start", "132",
                "--out", str(output)]
        self.assertEqual(overlap.main(args), 0)
        report = json.loads(output.read_text())
        self.assertEqual(report["status"], overlap.MATCH_DYNAMIC)
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.root), output.read_text())
        with self.assertRaises(FileExistsError):
            overlap.main(args)

    def test_nonmatching_cli_returns_nonzero(self):
        self.write(tamper=8)
        output = self.root / "mismatch.json"
        args = ["--first-mng", str(self.first), "--second-mng", str(self.second),
                "--first-start", "100", "--second-start", "132",
                "--out", str(output)]
        self.assertEqual(overlap.main(args), 2)
        self.assertEqual(json.loads(output.read_text())["mismatching_overlap_frames"], 1)


if __name__ == "__main__":
    unittest.main()
