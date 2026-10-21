"""ROM-free synthetic tests for the private WolfMAME 0.106 capture request."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from tools import wolfmame0106_reference_capture_plan as plan

def summary():
    return {
        "schema":"dino-wolfmame0106-input-mapping-rom-free-v1",
        "status":"STRUCTURAL_PORT_INFERENCE_NOT_REPLAY_VERIFIED",
        "game":"dino",
        "frames":7200,
        "total_press_onsets":200,
        "port_byte_offsets":{"system":3,"p1":19,"p2":18,"p3":23},
        "original_0_106_serializer_confirmed":False,
        "distinct_human_players_confirmed":False,
        "native_gameplay_or_sprite_parity_confirmed":False,
        "safe_to_publish_original_files":False,
        "candidate_private_replay_capture_windows":[
            {"start_frame":0,"end_frame_exclusive":1200,
             "player1_action_onsets":5},
            {"start_frame":2400,"end_frame_exclusive":3600,
             "player1_action_onsets":9},
            {"start_frame":4800,"end_frame_exclusive":6000,
             "player1_action_onsets":8},
        ],
    }

class CapturePlanTests(unittest.TestCase):
    def test_two_tier_schedule_and_densest_window(self):
        d=plan.create_plan(summary())
        self.assertEqual(d["overview_frame_count"],60)
        self.assertEqual(d["detail_frame_count"],1200)
        self.assertEqual(d["animation_detail"]["start_frame"],2400)
        self.assertEqual(d["overview"]["requested_frames"][:3],[0,60,120])
        self.assertEqual(d["overview"]["requested_frames"][-1],5940)
        self.assertEqual(d["animation_detail"]["requested_frames"][-1],3599)
        self.assertFalse(d["actual_emulator_frames_captured"])

    def test_deterministic_summary_binding(self):
        a=plan.create_plan(summary())
        b=plan.create_plan(summary())
        self.assertEqual(a["summary_sha256"],b["summary_sha256"])
        changed=summary()
        changed["total_press_onsets"]=201
        c=plan.create_plan(changed)
        self.assertNotEqual(a["summary_sha256"],c["summary_sha256"])

    def test_forbid_unverified_authenticity_upgrade(self):
        for name in ("original_0_106_serializer_confirmed",
                     "distinct_human_players_confirmed",
                     "native_gameplay_or_sprite_parity_confirmed",
                     "safe_to_publish_original_files"):
            with self.subTest(name=name):
                src=summary()
                src[name]=True
                with self.assertRaises(ValueError):
                    plan.create_plan(src)

    def test_reject_wrong_player_order(self):
        src=summary()
        src["port_byte_offsets"]["p1"]=18
        src["port_byte_offsets"]["p2"]=19
        with self.assertRaisesRegex(ValueError,"byte ordering"):
            plan.create_plan(src)

    def test_reject_overlapping_or_non_frame_aligned(self):
        for bad in (1100,1200,1250,2501,-1,7200):
            src=summary()
            src["candidate_private_replay_capture_windows"][1]["start_frame"]=bad
            with self.subTest(start=bad),self.assertRaises(ValueError):
                plan.create_plan(src)

    def test_reject_window_beyond_record(self):
        src=summary()
        src["candidate_private_replay_capture_windows"][2]["end_frame_exclusive"]=8000
        with self.assertRaises(ValueError):
            plan.create_plan(src)

    def test_reject_bool_as_integer(self):
        src=summary()
        src["candidate_private_replay_capture_windows"][0]["player1_action_onsets"]=True
        with self.assertRaises(ValueError):
            plan.create_plan(src)

    def test_read_rejects_duplicate_json_key(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"dup.json"
            target.write_text('{"frames":7200,"frames":7200,'+'"a":"synthetic"}')
            with self.assertRaisesRegex(ValueError,"duplicate JSON key"):
                plan.read_source(target)

    def test_read_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"source.json"
            target.write_text(json.dumps(summary()))
            link=Path(folder)/"link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError,"ordinary"):
                plan.read_source(link)

if __name__=="__main__":
    unittest.main()
