"""Stage297: synthetic-only repeatability tests (no real game or Z80 assets)."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tools import mame0106_synthetic_dual_replay_297 as dual


def digests(start, *, n=dual.FRAME_COUNT):
    return [hashlib.sha256(f"artificial-pixel-{k}".encode()).digest()
            for k in range(start, start + n)]


def counters(start, *, n=dual.FRAME_COUNT):
    return [(k + 2, (k + 2) * 31) for k in range(start, start + n)]


class Stage297SyntheticDualReplayTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="dino297-rom-free-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def compare(self, **changes):
        a, ac = digests(10), counters(10)
        b, bc = digests(18), counters(18)
        for key, arr in (("a", a), ("ac", ac), ("b", b), ("bc", bc)):
            if key in changes:
                arr[:] = changes[key]
        return dual.compare_windows(a, ac, b, bc,
                                    first_start=changes.get("first_start", 10),
                                    second_start=changes.get("second_start", 18))

    def test_matching_dynamic_overlapping_callbacks_are_only_synthetic_evidence(self):
        result = self.compare()
        self.assertEqual(result["status"], dual.MATCH)
        self.assertEqual(result["overlap_frames_compared"], 16)
        self.assertEqual(result["matching_normalized_pixel_frames"], 16)
        self.assertEqual(result["matching_port0_read_counts"], 16)
        self.assertEqual(result["matching_total_playback_word_counts"], 16)
        self.assertTrue(result["overlap_contains_dynamic_video"])
        self.assertTrue(result["overlap_counters_advance"])
        self.assertNotIn(str(self.root), json.dumps(result))
        self.assertNotIn("sha256", json.dumps(result))

    def test_pixel_divergence_detected_even_if_input_counts_match(self):
        altered = digests(18)
        altered[5] = b"\xff" * 32
        result = self.compare(b=altered)
        self.assertEqual(result["status"], dual.NO_MATCH)
        self.assertEqual(result["matching_normalized_pixel_frames"], 15)
        self.assertEqual(result["matching_port0_read_counts"], 16)

    def test_port0_divergence_does_not_hide_behind_identical_pixels(self):
        shifted = counters(18)
        shifted[5] = (shifted[5][0]+1, shifted[5][1])
        result = self.compare(bc=shifted)
        self.assertEqual(result["status"], dual.NO_MATCH)
        self.assertEqual(result["matching_port0_read_counts"], 15)
        self.assertEqual(result["matching_total_playback_word_counts"], 16)
        self.assertEqual(result["first_counter_mismatch_callback"], 23)

    def test_word_counter_divergence_separately_reported(self):
        changed = counters(18)
        changed[8] = (changed[8][0], changed[8][1]+1)
        result = self.compare(bc=changed)
        self.assertEqual(result["status"], dual.NO_MATCH)
        self.assertEqual(result["matching_total_playback_word_counts"], 15)

    def test_identical_static_video_is_not_success(self):
        same = b"0" * 32
        result = self.compare(a=[same]*24, b=[same]*24)
        self.assertEqual(result["status"], dual.STATIC)
        self.assertFalse(result["overlap_contains_dynamic_video"])

    def test_static_counters_are_not_success(self):
        result = self.compare(ac=[(1, 1)]*24, bc=[(1, 1)]*24)
        self.assertEqual(result["status"], dual.STATIC)
        self.assertFalse(result["overlap_counters_advance"])

    def test_wrong_lengths_weak_overlap_and_fake_digests_fail_closed(self):
        with self.assertRaises(ValueError):
            self.compare(a=digests(10)[:23])
        with self.assertRaisesRegex(ValueError, "insufficient overlap"):
            self.compare(second_start=20)
        with self.assertRaises(ValueError):
            self.compare(b=[b"not-a-sha256"]*24)
        with self.assertRaises(ValueError):
            self.compare(bc=[(True, 9)]*24)

    def write_trace(self, start=10, count=24):
        path = self.root / "trace.csv"
        header = "callback_index,first_port_reads,playback_words\n"
        lines = "".join(f"{i},{i+2},{(i+2)*31}\n"
                        for i in range(start, start+count))
        path.write_text(header + lines, encoding="ascii")
        return path

    def test_trace_exact_callback_indices_and_monotone_counts(self):
        path = self.write_trace()
        self.assertEqual(dual.parse_trace(path, first_frame=10, count=24),
                         counters(10))
        with self.assertRaises(ValueError):
            dual.parse_trace(path, first_frame=11, count=24)
        with self.assertRaises(ValueError):
            dual.parse_trace(path, first_frame=10, count=23)

    def test_trace_rejects_nonmonotone_and_invalid_bytes(self):
        path = self.write_trace()
        src = path.read_text()
        src = src.replace("20,22,682", "20,1,1")
        path.write_text(src)
        with self.assertRaises(ValueError):
            dual.parse_trace(path, first_frame=10, count=24)
        path.write_bytes(b"\xff" + src.encode("ascii"))
        with self.assertRaises(ValueError):
            dual.parse_trace(path, first_frame=10, count=24)

    def test_trace_rejects_symlink_and_stale_invalid_trailing_row(self):
        path = self.write_trace()
        link = self.root / "link.csv"
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            dual.parse_trace(link, first_frame=10, count=24)
        path.write_text(path.read_text()+"34,35,1085\n")
        with self.assertRaises(ValueError):
            dual.parse_trace(path, first_frame=10, count=24)

    def fake_workflow(self, *, fail_second=False, mutate_second=False, omit_second_trace=False):
        calls = []
        def runner(_exe, args, cwd):
            args = list(args)
            calls.append(args)
            work = Path(cwd)
            if "-verifyroms" in args:
                return 0, "romset minivadr is good\n"
            if "-record" in args:
                (work / "inp" / "stage297.inp").write_bytes(bytes(128))
                return 0, ""
            start = int(args[args.index("-mngstartframe")+1])
            if "-mngcounttrace" not in args or "1" in args:
                return 9, ""
            name = args[args.index("-mngwrite")+1]
            if fail_second and start == 18:
                return 9, ""
            (work / f"{name}.mng").write_bytes(b"artificial MNG placeholder")
            if not (omit_second_trace and start == 18):
                fake = "".join(f"{i},{i+2},{(i+2)*31}\n"
                               for i in range(start, start+24))
                (work / dual.TRACE_NAME).write_text(dual.base.TRACE_HEAD+"\n"+fake)
            return 0, ""
        def auditor(path, minimum_frames=2, _private_frame_digests=None):
            start = 10 if "first" in Path(path).stem else 18
            simulated = digests(start)
            if mutate_second and start == 18:
                simulated[3] = b"f"*32
            _private_frame_digests.extend(simulated)
            return {"candidate_frame_count": 24}
        out = dual.run_synthetic_dual_replay(
            self.root / "synthetic-not-executable.exe", self.root,
            invoke=runner, audit=auditor)
        return out, calls

    def test_two_real_process_contracts_and_independent_trace_lifecycle(self):
        result, calls = self.fake_workflow()
        self.assertEqual(result["status"], dual.MATCH)
        self.assertEqual(len(calls), 4)
        self.assertEqual(result["first_mng_decoded_frames"], 24)
        self.assertEqual(result["second_mng_decoded_frames"], 24)
        self.assertEqual(result["first_trace_rows"], 24)
        self.assertEqual(result["second_trace_rows"], 24)
        self.assertEqual(result["overlap_frames_compared"], 16)
        self.assertTrue(result["first_synthetic_replay_complete"])
        self.assertTrue(result["second_synthetic_replay_complete"])
        self.assertFalse(result["real_dino_rom_or_inp_used"])
        self.assertFalse(result["exact_input_video_causality_verified"])
        self.assertFalse(result["physical_nintendo_switch_tested"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_two_process_same_video_different_pixels_is_blocked(self):
        result, _ = self.fake_workflow(mutate_second=True)
        self.assertEqual(result["status"], dual.NO_MATCH)
        self.assertEqual(result["matching_normalized_pixel_frames"], 15)

    def test_second_process_failure_does_not_reuse_previous_trace(self):
        result, _ = self.fake_workflow(fail_second=True)
        self.assertEqual(result["status"], "BLOCKED_SYNTHETIC_SECOND_REPLAY")
        self.assertTrue(result["first_synthetic_replay_complete"])
        self.assertFalse(result["second_synthetic_replay_complete"])
        self.assertEqual(result["overlap_frames_compared"], 0)

    def test_missing_second_trace_is_not_mistaken_for_first_trace(self):
        result, _ = self.fake_workflow(omit_second_trace=True)
        self.assertEqual(result["status"], "BLOCKED_SYNTHETIC_SECOND_REPLAY")
        self.assertEqual(result["second_trace_rows"], 0)


if __name__ == "__main__":
    unittest.main()
