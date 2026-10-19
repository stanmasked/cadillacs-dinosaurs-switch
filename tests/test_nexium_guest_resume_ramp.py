"""Pure ROM-free tests of attested guest 900-tick resume-ramp telemetry.

Synthetic rows do NOT stand for observed speaker output or NeXium guest
data; the final verifier independently validates actual NRO/mode/ACKs.
"""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import copy
import tempfile
import unittest

from tools import verify_nexium_guest_resume_ramp as ramp


def rows(skipped_indices=()):
    indexes = set(skipped_indices)
    return [dict(submitted=int(i not in indexes),
                 skipped=int(i in indexes)) for i in range(900)]


def count_fields(entries, start_pending=0):
    pending = bool(start_pending)
    applied = 0
    skipped = 0
    for entry in entries:
        if entry["skipped"]:
            pending = True
            skipped += 1
        elif pending:
            pending = False
            applied += 1
    return {
        "sampled_ticks": 900, "applied_start": 3,
        "applied_end": 3 + applied, "full_skips_start": 7,
        "full_skips_end": 7 + skipped,
        "pending_at_start": start_pending, "pending_at_end": int(pending),
    }


class GuestRampBindingTests(unittest.TestCase):
    def test_no_skips_has_no_ramp_applications(self):
        data = rows()
        result = ramp.check(count_fields(data), data)
        self.assertEqual(result["full_queue_pcm_skips"], 0)
        self.assertEqual(result["ramp_applications_inside_window"], 0)
        self.assertFalse(result["speaker_click_reduction_verified"])

    def test_full_skip_then_success_triggers_exactly_one_application(self):
        data = rows((7, 8, 9))
        report = ramp.check(count_fields(data), data)
        self.assertEqual(report["full_queue_pcm_skips"], 3)
        self.assertEqual(report["ramp_applications_inside_window"], 1)
        self.assertEqual(report["ramp_pending_at_window_end"], 0)

    def test_last_tick_skip_retains_pending_state(self):
        data = rows((899,))
        result = ramp.check(count_fields(data), data)
        self.assertEqual(result["full_queue_pcm_skips"], 1)
        self.assertEqual(result["ramp_applications_inside_window"], 0)
        # This is a physically valid observation: the guest has not
        # submitted a subsequent PCM block, so no attack could occur.
        self.assertTrue(result["ramp_pending_at_window_end"])

    def test_start_pending_is_not_imputed_as_new_measured_skip(self):
        data = rows()
        result = ramp.check(count_fields(data, start_pending=1), data)
        self.assertEqual(result["full_queue_pcm_skips"], 0)
        self.assertEqual(result["ramp_applications_inside_window"], 1)

    def test_fake_counts_and_mismatched_pending_rejected(self):
        sample = rows((6, 10, 11, 550))
        good = count_fields(sample)
        ramp.check(good, sample)
        for key in (
            "sampled_ticks", "applied_end", "full_skips_end",
            "pending_at_start", "pending_at_end",
        ):
            bad = dict(good)
            bad[key] = 901 if key == "sampled_ticks" else (
                2 if key.startswith("pending") else good[key] + 1)
            with self.subTest(key=key), self.assertRaises(ValueError):
                ramp.check(bad, sample)
        for idx, change in ((0, {"skipped": True}),
                            (0, {"submitted": 2}),
                            (0, {"submitted": 0, "skipped": 0})):
            bad_rows = copy.deepcopy(sample)
            bad_rows[idx].update(change)
            with self.assertRaises(ValueError):
                ramp.check(good, bad_rows)

    def test_csv_parser_rejects_noncanonical_and_missing_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ramp.csv"
            def save(values, header=ramp.COLUMNS):
                path.write_text(",".join(header)+"\n"+
                                ",".join(str(values[x]) for x in header)+"\n",
                                encoding="ascii")
            data = count_fields(rows((1,)))
            save(data)
            raw, parsed = ramp.parse(path)
            self.assertEqual(parsed, data)
            self.assertGreater(len(raw), 50)
            path.write_text(path.read_text().replace("900,", "0900,", 1))
            with self.assertRaises(ValueError):
                ramp.parse(path)
            path.write_bytes(b"X"*600)
            with self.assertRaises(ValueError):
                ramp.parse(path)
            path.unlink()
            with self.assertRaises(ValueError):
                ramp.parse(path)

    def test_unauthenticated_guest_files_do_not_publish_success(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            args = []
            for key in ("ramp", "trace", "report", "nro"):
                args.extend(["--" + key, str(root / key)])
            path = root / "out.json"
            args.extend(["--out", str(path)])
            with redirect_stdout(StringIO()) as output:
                self.assertEqual(ramp.main(args), 1)
            self.assertIn("INCONCLUSIVE_GUEST_OPTIN_PCM_RESUME_RAMP",
                          output.getvalue())
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
