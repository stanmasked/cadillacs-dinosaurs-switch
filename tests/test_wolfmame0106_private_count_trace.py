"""Stage290 synthetic-only tests. No original game, INP/WLF, or captured pixels."""
import hashlib
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import wolfmame0106_private_count_trace as counts
from tools import wolfmame0106_private_mng_capture as capture
from tools import wolfmame0106_private_mng_audit as mng
from tools import mame0106_stage290_trace_patch as patcher


def chunk(tag, payload=b""):
    return (struct.pack(">I", len(payload)) + tag + payload +
            struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))


def fake_mng(n):
    mhdr = struct.pack(">7I", 2, 2, 60, 0, 0, 0, 0x41)
    frames = []
    for i in range(n):
        rgb = (i % 251, (i * 7) % 249, (i * 5) % 247)
        scanlines = (b"\x00" + bytes(rgb) * 2) * 2
        frame = (mng.png.PNG_SIG +
                 chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0)) +
                 chunk(b"IDAT", zlib.compress(scanlines)) + chunk(b"IEND"))
        frames.append(frame[len(mng.png.PNG_SIG):])
    return mng.MNG_SIGNATURE + chunk(b"MHDR", mhdr) + b"".join(frames) + chunk(b"MEND")


class CounterTraceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dino290-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.mng = self.root / "capture.mng"
        self.trace = self.root / "counters.csv"
        self.receipt = self.root / "capture.json"
        self.write()

    def write(self, *, n=20, start=100, count_fn=None):
        self.mng.write_bytes(fake_mng(n))
        data = [counts.HEADER]
        for i in range(n):
            a, b = (100 + i, (100 + i) * 31) if count_fn is None else count_fn(i)
            data.append(f"{start+i},{a},{b}")
        self.trace.write_bytes(("\n".join(data) + "\n").encode("ascii"))
        rec = capture._empty_report(n, start)
        rec.update({
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
            "candidate_video_frames": n,
            "capture_mng_sha256": hashlib.sha256(self.mng.read_bytes()).hexdigest(),
            "capture_mng_byte_count": self.mng.stat().st_size,
            "candidate_count_trace_retained_privately": True,
            "candidate_count_trace_sha256": hashlib.sha256(self.trace.read_bytes()).hexdigest(),
            "candidate_count_trace_byte_count": self.trace.stat().st_size,
        })
        self.receipt.write_text(json.dumps(rec))

    def update_receipt(self, **kwargs):
        x = json.loads(self.receipt.read_text())
        x.update(kwargs)
        self.receipt.write_text(json.dumps(x))

    def rebind_trace(self):
        raw = self.trace.read_bytes()
        self.update_receipt(candidate_count_trace_sha256=hashlib.sha256(raw).hexdigest(),
                            candidate_count_trace_byte_count=len(raw))

    def test_structurally_valid_count_trace_is_not_gameplay_proof(self):
        result = counts.audit(self.mng, self.receipt, self.trace)
        self.assertEqual(result["status"], counts.STATUS)
        self.assertEqual(result["audited_callback_rows"], 20)
        self.assertEqual(result["candidate_callback_minus_port0_counter_spread"], 0)
        self.assertTrue(result["counter_trace_bytes_bound_to_receipt"])
        self.assertFalse(result["exact_input_video_alignment_verified"])
        self.assertFalse(result["source_wolfmame_binary_provenance_verified"])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("sha256", json.dumps(result))

    def test_trace_hash_or_byte_count_mismatch_refused(self):
        self.update_receipt(candidate_count_trace_sha256="0"*64)
        with self.assertRaises(ValueError):
            counts.audit(self.mng, self.receipt, self.trace)
        self.write()
        self.update_receipt(candidate_count_trace_byte_count=9999)
        with self.assertRaises(ValueError):
            counts.audit(self.mng, self.receipt, self.trace)

    def test_callback_gap_or_duplicate_refused_even_with_matching_hash(self):
        raw = self.trace.read_text().splitlines()
        raw[2] = raw[2].replace("101,", "100,", 1)
        self.trace.write_text("\n".join(raw) + "\n")
        self.rebind_trace()
        with self.assertRaisesRegex(ValueError, "misordered"):
            counts.audit(self.mng, self.receipt, self.trace)

    def test_counter_regression_refused(self):
        self.write(count_fn=lambda i: (100 + i if i < 8 else 98, 3100 + i))
        with self.assertRaisesRegex(ValueError, "non-monotonic"):
            counts.audit(self.mng, self.receipt, self.trace)

    def test_static_counters_not_accepted(self):
        self.write(count_fn=lambda i: (100, 3100))
        with self.assertRaisesRegex(ValueError, "increasing"):
            counts.audit(self.mng, self.receipt, self.trace)

    def test_mng_container_corruption_detected_after_receipt_binding(self):
        raw = bytearray(self.mng.read_bytes())
        raw[70] ^= 32
        self.mng.write_bytes(raw)
        self.update_receipt(capture_mng_sha256=hashlib.sha256(raw).hexdigest(),
                            capture_mng_byte_count=len(raw))
        with self.assertRaises(ValueError):
            counts.audit(self.mng, self.receipt, self.trace)

    def test_non_private_symlink_refused(self):
        alias = self.root / "alias.csv"
        alias.symlink_to(self.trace)
        with self.assertRaises(ValueError):
            counts.audit(self.mng, self.receipt, alias)

    def test_missing_rows_refused(self):
        self.trace.write_text(counts.HEADER + "\n100,100,3100\n")
        self.rebind_trace()
        with self.assertRaises(ValueError):
            counts.audit(self.mng, self.receipt, self.trace)

    def test_clean_private_cli_receipt_has_no_sensitive_payload(self):
        out = self.root / "stage290.json"
        args = ["--mng", str(self.mng), "--trace", str(self.trace),
                "--capture-receipt", str(self.receipt), "--out", str(out)]
        self.assertEqual(counts.main(args), 0)
        self.assertEqual(out.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(out.read_text())["status"], counts.STATUS)
        self.assertNotIn(str(self.root), out.read_text())
        with self.assertRaises(FileExistsError):
            counts.main(args)

    def test_legacy_receipt_without_trace_refused(self):
        self.update_receipt(candidate_count_trace_retained_privately=False)
        with self.assertRaises(ValueError):
            counts.audit(self.mng, self.receipt, self.trace)

    def test_patcher_rejects_missing_or_duplicated_source_anchors(self):
        self.assertEqual(patcher._replace_once("a needle b", "needle", "new", "demo"),
                         "a new b")
        with self.assertRaises(ValueError):
            patcher._replace_once("none", "needle", "new", "demo")
        with self.assertRaises(ValueError):
            patcher._replace_once("needle needle", "needle", "new", "demo")


if __name__ == "__main__":
    unittest.main()
