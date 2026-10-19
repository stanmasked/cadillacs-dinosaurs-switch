"""ROM-free exact carry interval tests; no fabricated NeXium clocks."""
import itertools
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from tools import nexium_guest_clock_phase_invariant as phase


def rows_from(ns, ticks):
    return [
        {"frame_id": i + 1, "elapsed_ns_capped": delay,
         "frame_game_ticks": games, "stress_game_ticks": games}
        for i, (delay, games) in enumerate(zip(ns, ticks))
    ]


def independent_brute_possible(ns, ticks, start):
    carry = start
    for delay, step in zip(ns, ticks):
        total = carry + delay * 60
        if total // phase.DENOM != step:
            return False
        carry = total % phase.DENOM
    return True


class Guest60HzClockPhaseInvariantTests(unittest.TestCase):
    def test_one_step_per_frame_for_900_ticks_has_exact_feasible_range(self):
        rows = rows_from([16666666] * 900, [1] * 900)
        result = phase.verify_phase(rows)
        self.assertEqual(result["initial_carry_min_inclusive"], 36000)
        self.assertEqual(result["initial_carry_max_inclusive"], 999999999)
        self.assertEqual(result["observed_stress_game_ticks"], 900)
        self.assertFalse(result["audio_service_release_timestamps_verified"])
        self.assertFalse(result["physical_speaker_audio_latency_verified"])

    def test_exact_small_phase_intersections_match_bruteforce(self):
        # Independent direct-division oracle checks multiple candidate
        # starting carries against all short frame/step sequences.
        scale = phase.DENOM // 10
        for length in (1, 2, 3, 4):
            for increments in itertools.product((0, 2, 5, 9), repeat=length):
                ns = [v * scale // 60 for v in increments]
                for ticks in itertools.product((0, 1), repeat=length):
                    rows = rows_from(ns, ticks)
                    starts = [x for x in range(0, phase.DENOM, scale)
                              if independent_brute_possible(ns, ticks, x)]
                    try:
                        result = phase.verify_phase(rows)
                    except ValueError:
                        self.assertEqual(starts, [])
                    else:
                        # Grid samples may miss narrow feasible intervals;
                        # check exact inclusion/exclusion of every sample.
                        for start in range(0, phase.DENOM, scale):
                            inside = (result["initial_carry_min_inclusive"] <=
                                      start <=
                                      result["initial_carry_max_inclusive"])
                            self.assertEqual(inside, start in starts)

    def test_zero_tick_render_frame_and_15_tick_capped_frame_are_feasible(self):
        rows = rows_from([10000000] * 5 + [250000000],
                         [0, 1, 0, 1, 1, 15])
        result = phase.verify_phase(rows)
        self.assertEqual(result["observed_stress_game_ticks"], 18)
        self.assertEqual(result["zero_game_tick_render_iterations"], 2)
        self.assertEqual(result["existing_scheduler_250ms_clamped_rows"], 1)
        self.assertEqual(result["frame_clock_cap_ns"], 250000000)

    def test_impossible_schedule_rejected_even_if_every_row_is_locally_valid(self):
        # At 15ms, one game step is individually possible. Ten in a
        # row demand an impossible initial phase >=1 billion units.
        one = rows_from([15000000], [1])
        self.assertEqual(phase.verify_phase(one)["status"],
                         "EXACT_GUEST_60HZ_CARRY_START_INTERVAL_EXISTS")
        with self.assertRaisesRegex(ValueError, "no feasible"):
            phase.verify_phase(rows_from([15000000] * 10, [1] * 10))
        with self.assertRaises(ValueError):
            phase.verify_phase(rows_from([0], [1]))

    def test_counter_forgery_and_unbounded_input_fail_closed(self):
        source = rows_from([16666666] * 4, [1] * 4)
        for field, value in (
            ("frame_id", True), ("frame_id", 0),
            ("elapsed_ns_capped", 250000001),
            ("elapsed_ns_capped", False),
            ("frame_game_ticks", 16),
            ("frame_game_ticks", 1.1),
            ("stress_game_ticks", 2),
        ):
            forged = [dict(x) for x in source]
            forged[1][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                phase.verify_phase(forged)
        other = [dict(x) for x in source]
        other[1]["frame_id"] = 5
        with self.assertRaises(ValueError):
            phase.verify_phase(other)
        for invalid in ([], None, {}, tuple(source), source * 1025):
            with self.assertRaises(ValueError):
                phase.verify_phase(invalid)

    def test_output_is_exclusive_and_unattested_data_inconclusive(self):
        with tempfile.TemporaryDirectory() as dirname:
            folder = Path(dirname)
            args = []
            for key in (
                "baseline-clock", "baseline-trace", "baseline-report",
                "baseline-binding", "baseline-nro", "experimental-clock",
                "experimental-trace", "experimental-report",
                "experimental-binding", "experimental-nro",
            ):
                args += ["--" + key, str(folder / key)]
            dest = folder / "no-evidence.json"
            args += ["--out", str(dest)]
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(phase.main(args), 1)
            self.assertIn("INCONCLUSIVE_GUEST_60HZ_CARRY_PHASE", out.getvalue())
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
