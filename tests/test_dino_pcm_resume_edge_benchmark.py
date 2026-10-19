"""Tests for the actual compiled native C ramp, not modeled game audio."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from tools import dino_pcm_resume_edge_benchmark as edge


@unittest.skipUnless(shutil.which("gcc"),"GCC required for real-C sample benchmark")
class ResumePCMEdgeBenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=edge.benchmark()
        cls.by_name={r["case"]:r for r in cls.report["profiles"]}

    def test_real_c_benchmark_has_exact_bounded_no_rom_configuration(self):
        data=self.report
        self.assertEqual(data["status"],
            "ACTUAL_C_PCM_ATTACK_HAS_CONDITION_DEPENDENT_EDGE_TRADEOFF")
        self.assertEqual(data["sample_rate_hz"],48000)
        self.assertEqual(data["pcm_frames_per_game_tick"],800)
        self.assertEqual(data["ramp_frames"],96)
        self.assertEqual(data["ramp_duration_ms_exact"],2)
        self.assertEqual(data["input_samples"],"synthetic_rom_free_only")
        self.assertEqual(len(data["profiles"]),5)
        self.assertFalse(data["production_enablement_recommended"])
        self.assertFalse(data["audible_click_reduction_verified"])
        self.assertFalse(data["physical_switch_speaker_audio_verified"])

    def test_silence_to_loud_boundary_jump_reduced_exactly(self):
        r=self.by_name["silence_to_loud"]
        self.assertEqual(r["boundary_max_abs_sample_step_before"],30000)
        self.assertEqual(r["boundary_max_abs_sample_step_after"],312)
        self.assertEqual(r["boundary_step_delta_after_minus_before"],-29688)
        self.assertEqual(r["first_shaped_stereo_frame"],[312,-250])
        self.assertTrue(r["boundary_discontinuity_improved"])
        self.assertFalse(r["boundary_discontinuity_worsened"])
        self.assertEqual(r["max_sample_step_within_attack_including_boundary_after"],313)

    def test_already_continuous_boundary_jump_is_made_worse(self):
        r=self.by_name["already_continuous"]
        self.assertEqual(r["boundary_max_abs_sample_step_before"],0)
        self.assertEqual(r["boundary_max_abs_sample_step_after"],29688)
        self.assertEqual(r["boundary_step_delta_after_minus_before"],29688)
        self.assertTrue(r["boundary_discontinuity_worsened"])
        self.assertFalse(r["boundary_discontinuity_improved"])
        self.assertFalse(self.report["guaranteed_boundary_improvement"])

    def test_opposite_polarity_crossing_is_not_confused_with_silence(self):
        r=self.by_name["opposite_polarity"]
        self.assertEqual(r["boundary_max_abs_sample_step_before"],60000)
        self.assertEqual(r["boundary_max_abs_sample_step_after"],30312)
        self.assertTrue(r["boundary_discontinuity_improved"])

    def test_zero_signal_stays_exact_silence(self):
        r=self.by_name["zero_signal"]
        self.assertEqual(r["changed_attack_samples"],0)
        self.assertEqual(r["squared_sample_difference_sum"],0)
        self.assertEqual(r["max_sample_step_within_attack_including_boundary_after"],0)
        self.assertEqual(r["boundary_max_abs_sample_step_before"],0)
        self.assertEqual(r["boundary_max_abs_sample_step_after"],0)

    def test_no_extra_samples_no_modified_tail_for_all_five_cases(self):
        for r in self.report["profiles"]:
            with self.subTest(case=r["case"]):
                self.assertEqual(r["output_frame_count_before"],800)
                self.assertEqual(r["output_frame_count_after"],800)
                self.assertEqual(r["unchanged_sample_count_after_attack"],1408)
                self.assertTrue(r["actual_c_ramp_matched_integer_oracle"])
                self.assertEqual(len(r["shaped_pcm_sha256"]),64)
        self.assertEqual(len({
            r["shaped_pcm_sha256"] for r in self.report["profiles"]}),3)

    def test_signed_c_truncation_reference_matches_at_edges(self):
        self.assertEqual(edge.oracle_sample(-32768,0),-341)
        self.assertEqual(edge.oracle_sample(32767,0),341)
        self.assertEqual(edge.oracle_sample(-32768,95),-32768)
        self.assertEqual(edge.oracle_sample(32767,95),32767)
        for sample,index in ((32768,0),(-32769,0),(100,96),(100,-1),
                             (True,0),(0,False)):
            with self.subTest(sample=sample,index=index):
                with self.assertRaises(ValueError):
                    edge.oracle_sample(sample,index)

    def test_source_mismatch_is_rejected_even_with_plausible_metrics(self):
        cases=edge.make_cases()
        previous,original=cases["already_continuous"]
        shaped=original.copy()
        shaped[0]=1
        with self.assertRaisesRegex(ValueError,"integer oracle"):
            edge.score(previous,original,shaped,"already_continuous")
        shaped=original.copy()
        shaped[2*96]=0
        with self.assertRaisesRegex(ValueError,"beyond the 96-frame"):
            edge.score(previous,original,shaped,"already_continuous")

    def test_exact_channel_crossover_is_not_assumed_audible(self):
        positive=edge.boundary_channel_tradeoff(15156,30000,312)
        self.assertEqual(positive["crossover_previous_sample_numerator"],30312)
        self.assertEqual(positive["crossover_previous_sample_denominator"],2)
        self.assertTrue(positive["equal"])
        self.assertFalse(positive["improved"])
        self.assertFalse(positive["worsened"])
        self.assertTrue(edge.boundary_channel_tradeoff(
            15155,30000,312)["improved"])
        self.assertTrue(edge.boundary_channel_tradeoff(
            15157,30000,312)["worsened"])
        negative=edge.boundary_channel_tradeoff(-12125,-24000,-250)
        self.assertTrue(negative["equal"])
        self.assertTrue(edge.boundary_channel_tradeoff(
            -12126,-24000,-250)["worsened"])
        self.assertTrue(edge.boundary_channel_tradeoff(
            -12124,-24000,-250)["improved"])

    def test_previous_sample_sweep_demonstrates_both_unsafe_and_beneficial_edges(self):
        for first,shaped,crossover in (
            (30000,312,15156),
            (-24000,-250,-12125),
        ):
            seen={"improved":0,"worsened":0,"equal":0}
            for previous in range(-32768,32768,257):
                scenario=edge.boundary_channel_tradeoff(previous,first,shaped)
                correct_before=abs(first-previous)
                correct_after=abs(shaped-previous)
                self.assertEqual(scenario["unshaped_boundary_jump"],
                                 correct_before)
                self.assertEqual(scenario["shaped_boundary_jump"],
                                 correct_after)
                self.assertEqual(scenario["delta_shaped_minus_unshaped"],
                                 correct_after-correct_before)
                for field in seen:
                    seen[field]+=int(scenario[field])
                self.assertEqual(scenario["improved"],
                                 (previous<crossover if first>shaped
                                  else previous>crossover))
            self.assertGreater(seen["worsened"],0)
            self.assertGreater(seen["improved"],0)
            self.assertEqual(sum(seen.values()),
                             len(range(-32768,32768,257)))
        for invalid in (
            (True,30000,312),
            (0,32768,312),
            (0,-32769,-250),
            (0,0,1.5),
        ):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                edge.boundary_channel_tradeoff(*invalid)

    def test_main_writes_complete_json_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/"edge.json"
            with redirect_stdout(StringIO()) as messages:
                self.assertEqual(edge.main(["--out",str(out)]),0)
            self.assertIn("CONDITION_DEPENDENT_EDGE_TRADEOFF",
                          messages.getvalue())
            data=json.loads(out.read_text(encoding="ascii"))
            self.assertEqual(data["schema"],edge.SCHEMA)
            original=out.read_bytes()
            with redirect_stdout(StringIO()) as messages:
                self.assertEqual(edge.main(["--out",str(out)]),1)
            self.assertIn("INCONCLUSIVE_RESUME_EDGE_BENCHMARK",
                          messages.getvalue())
            self.assertEqual(out.read_bytes(),original)

    def test_benchmark_fails_closed_without_a_real_c_compiler(self):
        with mock.patch.object(edge.shutil,"which",return_value=None):
            with self.assertRaises(ValueError):
                edge.benchmark()

    def test_incorrect_attack_length_fails_closed(self):
        original=edge.ATTACK
        try:
            edge.ATTACK=1
            # Real C still performs 96 frames, so the independent oracle
            # must reject the altered benchmark configuration.
            with self.assertRaises(ValueError):
                edge.benchmark()
        finally:
            edge.ATTACK=original


if __name__=="__main__":
    unittest.main()
