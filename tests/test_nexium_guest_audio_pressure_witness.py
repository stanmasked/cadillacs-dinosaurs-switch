"""ROM-free pressure/drop identities; synthetic data is NOT NeXium evidence."""
import copy
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from tools import nexium_guest_audio_pressure_witness as pressure
from test_nexium_audio_ack_tick_trace import fixture


class GuestPCMQueuePressureTests(unittest.TestCase):
    def test_synthetic_900_tick_uncontended_queue_is_lossless(self):
        rows, _ = fixture()
        result = pressure.summarize(rows, "baseline")
        self.assertEqual(result["totals"]["ticks"], 900)
        self.assertEqual(result["totals"]["skipped"], 0)
        self.assertEqual(result["totals"]["full_before_poll"], 0)
        self.assertEqual(result["totals"]["returned_pages"], 900)
        self.assertEqual(len(result["six_150tick_windows"]), 6)
        self.assertTrue(result["all_skips_are_full_queue_without_observed_recovery"])
        self.assertFalse(result["causal_mid_batch_poll_benefit_verified"])

    def test_full_without_ack_is_only_admission_failure(self):
        rows, _ = fixture()
        rows[151].update(pre_poll_full=1, pre_poll_recovered=0,
                         released=0, skipped=1, submitted=0, pending=2)
        rows[152].update(pre_poll_full=1, pre_poll_recovered=1,
                         released=1, skipped=0, submitted=1, pending=2)
        profile = pressure.summarize(rows, "baseline")
        totals = profile["totals"]
        self.assertEqual(totals["full_before_poll"], 2)
        self.assertEqual(totals["recovered_when_full"], 1)
        self.assertEqual(totals["unrecovered_full"], 1)
        self.assertEqual(totals["skipped"], 1)
        self.assertEqual(totals["admitted"], 899)
        self.assertEqual(profile["six_150tick_windows"][1]["skipped"], 1)
        self.assertEqual(profile["longest_consecutive_skipped_pcm_ticks"], 1)

    def test_experimental_mid_batch_calls_are_recorded_not_claimed_causal(self):
        rows, _ = fixture()
        rows[200].update(batch_size=2, batch_position=1,
                         mid_calls=1, mid_released=1, released=1)
        rows[201].update(batch_size=2, batch_position=1,
                         mid_calls=1, mid_released=0, released=0,
                         pre_poll_full=1, pre_poll_recovered=0,
                         skipped=1, submitted=0, pending=2)
        result = pressure.summarize(rows, "extra-poll")
        group = result["by_game_tick_position"]["later"]
        self.assertEqual(group["extra_poll_calls"], 2)
        self.assertEqual(group["extra_poll_return_ticks"], 1)
        self.assertEqual(group["extra_poll_pages"], 1)
        self.assertEqual(group["skipped"], 1)
        self.assertFalse(result["causal_mid_batch_poll_benefit_verified"])

    def test_multiple_zero_return_ticks_count_contiguous_skip_streak(self):
        rows, _ = fixture()
        for i in range(148,154):
            rows[i].update(pre_poll_full=1, pre_poll_recovered=0,
                           released=0, skipped=1, submitted=0, pending=2)
        result = pressure.summarize(rows, "baseline")
        self.assertEqual(result["longest_consecutive_skipped_pcm_ticks"], 6)
        self.assertEqual(result["longest_consecutive_no_return_ticks"], 6)
        self.assertEqual(result["six_150tick_windows"][0]["skipped"], 2)
        self.assertEqual(result["six_150tick_windows"][1]["skipped"], 4)

    def test_forgeries_in_ownership_poll_recovery_or_mode_are_rejected(self):
        rows, _ = fixture()
        for key,value in (
            ("pre_poll_full",1), ("pre_poll_recovered",1), ("skipped",1),
            ("submitted",0), ("pending",0), ("mid_calls",1),
            ("mid_released",1), ("released",3),
            ("batch_size",0), ("batch_position",1),
            ("pre_poll_full",True), ("skipped",0.5),
        ):
            forged = copy.deepcopy(rows)
            forged[10][key] = value
            with self.subTest(field=key,value=value),self.assertRaises(ValueError):
                pressure.summarize(forged,"baseline")
        forged = copy.deepcopy(rows)
        forged[1].update(batch_size=2,batch_position=1,mid_calls=1)
        with self.assertRaises(ValueError):
            pressure.summarize(forged,"baseline")

    def test_late_extra_poll_requires_valid_batch_phase(self):
        rows, _ = fixture()
        rows[199].update(mid_calls=1)
        with self.assertRaises(ValueError):
            pressure.summarize(rows,"extra-poll")
        rows[199].update(batch_size=2,batch_position=1)
        ok = pressure.summarize(rows,"extra-poll")
        self.assertEqual(ok["totals"]["extra_poll_calls"],1)
        self.assertEqual(ok["by_game_tick_position"]["later"]["ticks"],1)

    def test_wrong_lengths_modes_and_missing_full_trace_are_rejected(self):
        rows, _ = fixture()
        for sample in ([],rows[:-1],rows+[rows[-1]],tuple(rows),None):
            with self.subTest(n=len(sample) if sample is not None else None):
                with self.assertRaises(ValueError):
                    pressure.summarize(sample,"baseline")
        for mode in ("invalid",None,"",True):
            with self.assertRaises(ValueError):
                pressure.summarize(rows,mode)

    def test_missing_bound_guest_artifacts_never_publish_success(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            argv=[]
            for field in ("baseline-trace","baseline-report","baseline-binding",
                          "baseline-nro","experimental-trace","experimental-report",
                          "experimental-binding","experimental-nro"):
                argv.extend(["--"+field,str(path/field)])
            dest=path/"pressure.json"
            argv.extend(["--out",str(dest)])
            with redirect_stdout(StringIO()) as result:
                self.assertEqual(pressure.main(argv),1)
            self.assertIn("INCONCLUSIVE_GUEST_QUEUE_PRESSURE_IDENTITY",
                          result.getvalue())
            self.assertFalse(dest.exists())


if __name__=="__main__":
    unittest.main()
