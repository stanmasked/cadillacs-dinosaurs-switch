"""Stage295 ROM-free actual-MAME synthetic probe safety/regression tests."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import mame0106_synthetic_runtime_probe_295 as probe


class SyntheticRealMameProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dino295-probe-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_missing_valid_rom_loader_response_blocks_gameplay(self):
        with patch.object(probe, "_invoke", return_value=(0, "not verified")) as stub:
            result = probe.probe(self.root / "no-mame.exe", self.root)
        self.assertEqual(result["status"], "BLOCKED_SYNTHETIC_ROM_LOADER")
        self.assertFalse(result["synthetic_minivader_rom_verification"])
        self.assertFalse(result["original_dino_rom_or_inp_used"])
        self.assertEqual(stub.call_count, 1)

    def test_accepted_rom_loader_does_not_claim_recording_without_data(self):
        with patch.object(probe, "_invoke", side_effect=[
                (0, "romset minivadr is good\n"),
                (0, "process exited normally\n"),
        ]) as stub:
            result = probe.probe(self.root / "synthetic.exe", self.root)
        self.assertTrue(result["synthetic_minivader_rom_verification"])
        self.assertEqual(result["status"], "BLOCKED_SYNTHETIC_RECORDING_WINDOW_OR_GUI")
        self.assertFalse(result["synthetic_mame_recording_executed"])
        self.assertFalse(result["original_gameplay_verified"])
        self.assertEqual(stub.call_count, 2)

    def test_nonzero_recording_process_is_not_a_success(self):
        with patch.object(probe, "_invoke", side_effect=[
            (0, "romset minivadr is good\n"), (17, "blocked window"),
        ]):
            result = probe.probe(self.root / "synthetic.exe", self.root)
        self.assertEqual(result["status"], "BLOCKED_SYNTHETIC_RECORDING_WINDOW_OR_GUI")
        self.assertFalse(result["synthetic_mame_playback_executed"])
        self.assertFalse(result["exact_input_video_alignment_verified"])

    def test_trace_requires_exact_callback_count_and_monotonicity(self):
        path = self.root / "test.csv"
        header = probe.TRACE_HEAD
        body = "\n".join(f"{100+i},{101+i},{(101+i)*31}" for i in range(24))
        path.write_text(header + "\n" + body + "\n")
        self.assertTrue(probe._check_trace(path, 100, 24))
        self.assertFalse(probe._check_trace(path, 101, 24))
        self.assertFalse(probe._check_trace(path, 100, 23))
        path.write_text(header + "\n" + body.replace("112,113,3503", "112,1,31") + "\n")
        self.assertFalse(probe._check_trace(path, 100, 24))

    def test_trace_audit_reports_only_aggregate_counter_advancement(self):
        path = self.root / "test.csv"
        rows = ["callback_index,first_port_reads,playback_words"]
        rows += [f"{10+i},{100+i},{300+5*i}" for i in range(24)]
        path.write_text("\n".join(rows) + "\n", encoding="ascii")
        summary = probe._audit_trace(path, 10, 24)
        self.assertEqual(summary["rows"], 24)
        self.assertEqual(summary["first_callback"], 10)
        self.assertEqual(summary["last_callback"], 33)
        self.assertTrue(summary["first_port_reads_advanced"])
        self.assertTrue(summary["playback_words_advanced"])
        self.assertEqual(summary["first_port_read_delta"], 23)
        self.assertEqual(summary["playback_word_delta"], 115)
        self.assertNotIn("100", str(summary))
        self.assertNotIn("300", str(summary))

    def test_trace_audit_rejects_integer_fields_over_unsigned_64_bit_width(self):
        path = self.root / "oversized.csv"
        rows = ["callback_index,first_port_reads,playback_words"]
        rows += [f"{10+i},{100+i},{300+5*i}" for i in range(24)]
        rows[1] = "10," + ("9" * 21) + ",300"
        path.write_text("\n".join(rows) + "\n", encoding="ascii")
        self.assertIsNone(probe._audit_trace(path, 10, 24))

    def test_static_counters_are_structural_but_not_progress_evidence(self):
        path = self.root / "static.csv"
        rows = ["callback_index,first_port_reads,playback_words"]
        rows += [f"{10+i},100,300" for i in range(24)]
        path.write_text("\n".join(rows) + "\n", encoding="ascii")
        summary = probe._audit_trace(path, 10, 24)
        self.assertIsNotNone(summary)
        self.assertFalse(summary["first_port_reads_advanced"])
        self.assertFalse(summary["playback_words_advanced"])
        self.assertEqual(summary["first_port_read_delta"], 0)
        self.assertEqual(summary["playback_word_delta"], 0)

    def _probe_with_synthetic_trace(self, *, static=False):
        calls = []

        def runner(_exe, _argv, cwd, **_kwargs):
            calls.append(True)
            if len(calls) == 1:
                return 0, "romset minivadr is good\n"
            if len(calls) == 2:
                (Path(cwd) / "inp" / "test295.inp").write_bytes(bytes(64))
                return 0, "synthetic recording complete"
            (Path(cwd) / "test295-replay.mng").write_bytes(b"synthetic MNG placeholder")
            rows = [probe.TRACE_HEAD]
            for i in range(24):
                port0, words = (100, 300) if static else (100 + i, 300 + 5 * i)
                rows.append(f"{10+i},{port0},{words}")
            (Path(cwd) / "stage290-mng-counts.csv").write_text(
                "\n".join(rows) + "\n", encoding="ascii")
            return 0, "synthetic replay complete"

        with patch.object(probe, "_invoke", side_effect=runner), \
             patch("tools.wolfmame0106_private_mng_audit.audit",
                   return_value={"candidate_frame_count": 24}):
            return probe.probe(self.root / "fake.exe", self.root)

    def test_full_probe_blocks_structurally_valid_but_static_counters(self):
        result = self._probe_with_synthetic_trace(static=True)
        self.assertEqual(result["status"], "BLOCKED_SYNTHETIC_PLAYBACK_TRACE_COUNTERS_STATIC")
        # The emulator did run and exit zero; the independent trace gate
        # blocks acceptance because its counters did not advance.
        self.assertTrue(result["synthetic_mame_playback_executed"])
        self.assertTrue(result["synthetic_replay_process_exit_zero"])
        self.assertEqual(result["synthetic_trace_audited_rows"], 24)
        self.assertFalse(result["synthetic_trace_first_port_reads_advanced"])
        self.assertFalse(result["synthetic_trace_playback_words_advanced"])
        self.assertEqual(result["synthetic_trace_first_port_read_delta"], 0)
        self.assertEqual(result["synthetic_trace_playback_word_delta"], 0)

    def test_full_probe_accepts_mng_only_when_both_counters_advance(self):
        result = self._probe_with_synthetic_trace()
        self.assertEqual(result["status"], "SYNTHETIC_MINIVADER_MAME_VIDEO_AND_INPUT_READ_CONFIRMED")
        self.assertTrue(result["synthetic_mame_playback_executed"])
        self.assertEqual(result["synthetic_mng_audited_frames"], 24)
        self.assertEqual(result["synthetic_trace_audited_rows"], 24)
        self.assertTrue(result["synthetic_trace_first_port_reads_advanced"])
        self.assertTrue(result["synthetic_trace_playback_words_advanced"])
        self.assertEqual(result["synthetic_trace_first_port_read_delta"], 23)
        self.assertEqual(result["synthetic_trace_playback_word_delta"], 115)

    def test_real_recording_then_replay_nonzero_exit_is_distinct_block(self):
        calls = []
        def runner(_exe, _argv, cwd, **_kwargs):
            calls.append(True)
            if len(calls) == 1:
                return 0, "romset minivadr is good\n"
            if len(calls) == 2:
                (Path(cwd) / "inp" / "test295.inp").write_bytes(bytes(64))
                return 0, "recorded artificial frames"
            return 3, "GUI unavailable"
        with patch.object(probe, "_invoke", side_effect=runner):
            result = probe.probe(self.root / "fake.exe", self.root)
        self.assertEqual(result["status"], "BLOCKED_SYNTHETIC_PLAYBACK_PROCESS_EXIT")
        self.assertTrue(result["synthetic_mame_recording_executed"])
        self.assertFalse(result["synthetic_replay_process_exit_zero"])
        self.assertFalse(result["synthetic_replay_trace_file_present"])
        self.assertFalse(result["original_gameplay_verified"])

    def test_replay_zero_exit_missing_video_is_not_conflated_with_trace(self):
        calls = []
        def runner(_exe, _argv, cwd, **_kwargs):
            calls.append(True)
            if len(calls) == 1:
                return 0, "romset minivadr is good\n"
            if len(calls) == 2:
                (Path(cwd) / "inp" / "test295.inp").write_bytes(bytes(64))
                return 0, ""
            return 0, ""
        with patch.object(probe, "_invoke", side_effect=runner):
            result = probe.probe(self.root / "fake.exe", self.root)
        self.assertEqual(result["status"], "BLOCKED_SYNTHETIC_PLAYBACK_MNG_MISSING")
        self.assertTrue(result["synthetic_replay_process_exit_zero"])
        self.assertFalse(result["synthetic_replay_mng_file_present"])

    def test_mng_failure_codes_are_fixed_and_do_not_echo_raw_errors(self):
        cases = {
            "invalid MNG signature": "INVALID_SIGNATURE",
            "truncated MNG chunk body": "TRUNCATED_STREAM",
            "MNG chunk CRC mismatch": "CHUNK_CRC_MISMATCH",
            "MNG/PNG image dimensions differ": "DIMENSION_MISMATCH",
            "unexpected global chunk in MAME 0.106 MNG": "UNEXPECTED_GLOBAL_CHUNK",
            "invalid or non-MAME-0.106 MHDR": "INVALID_MHDR",
            "unsupported PNG dimensions/mode": "UNSUPPORTED_PNG_MODE",
            "corrupted PNG image": "INVALID_EMBEDDED_PNG",
            "candidate MNG must be a private regular file": "INVALID_PRIVATE_PATH",
            "unanticipated parser failure at /private/user/path": "UNCLASSIFIED_AUDIT_ERROR",
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                code = probe._classify_mng_audit_error(ValueError(message))
                self.assertEqual(code, expected)
                self.assertNotIn("/private/user/path", code)
                self.assertNotIn(message, code)

    def test_full_probe_does_not_use_or_export_any_original_game_material(self):
        with patch.object(probe, "_invoke", return_value=(None, "")):
            result = probe.probe(self.root / "none.exe", self.root)
        for key in ("original_dino_rom_or_inp_used", "original_gameplay_verified",
                    "wolfmame_binary_authenticity_verified",
                    "exact_input_video_alignment_verified",
                    "physical_nintendo_switch_tested"):
            self.assertFalse(result[key])
        self.assertNotIn(str(self.root), str(result))


if __name__ == "__main__":
    unittest.main()
