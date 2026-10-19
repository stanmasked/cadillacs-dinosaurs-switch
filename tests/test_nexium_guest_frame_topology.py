"""ROM-free frame-boundary tests for real guest ACK topology.

This synthetic suite does not substitute for NRO-mode/SHA-attested guest
evidence. It independently checks censored first/last frame handling and
rejects accidental reclassification at 150-game-tick window boundaries.
"""
import copy
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from tools import nexium_guest_frame_topology as topology
from test_nexium_audio_ack_tick_trace import fixture


def row(frame, batch, position, skipped=0, release=1):
    return {
        "frame_id":frame,"batch_size":batch,"batch_position":position,
        "released":release,"skipped":skipped,"submitted":1-skipped,
        "mid_calls":0,"mid_released":0,
    }


class GuestFrameTopologyTests(unittest.TestCase):
    def test_all_900_single_frame_ticks_are_complete(self):
        rows,_=fixture()
        result=topology.scan_frames(rows)
        self.assertEqual(result["observed_simulation_ticks"],900)
        self.assertEqual(
            result["observed_render_frames_with_at_least_one_game_tick"],900)
        self.assertEqual(result["observed_complete_render_frames"],900)
        self.assertEqual(result["observed_partial_boundary_frames"],0)
        self.assertEqual(result["render_frame_ids_unobserved_in_interior_gaps"],0)
        self.assertEqual(result["observed_frame_size_histogram"]["1"][
            "complete_frames"],900)
        self.assertEqual(result["observed_pcm_released_pages"],900)
        self.assertEqual(result["observed_pcm_skips"],0)
        self.assertEqual(result["max_consecutive_observed_batched_render_frames"],0)

    def test_window_start_and_end_inside_frames_are_not_full_frames(self):
        rows=[
            row(10,3,1,1,0),
            row(10,3,2,0,1),
            row(11,1,0,0,1),
            row(12,3,0,0,2),
            row(12,3,1,1,0),
        ]
        result=topology.scan_frames(rows)
        self.assertEqual(result["observed_simulation_ticks"],5)
        self.assertEqual(result["observed_complete_render_frames"],1)
        self.assertEqual(result["observed_partial_boundary_frames"],2)
        self.assertTrue(result["first_observed_render_frame_left_censored"])
        self.assertTrue(result["last_observed_render_frame_right_censored"])
        self.assertEqual(result["complete_batched_render_frames"],0)
        self.assertEqual(result["boundary_partial_batched_render_frames"],2)
        self.assertEqual(result["observed_batched_frames_with_any_pcm_skip"],2)
        self.assertEqual(result["observed_pcm_skips"],2)
        self.assertEqual(result["observed_pcm_released_pages"],4)
        self.assertEqual(result["skipped_pcm_by_frame_position"]["later"],2)
        self.assertEqual(result["observed_frame_size_histogram"]["3"][
            "observed_game_ticks"],4)

    def test_frame_crosses_150_tick_checkpoint_without_inventing_frame(self):
        rows=[row(i,1,0) for i in range(1,150)]
        rows.extend([row(150,2,0),row(150,2,1,1,0)])
        rows.extend(row(i,1,0) for i in range(151,160))
        self.assertEqual(len(rows),160)
        result=topology.scan_frames(rows)
        self.assertEqual(result["observed_render_frames_with_at_least_one_game_tick"],
                         159)
        self.assertEqual(result["observed_complete_render_frames"],159)
        self.assertEqual(result["observed_partial_boundary_frames"],0)
        self.assertEqual(result["observed_frame_size_histogram"]["2"][
            "observed_frames"],1)
        self.assertEqual(result["skipped_pcm_by_frame_position"]["later"],1)

    def test_render_frame_id_gaps_do_not_fabricate_simulation_ticks(self):
        rows=[row(7,1,0),row(9,2,0),row(9,2,1),row(13,1,0)]
        result=topology.scan_frames(rows)
        self.assertEqual(result["observed_simulation_ticks"],4)
        self.assertEqual(result["render_frame_ids_unobserved_in_interior_gaps"],4)
        self.assertEqual(result["observed_complete_render_frames"],3)
        self.assertEqual(result["max_consecutive_observed_batched_render_frames"],1)
        self.assertTrue(result["unknown_unobserved_simulation_frames_not_imputed"])

    def test_long_burst_of_batched_frames_is_recorded_without_audio_causality(self):
        rows=[row(1,1,0)]
        for i in range(2,7):
            rows.extend([row(i,2,0),row(i,2,1,1,0)])
        rows.append(row(7,1,0))
        rows.extend([row(8,2,0),row(8,2,1)])
        result=topology.scan_frames(rows)
        self.assertEqual(result["max_consecutive_observed_batched_render_frames"],5)
        self.assertEqual(result["observed_batched_frames_with_any_pcm_skip"],5)
        self.assertEqual(result["complete_batched_render_frames"],6)
        self.assertEqual(result["boundary_partial_batched_render_frames"],0)
        self.assertEqual(result["observed_pcm_skips"],5)

    def test_missing_or_corrupted_interior_frame_ticks_fail_closed(self):
        cases=[
            [row(1,2,0),row(1,2,2)],
            [row(1,2,0),row(2,1,0)],
            [row(1,1,0),row(2,2,1),row(2,2,2)],
            [row(1,1,0),row(2,2,0),row(3,1,0)],
            [row(1,1,0),row(2,1,0),row(1,1,0)],
            [row(1,2,0),row(1,3,1)],
        ]
        for rows in cases:
            with self.subTest(rows=rows),self.assertRaises(ValueError):
                topology.scan_frames(rows)

    def test_counter_forgery_types_and_overlong_traces_fail_closed(self):
        original=[row(1,2,0),row(1,2,1),row(2,1,0)]
        for name,val in (
            ("batch_size",0),("batch_size",16),
            ("batch_position",True),("frame_id",0),
            ("frame_id",2.0),("released",3),("mid_released",4),
            ("submitted",1.5),("skipped",2),("mid_calls",-1),
        ):
            fake=copy.deepcopy(original)
            fake[1][name]=val
            with self.subTest(name=name,value=val),self.assertRaises(ValueError):
                topology.scan_frames(fake)
        for rows in ([],[row(1,1,0)]*901,(),None):
            with self.assertRaises(ValueError):
                topology.scan_frames(rows)

    def test_missing_real_guest_evidence_is_inconclusive_not_a_success_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            argv=[]
            for k in ("baseline-trace","baseline-report","baseline-binding",
                      "baseline-nro","experimental-trace","experimental-report",
                      "experimental-binding","experimental-nro"):
                argv.extend(["--"+k,str(root/k)])
            target=root/"topology.json"
            argv+=["--out",str(target)]
            with redirect_stdout(StringIO()) as stdout:
                self.assertEqual(topology.main(argv),1)
            self.assertIn("INCONCLUSIVE_GUEST_FRAME_TOPOLOGY",
                          stdout.getvalue())
            self.assertFalse(target.exists())


if __name__=="__main__":
    unittest.main()
