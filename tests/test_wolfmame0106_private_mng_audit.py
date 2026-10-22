"""Stage284 MNG verification tests: synthetic RGB, no ROM or game imagery."""
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import wolfmame0106_private_mng_audit as mng


def chunk(kind, body=b""):
    return (
        struct.pack(">I", len(body)) + kind + body +
        struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
    )


def synthetic_png(rgb=(12, 30, 90), filter_mode=0, compression=6):
    raw = b""
    prev = bytes(6)
    current = bytes(rgb) * 2
    for _ in range(2):
        row = bytearray()
        for i, val in enumerate(current):
            left = current[i - 3] if i >= 3 else 0
            above = prev[i]
            if filter_mode == 0:
                predictor = 0
            elif filter_mode == 1:
                predictor = left
            elif filter_mode == 2:
                predictor = above
            elif filter_mode == 3:
                predictor = (left + above) // 2
            else:
                corner = prev[i - 3] if i >= 3 else 0
                predictor = mng.pixels._paeth(left, above, corner)
            row.append((val - predictor) % 256)
        raw += bytes([filter_mode]) + bytes(row)
        prev = current
    ihdr = struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)
    return (
        mng.png.PNG_SIG + chunk(b"IHDR", ihdr) +
        chunk(b"IDAT", zlib.compress(raw, compression)) +
        chunk(b"IEND")
    )


