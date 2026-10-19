"""ROM-free tests for guest render-frame-ID adjacency vs observation order.

Synthetic observations are not real NeXium samples; actual NRO/mode/SHA
binding occurs before final paired artifacts are admitted by GitHub CI.
"""
import copy
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from tools import nexium_guest_frame_gap_burst_audit as bursts
from test_nexium_guest_frame_topology import row
from test_nexium_audio_ack_tick_trace import fixture


class GuestFrameGapBurstTests(unittest.TestCase):
    def test_all_single_frame_900ticks_has_no_batch_bursts(self):
        rows,_=fixture()
        outcome=bursts.analyze_bursts(rows)
        self.assertEqual(outcome["observed_simulation_ticks"],900)
        self.assertEqual(outcome["consecutive_render_id_batched_runs"],0)
        self.assertEqual(outcome["max_genuinely_adjacent_render_id_batched_frames"],0)
        self.assertEqual(outcome["consecutive_render_id_batch_run_length_histogram"],{})
        self.assertEqual(outcome["zero_simulation_tick_render_id_gaps_total"],0)
        self.assertEqual(outcome["observed_released_pcm_pages"],900)

    def test_zero_step_render_gap_breaks_apparent_two_frame_batch_run(self):
        rows=[
            row(10,1,0),
            row(11,2,0),row(11,2,1,1,0),
            # Render frame 12 has no observed simulation ticks.
            row(13,2,0),row(13,2,1,1,0),
            row(14,1,0),
        ]
        result=bursts.analyze_bursts(rows)
        self.assertEqual(result["max_consecutive_observed_batched_frames_ignoring_id_gaps"],2)
        self.assertEqual(result["max_genuinely_adjacent_render_id_batched_frames"],1)
        self.assertEqual(result["zero_simulation_tick_render_id_gaps_total"],1)
        self.assertEqual(result["render_id_gaps_separating_observed_batched_frames"],1)
        self.assertEqual(result["consecutive_render_id_batch_run_length_histogram"],{"1":2})
        self.assertEqual(result["observed_batched_render_frames"],2)
        self.assertEqual(result["pcm_skips_in_isolated_batched_render_frames"],2)
        self.assertEqual(result["pcm_skips_in_batched_runs_of_length_two_or_more"],0)
        self.assertEqual(result["observed_skipped_pcm_ticks"],2)

    def test_true_consecutive_frame_ids_form_one_burst(self):
        rows=[row(7,1,0)]
        for frame in range(8,12):
            rows.extend([row(frame,2,0),row(frame,2,1,1,0)])
        rows.append(row(12,1,0))
        outcome=bursts.analyze_bursts(rows)
        self.assertEqual(outcome["consecutive_render_id_batched_runs"],1)
        self.assertEqual(outcome["max_genuinely_adjacent_render_id_batched_frames"],4)
        self.assertEqual(outcome["consecutive_render_id_batch_run_length_histogram"],{"4":1})
        self.assertEqual(outcome["pcm_skips_in_batched_runs_of_length_two_or_more"],4)
        self.assertEqual(outcome["pcm_skips_in_isolated_batched_render_frames"],0)
        self.assertEqual(outcome["max_genuinely_adjacent_render_id_batched_run"]["start_frame_id"],8)
        self.assertEqual(outcome["max_genuinely_adjacent_render_id_batched_run"]["end_frame_id"],11)

    def test_game_tick_checkpoint_at_150_does_not_cut_render_burst(self):
        rows=[row(i,1,0) for i in range(1,149)]
        rows.extend([row(149,2,0),row(149,2,1),
                     row(150,2,0),row(150,2,1,1,0)])
        rows.extend(row(i,1,0) for i in range(151,169))
        self.assertEqual(len(rows),170)
        result=bursts.analyze_bursts(rows)
        self.assertEqual(result["max_genuinely_adjacent_render_id_batched_frames"],2)
        self.assertEqual(result["consecutive_render_id_batch_run_length_histogram"],{"2":1})
        self.assertEqual(result["observed_skipped_pcm_ticks"],1)

    def test_censored_start_end_frames_keep_only_observed_ticks(self):
        rows=[
            row(8,3,1),row(8,3,2,1,0),
            row(9,2,0),row(9,2,1),
            row(10,1,0),
            row(11,3,0),row(11,3,1,1,0),
        ]
        result=bursts.analyze_bursts(rows)
        self.assertEqual(result["consecutive_render_id_batch_run_length_histogram"],{"2":1,"1":1})
        self.assertEqual(result["max_genuinely_adjacent_render_id_batched_frames"],2)
        self.assertEqual(result["max_genuinely_adjacent_render_id_batched_run"][
            "contains_left_window_censored_frame"],True)
        self.assertEqual(result["pcm_skips_in_batched_runs_of_length_two_or_more"],1)
        self.assertEqual(result["pcm_skips_in_isolated_batched_render_frames"],1)
        self.assertEqual(result["observed_simulation_ticks"],7)
        self.assertTrue(result["boundary_partial_frames_are_not_imputed"])

    def test_observed_zero_step_gap_between_single_and_batch_has_no_false_skip(self):
        rows=[
            row(1,1,0,1,0),
            row(4,2,0),row(4,2,1,1,0),
            row(6,1,0),
        ]
        result=bursts.analyze_bursts(rows)
        self.assertEqual(result["zero_simulation_tick_render_id_gaps_total"],3)
        self.assertEqual(result["render_id_gaps_separating_observed_batched_frames"],0)
        self.assertEqual(result["observed_skipped_pcm_ticks"],2)
        self.assertEqual(result["observed_batched_simulation_ticks"],2)
        self.assertEqual(result["max_genuinely_adjacent_render_id_batched_frames"],1)

    def test_corrupt_guest_audio_and_frame_ids_fail_closed(self):
        correct=[row(1,1,0),row(2,2,0),row(2,2,1)]
        for field,value in (("frame_id",0),("frame_id",True),
                            ("frame_id",1),("batch_size",3),
                            ("batch_position",0),("skipped",2),
                            ("released",3),("submitted",False)):
            altered=copy.deepcopy(correct)
            altered[2][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                bursts.analyze_bursts(altered)
        for invalid in ([],[row(1,1,0)]*901,{},None):
            with self.assertRaises(ValueError):
                bursts.analyze_bursts(invalid)

    def test_missing_guest_artifacts_cannot_publish_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            args=[]
            for name in (
                "baseline-trace","baseline-report","baseline-binding",
                "baseline-nro","experimental-trace","experimental-report",
                "experimental-binding","experimental-nro"):
                args.extend(["--"+name,str(root/name)])
            destination=root/"bursts.json"
            args.extend(["--out",str(destination)])
            with redirect_stdout(StringIO()) as stdout:
                self.assertEqual(bursts.main(args),1)
            self.assertIn("INCONCLUSIVE_GUEST_RENDER_FRAME_BURST_AUDIT",
                          stdout.getvalue())
            self.assertFalse(destination.exists())


if __name__=="__main__":
    unittest.main()
