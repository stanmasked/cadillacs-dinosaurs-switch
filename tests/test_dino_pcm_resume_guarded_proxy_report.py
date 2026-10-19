"""ROM-free evidence tests for sample-step guarded candidate, not DSP quality."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from tools import dino_pcm_resume_guarded_proxy_report as report
from tools import dino_pcm_resume_edge_benchmark as edge


@unittest.skipUnless(shutil.which("gcc"),"Native GCC required for actual C")
class GuardedPCMReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=report.benchmark()
        cls.profiles={x["scenario"]:x for x in cls.data["profiles"]}

    def test_all_six_synthetic_inputs_and_actual_c_oracle_agree(self):
        self.assertEqual(len(self.profiles),6)
        self.assertEqual(self.data["sample_rate_hz"],48000)
        self.assertEqual(self.data["ramp_frames"],96)
        self.assertEqual(self.data["pcm_frame_count"],800)
        self.assertEqual(self.data["input_audio"],
                         "six_deterministic_rom_free_synthetic_cases")
        self.assertEqual(self.data["status"],
                         "C_GATE_REJECTS_WORSE_WINDOW_STEP_PROXY_CASES")
        self.assertFalse(self.data["production_enabled"])
        self.assertFalse(self.data["production_enablement_recommended"])
        self.assertFalse(self.data["audible_click_reduction_verified"])

    def test_good_silence_boundary_improves_worst_per_channel_step(self):
        r=self.profiles["silence_to_loud"]
        self.assertTrue(r["guarded_proxy_would_run"])
        self.assertEqual(r["raw_window_peak_by_stereo_channel"],[30000,24000])
        self.assertLess(r["guard_selected_window_peak_by_stereo_channel"][0],
                        30000)
        self.assertLess(r["guard_selected_window_peak_by_stereo_channel"][1],
                        24000)

    def test_already_continuous_signal_fails_closed(self):
        r=self.profiles["already_continuous"]
        self.assertFalse(r["guarded_proxy_would_run"])
        self.assertEqual(r["raw_window_peak_by_stereo_channel"],[0,0])
        self.assertGreater(r["fixed_ramp_window_peak_by_stereo_channel"][0],0)
        self.assertEqual(r["guard_selected_window_peak_by_stereo_channel"],
                         [0,0])

    def test_channel_disagreement_fails_both_channel_safety_gate(self):
        r=self.profiles["one_channel_worsens"]
        self.assertFalse(r["guarded_proxy_would_run"])
        self.assertGreater(
            r["fixed_ramp_window_peak_by_stereo_channel"][1],
            r["raw_window_peak_by_stereo_channel"][1])
        self.assertEqual(r["guard_selected_window_peak_by_stereo_channel"],
                         r["raw_window_peak_by_stereo_channel"])

    def test_idle_silence_is_not_attributed_to_necessary_audio_processing(self):
        self.assertFalse(self.profiles["zero_signal"]["guarded_proxy_would_run"])
        self.assertEqual(self.profiles["zero_signal"][
            "guard_selected_window_peak_by_stereo_channel"],[0,0])

    def test_all_cases_conserve_frames_and_tail_under_selected_policy(self):
        for r in self.data["profiles"]:
            with self.subTest(r["scenario"]):
                self.assertTrue(
                    r["selected_window_peak_not_worse_in_either_channel"])
                self.assertTrue(r["selected_pcm_tail_unchanged"])
                self.assertFalse(r[
                    "previous_sample_is_confirmed_played_on_device"])
                self.assertFalse(r["speaker_click_reduction_measured"])

    def test_wrong_c_decision_fails_before_issuing_success(self):
        prev,raw=edge.make_cases()["already_continuous"]
        shaped=[0]*len(raw)
        with self.assertRaises(ValueError):
            report.profile("already_continuous",prev,raw,shaped,True)
        with self.assertRaises(ValueError):
            report.profile("already_continuous",prev,raw,raw,True)

    def test_report_is_exclusive_and_existing_evidence_unmodified(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"report.json"
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(report.main(["--out",str(path)]),0)
            self.assertIn("C_GATE_REJECTS_WORSE_WINDOW_STEP_PROXY_CASES",
                          out.getvalue())
            initial=path.read_bytes()
            parsed=json.loads(initial)
            self.assertEqual(parsed["schema"],report.SCHEMA)
            with redirect_stdout(StringIO()) as out:
                self.assertEqual(report.main(["--out",str(path)]),1)
            self.assertIn("INCONCLUSIVE_GUARDED_SAMPLE_STEP_PCM_PROXY",
                          out.getvalue())
            self.assertEqual(path.read_bytes(),initial)

    def test_missing_compiler_refuses_to_claim_native_proof(self):
        with mock.patch.object(report.shutil,"which",return_value=None):
            with self.assertRaises(ValueError):
                report.benchmark()

    def test_benchmark_never_uses_guest_or_arcade_sound_data(self):
        content=(report.ROOT/"tools"/
                 "dino_pcm_resume_guarded_proxy_report.py").read_text()
        self.assertNotIn("sdmc:",content)
        self.assertNotIn("audoutGet",content)
        self.assertIn("previous_pcm_tail_was_submitted_not_proven_played",
                      content)


if __name__=="__main__":
    unittest.main()
