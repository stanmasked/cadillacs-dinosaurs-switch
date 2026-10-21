"""Stage280 synthetic-only PNG continuity tests. No game ROM or real screenshots."""
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import wolfmame0106_private_visual_continuity as audit
from tools import wolfmame0106_replay_preflight as pre


def chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))


def sample_png(rgb=(12, 30, 90), *, filter_type=0, compression=6, padding=False):
    w, h = 2, 2
    plain = bytes(rgb) * w
    rows = []
    previous = bytes(len(plain))
    for y in range(h):
        saved = bytearray()
        for i, value in enumerate(plain):
            left = plain[i - 3] if i >= 3 else 0
            above = previous[i]
            corner = previous[i - 3] if i >= 3 else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            else:
                predictor = audit._paeth(left, above, corner)
            saved.append((value - predictor) & 255)
        rows.append(bytes([filter_type]) + saved)
        previous = plain
    raw = b"".join(rows)
    encoded = zlib.compress(raw, compression)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    extra = chunk(b"tEXt", b"source\x00synthetic") if padding else b""
    return pre.PNG_SIG + chunk(b"IHDR", ihdr) + extra + chunk(b"IDAT", encoded) + chunk(b"IEND", b"")


def request(indices):
    return {
        "schema": pre.REQUEST_SCHEMA,
        "status": "CAPTURE_REQUEST_NOT_CAPTURED",
        "recorded_input_frames": 300,
        "frame_indices": indices,
        "image_names": [f"frame-{i:08d}.png" for i in indices],
        "expected_capture_count": len(indices),
    }


class PrivateVisualContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dino280-synth-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.frames = self.root / "captures"
        self.frames.mkdir()

    def put(self, indices, overrides=None):
        overrides = overrides or {}
        for i in indices:
            (self.frames / f"frame-{i:08d}.png").write_bytes(
                overrides.get(i, sample_png())
            )

    def test_png_filters_normalize_to_identical_rgba(self):
        expected = audit.normalized_rgba(sample_png(filter_type=0))
        for mode in range(5):
            with self.subTest(mode=mode):
                self.assertEqual(audit.normalized_rgba(sample_png(filter_type=mode)), expected)

    def test_different_compression_and_metadata_are_same_pixels(self):
        a = sample_png(compression=1)
        b = sample_png(compression=9, padding=True)
        self.assertNotEqual(a, b)
        self.assertEqual(audit.normalized_rgba(a), audit.normalized_rgba(b))

    def test_actual_pixel_change_in_one_adjacent_pair(self):
        ids = [0, 1, 2, 30]
        self.put(ids, {2: sample_png((200, 30, 90))})
        out = audit.audit(request(ids), self.frames)
        self.assertEqual(out["adjacent_frame_pairs_compared"], 2)
        self.assertEqual(out["changed_pairs"], 1)
        self.assertEqual(out["unchanged_pairs"], 1)
        self.assertEqual(out["first_changed_candidate_pair"], [1, 2])
        self.assertEqual(out["changed_pixel_fraction_across_pairs"], 0.5)
        self.assertFalse(out["actual_inp_playback_verified"])
        self.assertFalse(out["emulator_provenance_verified"])

    def test_recompressed_duplicates_are_not_motion(self):
        ids = [0, 1, 2]
        self.put(ids, {
            0: sample_png(filter_type=0),
            1: sample_png(filter_type=4, compression=1),
            2: sample_png(filter_type=1, compression=9, padding=True),
        })
        out = audit.audit(request(ids), self.frames)
        self.assertEqual(out["status"], "ADJACENT_PIXELS_IDENTICAL_UNAUTHENTICATED")
        self.assertEqual(out["changed_pairs"], 0)

    def test_sparse_only_has_no_adjacent_pairs(self):
        ids = [0, 30, 60]
        self.put(ids, {60: sample_png((0, 0, 0))})
        out = audit.audit(request(ids), self.frames)
        self.assertEqual(out["status"], "NO_ADJACENT_PAIRS_TO_COMPARE")
        self.assertIsNone(out["changed_pixel_fraction_across_pairs"])

    def test_reject_duplicate_disordered_or_inconsistent_indices(self):
        for ids in ([0, 0], [2, 1], [0, 300], [-1, 1], [True, 1]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                audit.validate_request(request(ids))
        q = request([0, 1])
        q["image_names"] = ["frame-00000000.png", "frame-00000002.png"]
        with self.assertRaises(ValueError):
            audit.validate_request(q)

    def test_reject_malformed_provenance_claim(self):
        q = request([0, 1])
        q["status"] = "ORIGINAL_GAME_REPLAY_VERIFIED"
        with self.assertRaisesRegex(ValueError, "provenance"):
            audit.validate_request(q)

    def test_missing_extra_and_symlinked_capture_rejected(self):
        ids = [0, 1]
        self.put(ids)
        (self.frames / "extra.png").write_bytes(sample_png())
        with self.assertRaisesRegex(ValueError, "unexpected"):
            audit.audit(request(ids), self.frames)
        (self.frames / "extra.png").unlink()
        image = self.frames / "frame-00000001.png"
        image.unlink()
        image.symlink_to(self.frames / "frame-00000000.png")
        with self.assertRaisesRegex(ValueError, "ordinary"):
            audit.audit(request(ids), self.frames)

    def test_corrupt_png_rejected_before_pixel_comparison(self):
        ids = [0, 1]
        self.put(ids)
        bad = self.frames / "frame-00000001.png"
        damaged = bytearray(bad.read_bytes())
        damaged[25] ^= 0x10
        bad.write_bytes(damaged)
        with self.assertRaisesRegex(ValueError, "CRC"):
            audit.audit(request(ids), self.frames)

    def test_private_receipt_does_not_contain_paths_or_pixels(self):
        ids = [0, 1]
        self.put(ids, {1: sample_png((10, 20, 30))})
        manifest = self.root / "request.json"
        manifest.write_text(json.dumps(request(ids)))
        output = self.root / "summary.json"
        audit.main(["--request", str(manifest),
                    "--captures", str(self.frames), "--out", str(output)])
        result = json.loads(output.read_text())
        self.assertEqual(result["changed_pairs"], 1)
        self.assertNotIn(str(self.root), output.read_text())
        self.assertNotIn("frame-00000000.png", output.read_text())
        self.assertEqual(output.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError):
            audit.main(["--request", str(manifest),
                        "--captures", str(self.frames), "--out", str(output)])

    def test_reject_symlinked_request(self):
        ids = [0, 1]
        self.put(ids)
        manifest = self.root / "request.json"
        manifest.write_text(json.dumps(request(ids)))
        link = self.root / "alias.json"
        link.symlink_to(manifest)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            audit.main(["--request", str(link), "--captures", str(self.frames),
                        "--out", str(self.root / "output.json")])

    def test_crc_correct_transparency_chunk_explicitly_unsupported(self):
        png = sample_png()
        iend = png[-12:]
        with_transparency = png[:-12] + chunk(b"tRNS", b"\x00\x00\x00") + iend
        with self.assertRaisesRegex(ValueError, "tRNS"):
            audit.normalized_rgba(with_transparency)


if __name__ == "__main__":
    unittest.main()
