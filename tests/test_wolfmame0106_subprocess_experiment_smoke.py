"""Stage293 ROM-free real-subprocess contract smoke tests.

The executable spawned by Stage286/292 is an ARTIFICIAL Python stand-in that
writes tiny self-generated MNG frames and numeric traces. It is not MAME,
WolfMAME, dino, or evidence of original-game playback.
"""
import os
import json
import tempfile
import unittest
from pathlib import Path

from tools import wolfmame0106_private_mng_capture as capture
from tools import wolfmame0106_private_two_window_experiment as experiment

MOCK_EXECUTABLE = r'''#!/usr/bin/env python3
"""SYNTHETIC MAME CLI stand-in: generates only artificial data."""
import os
import struct
import sys
import zlib
from pathlib import Path


def chunk(kind, body=b""):
    return (struct.pack(">I", len(body)) + kind + body +
            struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff))


def png_frame(index):
    rgb = bytes((index % 251, (index * 3) % 253, (index * 7) % 239))
    rows = (b"\x00" + rgb * 2) * 2
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND")
    )
    return png[8:]


def option(args, name):
    return args[args.index(name) + 1]


def main():
    args = sys.argv[1:]
    start = int(option(args, "-mngstartframe"))
    count = int(option(args, "-mngframes"))
    name = option(args, "-mngwrite")
    mode = os.environ.get("DINO293_MOCK_MODE", "normal")
    if name != "stage286":
        return 3
    if not all(x in args for x in
               ("-playback", "-rompath", "-frames_to_run", "-mngwrite")):
        return 4
    if int(option(args, "-frames_to_run")) != start + count:
        return 5
    if mode == "no-mng":
        return 0
    header = struct.pack(">7I", 2, 2, 60, 0, 0, 0, 0x41)
    data = b"\x8aMNG\r\n\x1a\n" + chunk(b"MHDR", header)
    for frame in range(start, start + count):
        data += png_frame(frame)
    data += chunk(b"MEND")
    if mode == "corrupt-mng":
        data = data[:-4] + b"\x00\x00\x00\x00"
    Path(name + ".mng").write_bytes(data)
    if "-mngcounttrace" in args and option(args, "-mngcounttrace") == "1":
        if mode != "no-trace":
            rows = ["callback_index,first_port_reads,playback_words"]
            for frame in range(start, start + count):
                port0 = frame + 1
                words = 31 * port0
                if mode == "counter-diverge" and start == 120 and frame == 130:
                    port0 += 1
                    words += 31
                rows.append(f"{frame},{port0},{words}")
            Path("stage290-mng-counts.csv").write_bytes(
                ("\n".join(rows) + "\n").encode("ascii"))
    if mode == "nonzero":
        return 7
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


@unittest.skipIf(os.name == "nt", "POSIX mock executable uses shebang/chmod")
class SubprocessSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dino293-rom-free-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.exe = self.root / "synthetic-emulator"
        self.exe.write_text(MOCK_EXECUTABLE, encoding="utf-8")
        self.exe.chmod(0o700)
        self.inp = self.root / "synthetic.inp"
        self.wlf = self.root / "synthetic.wlf"
        # These are NOT real INP/WLF records: structural preflight is
        # explicitly stubbed, letting us test actual subprocess handling.
        self.inp.write_bytes(b"ARTIFICIAL INP: no original inputs")
        self.wlf.write_bytes(b"ARTIFICIAL WLF: no original inputs")
        self.rom_dir = self.root / "empty-synthetic-rom-directory"
        self.rom_dir.mkdir()
        self.out_dir = self.root / "experiment"
        self.original_mode = os.environ.get("DINO293_MOCK_MODE")
        self.addCleanup(self.restore_mode)

    def restore_mode(self):
        if self.original_mode is None:
            os.environ.pop("DINO293_MOCK_MODE", None)
        else:
            os.environ["DINO293_MOCK_MODE"] = self.original_mode

    @staticmethod
    def synthetic_preflight(exe, roms, inp, wlf):
        return {
            "input_record_count": 500,
            "recording_wolfmame_family_0_106": True,
            "emulator_help_reports_mame_0_106": True,
            "dino_rom_verifyroms_passed": True,
        }

    @staticmethod
    def synthetic_metadata(inp, wlf):
        return 500, "0.106 synthetic-test-only", 7

    def real_capture(self, emulator, rom_dir, inp, wlf, **kwargs):
        # Does not mock the subprocess, filesystem or MNG auditing code.
        return capture.capture(
            emulator, rom_dir, inp, wlf, verifier=self.synthetic_preflight,
            **kwargs)

    def run_two(self):
        return experiment.run_experiment(
            self.exe, self.rom_dir, self.inp, self.wlf,
            self.out_dir,
            first_start=100, frames=40, shift=20, seconds=15,
            metadata_fn=self.synthetic_metadata, capture_fn=self.real_capture)

    def test_full_process_launch_and_private_retention_to_dual_match(self):
        result = self.run_two()
        self.assertEqual(result["status"], experiment.MATCH)
        self.assertEqual(result["overlap_callbacks_compared"], 20)
        self.assertTrue(result["first_capture_complete"])
        self.assertTrue(result["second_capture_complete"])
        self.assertTrue(result["cross_capture_evidence_checked"])
        self.assertEqual(len(list(self.out_dir.iterdir())), 7)
        for expected in (
                "first.mng", "first-counts.csv", "first-receipt.json",
                "second.mng", "second-counts.csv", "second-receipt.json",
                "stage292-summary.json"):
            self.assertTrue((self.out_dir / expected).is_file())
            self.assertEqual((self.out_dir / expected).stat().st_mode & 0o777, 0o600)
        for key in (
                "independent_emulator_runs_authenticated",
                "original_inp_playback_verified",
                "wolfmame_binary_provenance_verified",
                "exact_input_record_to_video_callback_mapping_verified",
                "original_gameplay_parity_verified",
                "physical_nintendo_switch_tested"):
            self.assertIs(result[key], False)
        public_summary = (self.out_dir / "stage292-summary.json").read_text()
        self.assertNotIn(str(self.root), public_summary)
        self.assertNotIn("sha256", public_summary)
        self.assertNotIn("synthetic-emulator", public_summary)

    def test_real_subprocess_missing_trace_blocks_first_capture(self):
        os.environ["DINO293_MOCK_MODE"] = "no-trace"
        result = self.run_two()
        self.assertEqual(result["status"], experiment.BLOCKED_FIRST)
        self.assertFalse((self.out_dir / "second-receipt.json").exists())
        first = json.loads((self.out_dir / "first-receipt.json").read_text())
        self.assertEqual(first["status"], "COUNT_TRACE_FILE_NOT_CREATED")
        self.assertTrue((self.out_dir / "stage292-summary.json").exists())

    def test_real_subprocess_nonzero_exit_fails_closed(self):
        os.environ["DINO293_MOCK_MODE"] = "nonzero"
        result = self.run_two()
        self.assertEqual(result["status"], experiment.BLOCKED_FIRST)
        first = json.loads((self.out_dir / "first-receipt.json").read_text())
        self.assertEqual(first["status"], "CANDIDATE_MNG_VALID_BUT_PROCESS_EXIT_NONZERO")
        self.assertEqual(first["process_exit_code"], 7)

    def test_real_subprocess_missing_mng_blocks_first_capture(self):
        os.environ["DINO293_MOCK_MODE"] = "no-mng"
        result = self.run_two()
        self.assertEqual(result["status"], experiment.BLOCKED_FIRST)
        first = json.loads((self.out_dir / "first-receipt.json").read_text())
        self.assertEqual(first["status"], "CAPTURE_FILE_NOT_CREATED")

    def test_real_subprocess_corrupt_mng_does_not_publish_pixels(self):
        os.environ["DINO293_MOCK_MODE"] = "corrupt-mng"
        result = self.run_two()
        self.assertEqual(result["status"], experiment.BLOCKED_FIRST)
        first = json.loads((self.out_dir / "first-receipt.json").read_text())
        self.assertNotEqual(first["status"], "CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED")
        report = (self.out_dir / "stage292-summary.json").read_text()
        self.assertNotIn(str(self.root), report)

    def test_real_subprocess_counter_divergence_with_equal_pixels(self):
        os.environ["DINO293_MOCK_MODE"] = "counter-diverge"
        result = self.run_two()
        self.assertEqual(result["status"], experiment.NONMATCH)
        self.assertEqual(result["dual_check_status"], "PIXELS_MATCH_INPUT_READ_COUNTERS_DIVERGE_UNAUTHENTICATED")
        self.assertEqual(result["overlap_port0_count_mismatches"], 1)
        self.assertEqual(result["overlap_word_count_mismatches"], 1)

    def test_no_trace_mode_when_not_requested(self):
        # Confirm the optional instrumentation flag is not passed implicitly.
        report = capture.capture(
            self.exe, self.rom_dir, self.inp, self.wlf,
            frames=40, start_frame=100, seconds=15,
            capture_out=self.root / "mng-only.mng",
            verifier=self.synthetic_preflight)
        self.assertEqual(report["status"], "CANDIDATE_MNG_VALID_PLAYBACK_UNAUTHENTICATED")
        self.assertFalse(report["candidate_count_trace_retained_privately"])
        self.assertIsNone(report["candidate_count_trace_sha256"])


if __name__ == "__main__":
    unittest.main()
