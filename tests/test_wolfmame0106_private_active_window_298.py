"""Stage298: entirely synthetic dino INP/WLF active window selection tests."""
import json
import struct
import tempfile
import unittest
from pathlib import Path

from tools import wolfmame0106_private_active_window_298 as active
from tools import wolfmame0106_private_two_window_experiment as experiment
from tools import wolfmame0106_private_mng_capture as capture
from tools import wolfmame0106_dino_input_reference as inp_ref


class PrivateActionWindow298Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dino298-no-game-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inp = self.root / "synthetic-dino.inp"
        self.wlf = self.root / "synthetic-dino.wlf"
        self.frames = 200
        self.make_fixture()

    def make_fixture(self, pulses=None, n=None):
        if n is None:
            n = self.frames
        if pulses is None:
            pulses = [
                (78, inp_ref.PORTS["p1"], 4),
                (86, inp_ref.PORTS["p1"], 5),
                (97, inp_ref.PORTS["p1"], 4),
            ]
        rows = [bytearray(b"\xff" * inp_ref.FRAME_BYTES)
                for _ in range(n)]
        for frame, offset, bit in pulses:
            rows[frame][offset] &= ~(1 << bit)
        head = bytearray(inp_ref.HEADER_BYTES)
        head[:4] = b"dino"
        head[16:20] = b"ABCD"
        self.inp.write_bytes(head + b"".join(rows))
        wlf = bytearray(598)
        wlf[:4] = b"WLF\x00"
        struct.pack_into("<I", wlf, 4, 9)
        wlf[148:153] = b"dino\x00"
        wlf[157:157 + len(b"0.106 (synthetic test)")] = b"0.106 (synthetic test)"
        wlf[248:252] = b"ABCD"
        struct.pack_into("<III", wlf, 256, 1000000, 1000003, n)
        self.wlf.write_bytes(wlf)

    def test_select_earliest_window_containing_three_action_edges(self):
        start, edges = active.select(
            self.inp, self.wlf, frames=40, shift=20, minimum_edges=3)
        self.assertEqual((start, edges), (58, 3))
        self.assertTrue(start + 20 <= 78)
        self.assertTrue(97 < start + 40)
        self.assertFalse((self.root / "stage292-summary.json").exists())

    def test_no_action_region_fails_without_misleading_claims(self):
        self.make_fixture(pulses=[])
        with self.assertRaisesRegex(ValueError, "sufficiently active"):
            active.select(self.inp, self.wlf, frames=40, shift=20)
        self.assertEqual(list(self.root.iterdir()).count(self.inp), 1)

    def test_weighted_gameplay_action_outranks_equal_movement_count(self):
        self.make_fixture(pulses=[
            (24, inp_ref.PORTS["p1"], 0),
            (30, inp_ref.PORTS["p1"], 1),
            (39, inp_ref.PORTS["p1"], 2),
            (78, inp_ref.PORTS["p1"], 4),
            (86, inp_ref.PORTS["p1"], 5),
            (97, inp_ref.PORTS["p1"], 4),
        ])
        self.assertEqual(active.select(self.inp, self.wlf,
                                       frames=40, shift=20), (58, 3))

    def test_player_two_transitions_can_select_active_window(self):
        self.make_fixture(pulses=[
            (30, inp_ref.PORTS["p2"], 4),
            (36, inp_ref.PORTS["p2"], 5),
            (40, inp_ref.PORTS["p2"], 4),
        ])
        start, edges = active.select(self.inp, self.wlf, frames=40, shift=20)
        self.assertEqual(edges, 3)
        self.assertTrue(start + 20 <= 30 and start + 40 > 40)

    def test_permanently_held_button_does_not_create_fake_rising_edges(self):
        pulses = [
            (i, inp_ref.PORTS["p1"], 4) for i in range(70, 140)
        ]
        self.make_fixture(pulses=pulses)
        with self.assertRaises(ValueError):
            active.select(self.inp, self.wlf, frames=40, shift=20,
                          minimum_edges=3)

    def test_short_or_malformed_recording_blocks_before_directory_created(self):
        self.inp.write_bytes(self.inp.read_bytes()[:-1])
        with self.assertRaises(ValueError):
            active.select(self.inp, self.wlf, frames=40, shift=20)

    def test_invalid_window_size_and_overlap_are_rejected(self):
        for frames, shift in ((40, 15), (40, 25), (25, 16),
                              (100, 101), (200, 20), (True, 20)):
            with self.subTest((frames, shift)):
                with self.assertRaises(ValueError):
                    active.select(self.inp, self.wlf, frames=frames, shift=shift)

    def test_minimum_edges_must_be_integer_within_budget(self):
        for bad in (True, 0, -1, 65, "3", 3.0):
            with self.subTest(bad):
                with self.assertRaises(ValueError):
                    active.select(self.inp, self.wlf, frames=40,
                                  shift=20, minimum_edges=bad)

    def test_source_inp_symlink_and_outside_repo_enforced(self):
        link = self.root / "symlink-inp.inp"
        link.symlink_to(self.inp)
        with self.assertRaises(ValueError):
            active.select(link, self.wlf, frames=40, shift=20)

    def test_non_dino_source_or_different_recording_tag_blocked(self):
        data = bytearray(self.wlf.read_bytes())
        data[248:252] = b"BAD!"
        self.wlf.write_bytes(data)
        with self.assertRaises(ValueError):
            active.select(self.inp, self.wlf, frames=40, shift=20)

    def test_coordinator_auto_selection_changes_requested_capture_indices(self):
        calls = []
        out = self.root / "new-private-experiment"
        def interrupted_capture(_emulator, _rom, _inp, _wlf, *,
                                frames, start_frame, seconds,
                                capture_out, trace_out):
            calls.append(start_frame)
            report = capture._empty_report(frames, start_frame)
            report["status"] = "CAPTURE_FILE_NOT_CREATED"
            return report
        result = experiment.run_experiment(
            "fake.exe", "fake-rom", self.inp, self.wlf, out,
            first_start=0, frames=40, shift=20, seconds=30,
            metadata_fn=lambda _i,_w: (200, "0.106 synthetic", 3),
            auto_window=True, minimum_edges=3,
            capture_fn=interrupted_capture,
        )
        self.assertEqual(result["status"], experiment.BLOCKED_FIRST)
        self.assertEqual(calls, [58])
        self.assertEqual(result["requested_first_callback_start"], 58)
        self.assertEqual(result["requested_second_callback_start"], 78)
        self.assertEqual(result["source_inferred_overlap_press_onsets"], 3)
        self.assertEqual(result["window_selection_strategy"],
                         "source_inferred_local_inp")
        self.assertFalse(result["wolfmame_input_signal_mapping_independently_verified"])
        public = (out / "stage292-summary.json").read_text()
        self.assertNotIn(str(self.root), public)
        self.assertNotIn("private_inp_sha256", public)
        self.assertNotIn("ABCD", public)

    def test_no_active_window_blocks_before_creating_experiment_folder(self):
        self.make_fixture(pulses=[])
        out = self.root / "must-not-exist"
        with self.assertRaises(ValueError):
            experiment.run_experiment(
                "fake.exe", "fake-rom", self.inp, self.wlf, out,
                first_start=0, frames=40, shift=20, seconds=30,
                metadata_fn=lambda _i,_w: (200, "0.106 synthetic", 3),
                auto_window=True,
            )
        self.assertFalse(out.exists())

    def test_coordinator_rejects_counterfeit_selector_result(self):
        out = self.root / "must-not-exist"
        for candidate in ((True, 5), (58, True), (58, 999999),
                          (58, 1), [-1, 4], (58, "4")):
            with self.subTest(candidate):
                with self.assertRaises(ValueError):
                    experiment.run_experiment(
                        "fake.exe", "fake", self.inp, self.wlf, out,
                        frames=40, shift=20, seconds=30,
                        metadata_fn=lambda _i,_w: (200, "0.106 synthetic", 3),
                        auto_window=True,
                        selector_fn=lambda *_a, **_kw: candidate)
                self.assertFalse(out.exists())

    def test_default_manual_window_behavior_is_preserved(self):
        calls = []
        out = self.root / "manual-case"
        def bad_capture(_emulator, _rom, _inp, _wlf, *,
                        frames, start_frame, seconds, capture_out, trace_out):
            calls.append(start_frame)
            return capture._empty_report(frames, start_frame)
        result = experiment.run_experiment(
            "fake.exe", "fake", self.inp, self.wlf, out,
            first_start=20, frames=40, shift=20, seconds=30,
            metadata_fn=lambda *_: (200, "0.106 synthetic", 3),
            capture_fn=bad_capture)
        self.assertEqual(calls, [20])
        self.assertEqual(result["window_selection_strategy"], "manual")
        self.assertIsNone(result["source_inferred_overlap_press_onsets"])

    def test_cli_opt_in_and_no_sensitive_strings_in_status(self):
        called = {}
        def delegate(*args, **kwargs):
            called.update(kwargs)
            return {"status": experiment.BLOCKED_FIRST}
        args = [
            "--emulator", "fake.exe", "--rom-dir", "fake",
            "--inp", str(self.inp), "--wlf", str(self.wlf),
            "--out-dir", str(self.root / "output"),
            "--auto-window", "--minimum-edges", "4",
        ]
        self.assertEqual(experiment.main(args, experiment=delegate), 2)
        self.assertIs(called["auto_window"], True)
        self.assertEqual(called["minimum_edges"], 4)


if __name__ == "__main__":
    unittest.main()
