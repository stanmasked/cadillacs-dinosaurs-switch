"""Stage278 private checkpoint comparator; synthetic-only, ROM-free fixtures."""
import json
import tempfile
import unittest
from pathlib import Path
from tools import dino_native_compare_private_checkpoints as cmp

def make_logs(frames,period,broken=None):
    points=list(range(period,frames+1,period))
    if not points or points[-1]!=frames:points.append(frames)
    a="\n".join(f"DINO278_CHECKPOINT frame={i} full_state={i:016x}" for i in points)+"\n"
    b="\n".join(
        f"DINO278_CHECKPOINT frame={i} full_state={i+1 if i==broken else i:016x}"
        for i in points)+"\n"
    return a.encode("ascii"),b.encode("ascii")

class CheckpointComparatorTests(unittest.TestCase):
    def test_same_complete_logs_are_accepted(self):
        a,b=make_logs(248,60)
        report=cmp.compare(a,b,248,60)
        self.assertEqual(report["status"],"FULL_STATE_CHAINS_MATCH")
        self.assertEqual(report["checkpoints_compared"],5)
        self.assertIsNone(report["first_observed_mismatch_at_input_frame"])
        self.assertFalse(report["WolfMAME_original_gameplay_verified"])

    def test_first_divergence_bracket_is_precise_to_interval(self):
        a,b=make_logs(248,60,180)
        report=cmp.compare(a,b,248,60)
        self.assertEqual(report["status"],"FIRST_OBSERVED_STATE_MISMATCH")
        self.assertEqual(report["first_observed_mismatch_at_input_frame"],180)
        self.assertEqual(report["last_matching_checkpoint_input_frame"],120)
        self.assertNotEqual(report["reference_checkpoint_chain_sha256"],
                            report["candidate_checkpoint_chain_sha256"])

    def test_mismatch_at_first_checkpoint_has_zero_lower_bound(self):
        a,b=make_logs(200,60,60)
        report=cmp.compare(a,b,200,60)
        self.assertEqual(report["last_matching_checkpoint_input_frame"],0)
        self.assertEqual(report["first_observed_mismatch_at_input_frame"],60)

    def test_aligned_last_checkpoint_single_occurrence(self):
        a,b=make_logs(240,60)
        self.assertEqual(len(cmp.parse_log(a,240,60)),4)

    def test_missing_or_extra_line_rejected(self):
        a,_=make_logs(121,60)
        parts=a.splitlines(keepends=True)
        for tampered in (b"".join(parts[:-1]),a+parts[-1]):
            with self.subTest(length=len(tampered)),self.assertRaises(ValueError):
                cmp.parse_log(tampered,121,60)

    def test_bad_line_field_and_nondeterministic_order_rejected(self):
        a,_=make_logs(121,60)
        for tampered in (a.replace(b"frame=60",b"frame=61"),
                         a.replace(b"full_state=",b"hash="),
                         a.replace(b"000000000000003c",b"zzzzzzzzzzzzzzzz"),
                         b"".join(reversed(a.splitlines(keepends=True)))):
            with self.subTest(tampered=tampered[:35]),self.assertRaises(ValueError):
                cmp.parse_log(tampered,121,60)

    def test_invalid_bounds_and_large_memory_requests_rejected(self):
        for frames,period in ((0,60),(121,0),(True,60),
                              (121,False),(10000000,1),(10000001,600)):
            with self.subTest(frames=frames,period=period),self.assertRaises(ValueError):
                cmp.parse_log(b"",frames,period)

    def test_reject_symlink_logs_and_preserve_private_log(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            regular=folder/"a.txt"
            regular.write_bytes(make_logs(120,60)[0])
            link=folder/"link.txt"
            link.symlink_to(regular)
            self.assertEqual(cmp.ordinary_private_log(regular),regular.read_bytes())
            with self.assertRaisesRegex(ValueError,"non-symlink"):
                cmp.ordinary_private_log(link)

    def test_private_cli_writes_only_short_comparison_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder)
            a,b=make_logs(121,60)
            ref=folder/"reference.log"
            candidate=folder/"candidate.log"
            out=folder/"summary.json"
            ref.write_bytes(a)
            candidate.write_bytes(b)
            code=cmp.main(["--reference",str(ref),"--candidate",str(candidate),
                           "--input-frames","121","--checkpoint-every","60",
                           "--out",str(out)])
            self.assertEqual(code,0)
            report=json.loads(out.read_text())
            self.assertEqual(report["checkpoints_compared"],3)
            with self.assertRaises(FileExistsError):
                cmp.main(["--reference",str(ref),"--candidate",str(candidate),
                          "--input-frames","121","--checkpoint-every","60",
                          "--out",str(out)])

if __name__=="__main__":
    unittest.main()
