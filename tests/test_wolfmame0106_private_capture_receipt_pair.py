"""Stage288 synthetic tests for private receipt linkage; no ROM/INP game data."""
import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import wolfmame0106_private_mng_audit as mng
from tools import wolfmame0106_private_mng_capture as capture
from tools import wolfmame0106_private_capture_receipt_pair as linkage
from tools import wolfmame0106_private_window_overlap as overlap


def chunk(kind, body=b""):
    return (struct.pack(">I", len(body)) + kind + body +
            struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def mng_bytes(start, count=32, static=False):
    header = struct.pack(">7I", 2, 2, 60, 0, 0, 0, 0x41)
    frames = []
    for i in range(start, start + count):
        rgb = (4, 5, 6) if static else (i % 239, (i * 3) % 251, (i * 7) % 253)
        scanlines = (b"\x00" + bytes(rgb) * 2) * 2
        png = (mng.png.PNG_SIG +
               chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) +
               chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND"))
        frames.append(png[len(mng.png.PNG_SIG):])
    return mng.MNG_SIGNATURE + chunk(b"MHDR", header) + b"".join(frames) + chunk(b"MEND")


class PrivateReceiptLinkageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dino288-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a, self.b = self.root / "a.mng", self.root / "b.mng"
        self.ar, self.br = self.root / "a.json", self.root / "b.json"
        self.write_pair()

    def make_receipt(self, mng_path, output, start, count=32):
        data = capture._empty_report(count, start)
        data.update(
            status="CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED",
            capture_window_within_recording=True,
            capture_frame_count_matches_request=True,
            candidate_mng_found=True,
            candidate_mng_integrity_verified=True,
            candidate_capture_retained_privately=True,
            private_input_staging_byte_identical=True,
            recording_wolfmame_family_0_106=True,
            emulator_help_reports_mame_0_106=True,
            dino_rom_verifyroms_passed=True,
            emulator_process_spawned=True,
            process_timed_out=False,
            process_exit_code=0,
            recorded_input_records=314951,
            candidate_video_frames=count,
            capture_mng_byte_count=mng_path.stat().st_size,
            capture_mng_sha256=hashlib.sha256(mng_path.read_bytes()).hexdigest(),
        )
        output.write_text(json.dumps(data), encoding="utf-8")
        return data

    def write_pair(self, *, static=False):
        self.a.write_bytes(mng_bytes(100, static=static))
        self.b.write_bytes(mng_bytes(116, static=static))
        self.make_receipt(self.a, self.ar, 100)
        self.make_receipt(self.b, self.br, 116)

    def compare(self, **kwargs):
        return linkage.compare_receipted(
            kwargs.get("a", self.a), kwargs.get("b", self.b),
            kwargs.get("ar", self.ar), kwargs.get("br", self.br),
            minimum_overlap=kwargs.get("min_overlap", 16))

    def edit_receipt(self, path, **updates):
        data = json.loads(path.read_text())
        data.update(updates)
        path.write_text(json.dumps(data), encoding="utf-8")

    def test_matching_dynamic_overlap_requires_two_bound_receipts(self):
        result = self.compare()
        self.assertEqual(result["schema"], linkage.SCHEMA)
        self.assertEqual(result["status"], overlap.MATCH_DYNAMIC)
        self.assertTrue(result["first_capture_receipt_validated_privately"])
        self.assertTrue(result["second_capture_receipt_validated_privately"])
        self.assertTrue(result["candidate_mng_bytes_bound_to_receipts"])
        self.assertEqual(result["overlap_frame_count"], 16)
        self.assertFalse(result["two_independent_emulator_runs_verified"])
        self.assertFalse(result["exact_input_video_alignment_verified"])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("capture_mng_sha256", json.dumps(result))

    def test_tampered_video_rejected_before_pixel_comparison(self):
        raw = bytearray(self.a.read_bytes())
        raw[90] ^= 3
        self.a.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "differs"):
            self.compare()

    def test_receipt_swapping_rejected(self):
        with self.assertRaisesRegex(ValueError, "inconsistency|differs"):
            self.compare(ar=self.br, br=self.ar)

    def test_missing_fingerprint_in_legacy_receipt_rejected(self):
        self.edit_receipt(self.ar, capture_mng_sha256=None)
        with self.assertRaisesRegex(ValueError, "content binding"):
            self.compare()

    def test_count_mismatch_or_bad_window_rejected(self):
        for update in (
                {"candidate_video_frames": 31},
                {"requested_end_frame_exclusive": 140},
                {"requested_start_frame": True},
                {"recorded_input_records": 100},
                {"capture_frame_count_matches_request": False},
                {"capture_mng_byte_count": 123},
                {"capture_mng_sha256": "a" * 64}):
            self.write_pair()
            self.edit_receipt(self.ar, **update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.compare()

    def test_incomplete_capture_and_provenance_claims_rejected(self):
        for update in (
                {"status": "CAPTURE_FRAME_COUNT_MISMATCH"},
                {"status": "CANDIDATE_MNG_VALID_BUT_PROCESS_TIMED_OUT"},
                {"process_exit_code": 1},
                {"process_timed_out": True},
                {"candidate_capture_retained_privately": False},
                {"dino_rom_verifyroms_passed": False},
                {"private_input_staging_byte_identical": False}):
            self.write_pair()
            self.edit_receipt(self.ar, **update)
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.compare()

    def test_same_file_or_symlink_receipt_rejected(self):
        with self.assertRaisesRegex(ValueError, "different private receipts"):
            self.compare(br=self.ar)
        with self.assertRaisesRegex(ValueError, "different candidate videos"):
            self.compare(b=self.a)
        alias = self.root / "alias.json"
        alias.symlink_to(self.ar)
        with self.assertRaisesRegex(ValueError, "private regular"):
            self.compare(ar=alias)

    def test_comparison_stays_private_for_static_overlap(self):
        self.write_pair(static=True)
        result = self.compare()
        self.assertEqual(result["status"], "OVERLAP_MATCH_STATIC_UNAUTHENTICATED")
        self.assertTrue(result["candidate_mng_bytes_bound_to_receipts"])

    def test_cli_private_receipt_has_no_paths_or_content_hashes(self):
        output = self.root / "linked.json"
        args = ["--first-mng", str(self.a), "--second-mng", str(self.b),
                "--first-receipt", str(self.ar), "--second-receipt", str(self.br),
                "--out", str(output)]
        self.assertEqual(linkage.main(args), 0)
        data = json.loads(output.read_text())
        self.assertTrue(data["candidate_mng_bytes_bound_to_receipts"])
        self.assertNotIn(str(self.root), output.read_text())
        self.assertNotIn("sha256", output.read_text())
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            linkage.main(args)

    def test_cli_blocks_invalid_receipts_without_leaking_details(self):
        self.edit_receipt(self.br, capture_mng_sha256="wrong")
        output = self.root / "invalid.json"
        args = ["--first-mng", str(self.a), "--second-mng", str(self.b),
                "--first-receipt", str(self.ar), "--second-receipt", str(self.br),
                "--out", str(output)]
        self.assertEqual(linkage.main(args), 2)
        data = json.loads(output.read_text())
        self.assertEqual(data["status"], "BLOCKED_PRIVATE_CAPTURE_RECEIPT_LINKAGE")
        self.assertFalse(data["candidate_mng_bytes_bound_to_receipts"])
        self.assertNotIn(str(self.root), output.read_text())

    def test_unexpected_receipt_layout_refused(self):
        self.edit_receipt(self.ar, schema="invalid-version")
        with self.assertRaisesRegex(ValueError, "schema"):
            self.compare()

    def test_insufficient_overlap_returns_nonzero_in_cli(self):
        self.write_pair()
        output = self.root / "insufficient.json"
        args = ["--first-mng", str(self.a), "--second-mng", str(self.b),
                "--first-receipt", str(self.ar), "--second-receipt", str(self.br),
                "--min-overlap", "24", "--out", str(output)]
        self.assertEqual(linkage.main(args), 2)
        self.assertEqual(json.loads(output.read_text())["status"],
                         "INSUFFICIENT_REQUESTED_WINDOW_OVERLAP")


if __name__ == "__main__":
    unittest.main()
