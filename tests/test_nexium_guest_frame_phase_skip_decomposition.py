"""ROM-free deterministic checks for noncausal frame-position skip arithmetic.

No guest files, copied copyrighted assets, service timestamps or acoustic
latency are fabricated. Production runs must pass NRO/SHA binding first.
"""
from fractions import Fraction
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import copy
import tempfile
import unittest

from tools import nexium_guest_frame_phase_skip_decomposition as phases
from test_nexium_audio_ack_tick_trace import fixture


def synthetic_groups(ticks,skips,pages=None):
    if pages is None:
        pages=[0]*3
    return {p:{"ticks":n,"skipped_pcm":s,"ack_pages":ack}
            for p,n,s,ack in zip(phases.PHASES,ticks,skips,pages)}


def ratio(encoded):
    return Fraction(encoded["numerator"],encoded["denominator"])


class GuestFramePhaseSkipArithmeticTests(unittest.TestCase):
    def test_900_guest_ticks_all_single_are_counted_exactly(self):
        rows,_=fixture()
        values=phases.phase_counts(rows)
        self.assertEqual(values["single"],
                         {"ticks":900,"skipped_pcm":0,"ack_pages":900})
        self.assertEqual(values["first"],
                         {"ticks":0,"skipped_pcm":0,"ack_pages":0})
        self.assertEqual(values["later"],
                         {"ticks":0,"skipped_pcm":0,"ack_pages":0})
        result=phases.exact_skip_decomposition(values,values)
        self.assertEqual(result["status"],
                         "INCOMPARABLE_FRAME_PHASE_WITHOUT_BOTH_EXPOSURES")
        self.assertIsNone(result["exact_skip_count_identity"])
        self.assertEqual(result["missing_common_phase_exposure"],
                         ["first","later"])
        self.assertFalse(result["causal_audio_mode_effect_verified"])

    def test_phase_classification_is_based_on_recorded_batch_position(self):
        rows,_=fixture()
        rows[0]["batch_size"]=3
        rows[1]["batch_size"]=3
        rows[2]["batch_size"]=3
        rows[1]["batch_position"]=1
        rows[2]["batch_position"]=2
        rows[1]["skipped"]=1
        rows[2]["released"]=2
        counts=phases.phase_counts(rows)
        self.assertEqual([counts[k]["ticks"] for k in phases.PHASES],
                         [897,1,2])
        self.assertEqual(counts["later"]["skipped_pcm"],1)
        self.assertEqual(counts["later"]["ack_pages"],3)

    def test_symmetric_rational_identity_separates_exposure_and_rates(self):
        # Each regime has six simulation ticks. Category distributions and
        # conditional rates BOTH change, so naive skip difference misleads.
        a=synthetic_groups((2,2,2),(0,1,2))
        b=synthetic_groups((4,1,1),(1,0,1))
        result=phases.exact_skip_decomposition(a,b)
        self.assertEqual(result["status"],
                         "EXACT_FRAME_PHASE_SKIP_IDENTITY_NONCAUSAL")
        self.assertEqual(result["observed_extra_minus_baseline_skipped_pcm"],-1)
        exposure=ratio(result["arithmetic_exposure_component"])
        within=ratio(result["arithmetic_within_phase_rate_component"])
        self.assertEqual(exposure+within,Fraction(-1))
        # Independently expand identity in rational arithmetic.
        oracle_e=Fraction(0)
        oracle_r=Fraction(0)
        for phase in phases.PHASES:
            n0,s0=a[phase]["ticks"],a[phase]["skipped_pcm"]
            n1,s1=b[phase]["ticks"],b[phase]["skipped_pcm"]
            rate0=Fraction(s0,n0)
            rate1=Fraction(s1,n1)
            oracle_e+=(n1-n0)*(rate0+rate1)/2
            oracle_r+=(n1+n0)*(rate1-rate0)/2
        self.assertEqual((exposure,within),(oracle_e,oracle_r))
        self.assertFalse(result["causal_frame_pacing_explanation_verified"])
        self.assertFalse(result["matched_guest_service_timing_verified"])

    def test_full_900_tick_unequal_phase_exposure_has_exact_two_skip_delta(self):
        # Synthetic numbers reproduce a possible 900-tick imbalance;
        # they are not an attested NeXium run or any causal estimate.
        a=synthetic_groups((512,194,194),(51,0,68),(564,217,0))
        b=synthetic_groups((553,173,174),(53,0,64),(597,183,2))
        report=phases.exact_skip_decomposition(a,b)
        self.assertEqual(report["totals"]["baseline"]["ticks"],900)
        self.assertEqual(report["totals"]["extra-poll"]["ticks"],900)
        self.assertEqual(report["observed_extra_minus_baseline_skipped_pcm"],-2)
        diff=ratio(report["arithmetic_exposure_component"])+ratio(
            report["arithmetic_within_phase_rate_component"])
        self.assertEqual(diff,Fraction(-2))
        for phase in report["per_phase"]:
            self.assertTrue(phase["phase"] in phases.PHASES)
            self.assertGreater(phase["baseline_skip_rate_exact"]["denominator"],0)

    def test_refuses_zero_exposure_to_prevent_undefined_rate_imputation(self):
        left=synthetic_groups((3,0,3),(0,0,2))
        right=synthetic_groups((2,2,2),(0,2,1))
        output=phases.exact_skip_decomposition(left,right)
        self.assertIn("first",output["missing_common_phase_exposure"])
        self.assertIsNone(output["exact_skip_count_identity"])
        self.assertNotIn("per_phase",output)
        self.assertEqual(output["observed_extra_minus_baseline_skipped_pcm"],1)

    def test_invalid_types_coverage_and_skip_counts_are_rejected(self):
        original=synthetic_groups((2,2,2),(1,0,2))
        changed=copy.deepcopy(original)
        changed["later"]["skipped_pcm"]=3
        with self.assertRaises(ValueError):
            phases.exact_skip_decomposition(original,changed)
        for field,value in (("ticks",True),("skipped_pcm",-1),
                            ("ack_pages",5),("ticks",0.5)):
            invalid=copy.deepcopy(original)
            invalid["single"][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                phases.exact_skip_decomposition(original,invalid)
        invalid=copy.deepcopy(original)
        invalid.pop("first")
        with self.assertRaises(ValueError):
            phases.exact_skip_decomposition(original,invalid)
        for bad in ([],{},None,"123"):
            with self.assertRaises(ValueError):
                phases.phase_counts(bad)
        row={"batch_size":2,"batch_position":True,
             "skipped":0,"released":0}
        with self.assertRaises(ValueError):
            phases.phase_counts([row])

    def test_missing_real_guest_files_never_publish_stratification(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            args=[]
            for key in ("baseline-trace","baseline-report","baseline-binding",
                        "baseline-nro","experimental-trace","experimental-report",
                        "experimental-binding","experimental-nro"):
                args+=["--"+key,str(root/key)]
            outfile=root/"result.json"
            args+=["--out",str(outfile)]
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(phases.main(args),1)
            self.assertIn("INCONCLUSIVE_FRAME_PHASE_SKIP_DIAGNOSTIC",
                          output.getvalue())
            self.assertFalse(outfile.exists())


if __name__=="__main__":
    unittest.main()