def synthetic_indexed_png(depth, offset=0):
    """MAME-style palette PNG using packed 1/2/4/8-bit indices."""
    palette_count = (1 << depth) if depth < 8 else 4
    palette = b"".join(
        bytes(((i * 37) & 255, (i * 73) & 255, (i * 109) & 255))
        for i in range(palette_count)
    )
    rows = [[(x + offset) % palette_count for x in range(5)] for _ in range(2)]
    raw = bytearray()
    for row in rows:
        packed = bytearray((len(row) * depth + 7) // 8)
        for x, index in enumerate(row):
            bit_offset = x * depth
            packed[bit_offset // 8] |= index << (8 - depth - (bit_offset % 8))
        raw.extend(bytes([0]))
        raw.extend(packed)
    ihdr = struct.pack(">IIBBBBB", 5, 2, depth, 3, 0, 0, 0)
    return (
        mng.png.PNG_SIG + chunk(b"IHDR", ihdr) + chunk(b"PLTE", palette) +
        chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND")
    )


def synthetic_mng(images, *, w=2, h=2, ticks=60, end=True):
    mhdr = struct.pack(">7I", w, h, ticks, 0, 0, 0, 0x41)
    data = (mng.MNG_SIGNATURE + chunk(b"MHDR", mhdr) +
            b"".join(frame[len(mng.png.PNG_SIG):] for frame in images))
    return data + (chunk(b"MEND") if end else b"")


class CandidateMNGFrameAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dino284-only-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "capture.mng"

    def store(self, frames=None, **kwargs):
        if frames is None:
            frames = [synthetic_png(), synthetic_png()]
        self.path.write_bytes(synthetic_mng(frames, **kwargs))

    def test_valid_mng_has_conservative_status_and_no_provenance(self):
        self.store([synthetic_png(), synthetic_png((90, 50, 20))])
        result = mng.audit(self.path)
        self.assertEqual(result["status"], "STRUCTURALLY_VALID_CANDIDATE_MNG_UNAUTHENTICATED")
        self.assertEqual(result["candidate_frame_count"], 2)
        self.assertEqual(result["changed_candidate_pairs"], 1)
        self.assertEqual(result["identical_candidate_pairs"], 0)
        self.assertEqual(result["first_changed_candidate_pair"], [0, 1])
        self.assertTrue(result["embedded_png_scanlines_and_chunk_crcs_valid"])
        self.assertEqual(result["mng_ticks_per_second"], 60)
        self.assertFalse(result["original_inp_playback_verified"])
        self.assertFalse(result["emulator_provenance_verified"])
        self.assertFalse(result["exact_video_to_inp_frame_alignment_verified"])
        self.assertFalse(result["physical_switch_tested"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_mame_palette_png_packed_depths_audit_end_to_end(self):
        # Historical MAME writes indexed PNG at bit depths 1, 2, 4 or 8
        # when its bitmap is palette-based. Width five exercises row padding.
        for depth in (1, 2, 4, 8):
            with self.subTest(depth=depth):
                self.store([
                    synthetic_indexed_png(depth, offset=0),
                    synthetic_indexed_png(depth, offset=1),
                ], w=5, h=2)
                result = mng.audit(self.path, minimum_frames=2)
                self.assertEqual(result["candidate_frame_count"], 2)
                self.assertEqual(result["changed_candidate_pairs"], 1)
                self.assertEqual(result["identical_candidate_pairs"], 0)
                self.assertTrue(result["embedded_png_scanlines_and_chunk_crcs_valid"])
                self.assertFalse(result["original_inp_playback_verified"])

    def test_recompressed_and_refiltered_identical_pixels(self):
        frames = [
            synthetic_png(filter_mode=0, compression=1),
            synthetic_png(filter_mode=4, compression=9),
            synthetic_png(filter_mode=2, compression=6),
        ]
        self.store(frames)
        result = mng.audit(self.path, minimum_frames=3)
        self.assertEqual(result["identical_candidate_pairs"], 2)
        self.assertEqual(result["changed_candidate_pairs"], 0)
        self.assertIsNone(result["first_changed_candidate_pair"])

    def test_detect_changed_candidate_pairs_with_middle_duplicate(self):
        self.store([synthetic_png(), synthetic_png((255, 10, 1)),
                    synthetic_png((255, 10, 1)), synthetic_png()])
        result = mng.audit(self.path, minimum_frames=4)
        self.assertEqual(result["candidate_frame_count"], 4)
        self.assertEqual(result["changed_candidate_pairs"], 2)
        self.assertEqual(result["identical_candidate_pairs"], 1)

    def test_missing_mng_signature(self):
        self.store()
        raw = self.path.read_bytes()
        self.path.write_bytes(b"not mng!" + raw[8:])
        with self.assertRaisesRegex(ValueError, "signature"):
            mng.audit(self.path)

    def test_bad_crc_is_rejected(self):
        self.store()
        raw = bytearray(self.path.read_bytes())
        raw[60] ^= 0xFF
        self.path.write_bytes(raw)
        with self.assertRaisesRegex(ValueError, "CRC"):
            mng.audit(self.path)

    def test_truncated_frame_or_missing_mend(self):
        self.store(end=False)
        with self.assertRaisesRegex(ValueError, "truncated"):
            mng.audit(self.path)

    def test_mng_trailing_data_refused(self):
        self.store()
        with self.path.open("ab") as handle:
            handle.write(b"untrusted")
        with self.assertRaisesRegex(ValueError, "trailing"):
            mng.audit(self.path)

    def test_mng_wrong_frame_dimensions_refused(self):
        self.store(w=3)
        with self.assertRaisesRegex(ValueError, "dimensions"):
            mng.audit(self.path)

    def test_bad_mhdr_unknown_mng_layout(self):
        self.store(ticks=0)
        with self.assertRaisesRegex(ValueError, "MHDR"):
            mng.audit(self.path)

    def test_extra_global_chunk_refused(self):
        self.store()
        raw = self.path.read_bytes()
        mng_header_end = 8 + 12 + 28
        self.path.write_bytes(raw[:mng_header_end] +
                              chunk(b"FRAM") + raw[mng_header_end:])
        with self.assertRaisesRegex(ValueError, "global"):
            mng.audit(self.path)

    def test_nested_ihdr_refused(self):
        self.store()
        raw = self.path.read_bytes()
        # First PNG starts immediately after MHDR and its first chunk is IHDR.
        pos = 8 + 12 + 28
        ihdr_chunk = raw[pos:pos + 25]
        self.path.write_bytes(raw[:pos + 25] + ihdr_chunk + raw[pos + 25:])
        with self.assertRaisesRegex(ValueError, "nested"):
            mng.audit(self.path)

    def test_broken_embedded_png_deflate_rejected(self):
        bad_png = (mng.png.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB",
                   2, 2, 8, 2, 0, 0, 0)) +
                   chunk(b"IDAT", b"not-zlib") + chunk(b"IEND"))
        self.store([synthetic_png(), bad_png])
        with self.assertRaisesRegex(ValueError, "corrupted PNG"):
            mng.audit(self.path)

    def test_minimum_frame_limit_refused(self):
        self.store()
        with self.assertRaisesRegex(ValueError, "fewer candidate"):
            mng.audit(self.path, minimum_frames=3)
        for value in (0, 1, 3602, True, "2"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "minimum"):
                mng.audit(self.path, minimum_frames=value)

    def test_invalid_private_path_or_symlink(self):
        self.store()
        alias = self.root / "alias.mng"
        alias.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, "private regular"):
            mng.audit(alias)
        with self.assertRaisesRegex(ValueError, "private regular"):
            mng.audit(mng.gate.ROOT / "fake-mng.mng")

    def test_cli_private_exclusive_0600_receipt(self):
        self.store([synthetic_png(), synthetic_png((0, 1, 2))])
        report_path = self.root / "audit.json"
        code = mng.main(["--mng", str(self.path),
                         "--minimum-frames", "2", "--out", str(report_path)])
        self.assertEqual(code, 0)
        report = json.loads(report_path.read_text())
        self.assertEqual(report["candidate_frame_count"], 2)
        self.assertEqual(report_path.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.root), report_path.read_text())
        self.assertNotIn(".mng", report_path.read_text())
        with self.assertRaises(FileExistsError):
            mng.main(["--mng", str(self.path), "--out", str(report_path)])


if __name__ == "__main__":
    unittest.main()
