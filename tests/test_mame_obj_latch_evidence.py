"""ROM-free tests for optional per-render CPS-1 OBJ latch callback counters."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.mame_obj_latch_evidence import latch_counter_diagnostic
from tools.mame_obj_sequence_alignment import main
from test_mame_obj_cli_end_to_end import make_capture


def write_counts(root, counts, *, first=900, step=2):
    for i, number in enumerate(counts):
        path = root / f'frame-{first+i*step:08d}.obj-latch-count.txt'
        path.write_bytes(f'CPS1_DINO_LATCH_V1 {number}\n'.encode('ascii'))


class MameObjLatchCounterTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_two_callbacks_per_two_nominal_frames_remains_unverified(self):
        write_counts(self.root, [400, 402, 404, 406, 408, 410])
        report = latch_counter_diagnostic(self.root, 900, 6, 2, [0]*5)
        self.assertEqual(report['inter_sample_callback_deltas'], [2]*5)
        self.assertEqual(report['multiple_callback_delta_frames'],
                         [902, 904, 906, 908, 910])
        self.assertEqual(report['zero_callback_delta_frames'], [])
        self.assertFalse(report['obj_latch_age_verified'])
        self.assertFalse(report['frame_sync_verified'])
        self.assertFalse(report['pixel_parity_eligible'])

    def test_zero_deltas_and_obj_change_are_only_diagnostic(self):
        write_counts(self.root, [3, 3, 4, 4, 5, 5])
        result = latch_counter_diagnostic(self.root, 900, 6, 2,
                                          [1, 0, 2, 0, 1])
        self.assertEqual(result['zero_callback_delta_frames'], [902, 906, 910])
        self.assertEqual(result['obj_changed_without_observed_latch_frames'],
                         [902, 906, 910])
        self.assertFalse(result['frame_sync_verified'])

    def test_single_latch_increment_is_not_assumed_frame_age(self):
        write_counts(self.root, [10, 11, 12, 13])
        out = latch_counter_diagnostic(self.root, 900, 4, 2)
        self.assertEqual(out['inter_sample_callback_deltas'], [1, 1, 1])
        self.assertEqual(out['obj_changed_without_observed_latch_frames'], None)

    def test_missing_one_sidecar_fails_closed(self):
        write_counts(self.root, [1, 2, 3, 4, 5, 6])
        (self.root / 'frame-00000906.obj-latch-count.txt').unlink()
        with self.assertRaises(OSError):
            latch_counter_diagnostic(self.root, 900, 6, 2)

    def test_counter_reset_or_descending_value_is_rejected(self):
        write_counts(self.root, [11, 12, 2, 3, 4, 5])
        with self.assertRaisesRegex(ValueError, 'decreased'):
            latch_counter_diagnostic(self.root, 900, 6, 2)

    def test_oversized_or_noncanonical_line_rejected(self):
        write_counts(self.root, [1, 2, 3, 4, 5, 6])
        path = self.root / 'frame-00000900.obj-latch-count.txt'
        bad_lines = [b'CPS1_DINO_LATCH_V1 ' + b'8'*400,
                     b'CPS1_DINO_LATCH_V1 01\n',
                     b'CPS1_DINO_LATCH_V1 -1\n',
                     b'CPS1_DINO_LATCH_V1 +1\n',
                     b'CPS1_DINO_LATCH_V2 1\n',
                     b'CPS1_DINO_LATCH_V1 1',
                     b'CPS1_DINO_LATCH_V1 1\nEXTRA\n',
                     b'CPS1_DINO_LATCH_V1 \xff\n']
        for data in bad_lines:
            with self.subTest(data=data[:24]):
                path.write_bytes(data)
                with self.assertRaises(ValueError):
                    latch_counter_diagnostic(self.root, 900, 6, 2)

    def test_uint64_max_value_accepted_no_overflow(self):
        hi = (1 << 64) - 1
        write_counts(self.root, [hi-3, hi-2, hi-1, hi])
        out = latch_counter_diagnostic(self.root, 900, 4, 2)
        self.assertEqual(out['observed_latch_callback_counts'][-1], hi)

    def test_overflow_value_is_rejected(self):
        hi = (1 << 64)
        write_counts(self.root, [hi, hi, hi, hi])
        with self.assertRaisesRegex(ValueError, 'uint64'):
            latch_counter_diagnostic(self.root, 900, 4, 2)

    def test_bool_and_invalid_range_inputs_rejected(self):
        write_counts(self.root, [1, 2, 3, 4, 5, 6])
        for bounds in [(True, 6, 2), (900, True, 2),
                       (900, 6, True), (-1, 6, 2),
                       (900, 25, 2), (99999999, 6, 2)]:
            with self.subTest(bounds=bounds):
                with self.assertRaises(ValueError):
                    latch_counter_diagnostic(self.root, *bounds)

    def test_mismatched_obj_change_series_rejected(self):
        write_counts(self.root, [1, 2, 3, 4, 5, 6])
        for changed in ([0]*4, [0]*6, [True]*5, [-1]*5, [257]*5):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    latch_counter_diagnostic(self.root, 900, 6, 2, changed)

    def test_cli_without_opt_in_still_accepts_legacy_capture(self):
        make_capture(self.root)
        output = self.root / 'old.json'
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main([str(self.root), '--out', str(output)])
        self.assertEqual(rc, 0)
        meta = json.loads(output.read_text())['obj_latch_count_evidence']
        self.assertEqual(meta['status'], 'NOT_REQUESTED')
        self.assertFalse(meta['frame_sync_verified'])

    def test_cli_opt_in_reads_complete_latch_series(self):
        make_capture(self.root)
        write_counts(self.root, [21, 23, 25, 27, 29, 31])
        output = self.root / 'new.json'
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main([str(self.root), '--latch-count-evidence',
                       '--out', str(output)])
        self.assertEqual(rc, 0)
        meta = json.loads(output.read_text())['obj_latch_count_evidence']
        self.assertEqual(meta['inter_sample_callback_deltas'], [2]*5)
        self.assertEqual(meta['status'], 'LATCH_CALLBACK_COUNTS_UNVERIFIED')
        self.assertFalse(meta['pixel_parity_eligible'])

    def test_cli_opt_in_refuses_partial_series_without_json(self):
        make_capture(self.root)
        write_counts(self.root, [1, 3, 5, 7, 9, 11])
        (self.root / 'frame-00000908.obj-latch-count.txt').unlink()
        output = self.root / 'bad.json'
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            rc = main([str(self.root), '--latch-count-evidence',
                       '--out', str(output)])
        self.assertEqual(rc, 2)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
