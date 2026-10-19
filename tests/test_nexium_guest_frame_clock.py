"""Portable ROM-free tests of guest clamped frame-interval RAM witness.

The 900-tick test trace is SYNTHETIC and cannot be used to make NeXium
or hardware audio timing claims. Real paired CI checks mode and NRO SHA.
"""
import copy
import csv
from io import StringIO
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import verify_nexium_guest_frame_clock as witness
from test_nexium_audio_ack_tick_trace import fixture

ROOT=Path(__file__).resolve().parents[1]
NATIVE=r'''
#include "dino_guest_frame_clock.h"
#include <stdint.h>
#include <stdio.h>
static DinoGuestFrameClock trace;
int main(int argc,char **argv) {
    if(argc!=2) return 1;
    dino_guest_frame_clock_reset(&trace);
    if(dino_guest_frame_clock_write_csv(stdout,&trace)) return 2;
    for(uint32_t i=0;i<900u;++i) {
        DinoGuestFrameClockRow r={i+1u,16666666u,1u,1u};
        if(!dino_guest_frame_clock_append(&trace,r)) return 3;
    }
    if(trace.stress_ticks!=900u || trace.used!=900u) return 4;
    FILE *out=fopen(argv[1],"w");
    if(!out) return 5;
    if(!dino_guest_frame_clock_write_csv(out,&trace)) return 6;
    if(fclose(out)!=0) return 7;
    DinoGuestFrameClockRow invalid={901u,250000001u,0u,0u};
    if(dino_guest_frame_clock_append(&trace,invalid) || !trace.overflow)
        return 8;
    dino_guest_frame_clock_reset(&trace);
    DinoGuestFrameClockRow tiny={1u,1u,0u,0u};
    if(!dino_guest_frame_clock_append(&trace,tiny)) return 9;
    if(dino_guest_frame_clock_write_csv(stdout,&trace)) return 10;
    return 0;
}
'''


class GuestFrameClockWitnessTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("gcc"),"Native GCC compiler required")
    def test_native_c_collector_requires_all_900_ticks_before_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)
            harness=p/"harness.c"
            harness.write_text(NATIVE,encoding="ascii")
            exe=p/"runner"
            cmd=["gcc","-std=c11","-O2","-Wall","-Wextra","-Werror",
                 "-Isource",str(harness),"source/dino_guest_frame_clock.c",
                 "-o",str(exe)]
            build=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            target=p/"frame-clock.csv"
            run=subprocess.run([str(exe),str(target)],cwd=ROOT,
                               capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            raw,frames=witness.read_clock(target)
            self.assertEqual(len(frames),900)
            self.assertEqual(frames[-1]["stress_game_ticks"],1)
            rows,_=fixture()
            result=witness.witness_clock(frames,rows)
            self.assertEqual(result["reconciled_actual_guest_audio_ticks"],900)
            self.assertEqual(result["frame_rows"],900)
            self.assertEqual(result["zero_game_tick_render_iterations"],0)
            self.assertEqual(result["scheduler_interval_ns_p95_order_statistic"],
                             16666666)
            self.assertFalse(result["uncapped_host_elapsed_time_verified"])

    def test_zero_simulation_tick_frames_are_accounted_without_fake_ack(self):
        rows,_=fixture()
        frames=[]
        fid=0
        for i,row in enumerate(rows):
            if i%150==0 and i:
                fid+=1
                frames.append({"frame_id":fid,"elapsed_ns_capped":0,
                               "frame_game_ticks":0,"stress_game_ticks":0})
            fid+=1
            row["frame_id"]=fid
            frames.append({"frame_id":fid,"elapsed_ns_capped":16666666,
                           "frame_game_ticks":1,"stress_game_ticks":1})
        result=witness.witness_clock(frames,rows)
        self.assertEqual(result["frame_rows"],905)
        self.assertEqual(result["zero_game_tick_render_iterations"],5)
        self.assertEqual(result["maximum_consecutive_zero_tick_render_iterations"],1)
        self.assertEqual(result["scheduler_interval_ns_min"],0)
        self.assertEqual(result["reconciled_actual_guest_audio_ticks"],900)

    def test_boundary_partial_frames_are_not_falsely_complete(self):
        rows,_=fixture()
        rows[0].update({"batch_size":2,"batch_position":1})
        rows[-1].update({"batch_size":2,"batch_position":0})
        frames=[]
        for i,row in enumerate(rows):
            frames.append({"frame_id":i+1,"elapsed_ns_capped":10000000,
                           "frame_game_ticks":2 if i in (0,899) else 1,
                           "stress_game_ticks":1})
        result=witness.witness_clock(frames,rows)
        self.assertTrue(result["first_frame_left_clipped_possible"])
        self.assertTrue(result["last_frame_right_clipped_possible"])

    def test_missing_ticks_forged_frame_lengths_and_capped_clock_are_rejected(self):
        rows,_=fixture()
        base=[{"frame_id":i+1,"elapsed_ns_capped":16666666,
               "frame_game_ticks":1,"stress_game_ticks":1}
              for i in range(900)]
        for item,value in (("elapsed_ns_capped",250000001),
                           ("frame_game_ticks",16),
                           ("stress_game_ticks",2),
                           ("frame_id",True),
                           ("frame_id",3)):
            edited=copy.deepcopy(base)
            edited[1][item]=value
            with self.subTest(item=item),self.assertRaises(ValueError):
                witness.witness_clock(edited,rows)
        for edited in (base[:-1],base+[base[-1]],[]):
            with self.assertRaises(ValueError):
                witness.witness_clock(edited,rows)
        mutated=copy.deepcopy(rows)
        mutated[17]["frame_id"]=99
        with self.assertRaises(ValueError):
            witness.witness_clock(base,mutated)

    def test_parser_refuses_noncanonical_and_oversized_frame_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/"frame.csv"
            target.write_text(
                ",".join(witness.COLS)+"\n01,0,1,1\n",encoding="ascii")
            with self.assertRaises(ValueError):
                witness.read_clock(target)
            target.write_text(",".join(witness.COLS)+"\n1,0,1,1\n",
                              encoding="ascii")
            raw,rows=witness.read_clock(target)
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]["frame_id"],1)
            target.write_bytes(b"0"*260000)
            with self.assertRaises(ValueError):
                witness.read_clock(target)
            target.unlink()
            target.symlink_to(Path(folder)/"missing")
            with self.assertRaises(ValueError):
                witness.read_clock(target)

    def test_selftest_only_no_extra_clock_reads_in_capture(self):
        text=(ROOT/"source/main.c").read_text(encoding="utf-8")
        self.assertIn('#include "dino_guest_frame_clock.h"',text)
        capture=text.split("if (guest_frame_clock_started && "
                           "!guest_frame_clock_flushed) {",1)[1].split(
                               "if (guest_witness && arena_active)",1)[0]
        self.assertIn("dino_guest_frame_clock_append(",capture)
        self.assertNotIn("armGetSystemTick(",capture)
        self.assertIn("guest_frame_full_game_ticks",capture)
        self.assertIn("guest_ack_tick_count-guest_ack_before_this_frame",capture)
        self.assertEqual(text.count("dino_guest_frame_clock_write_csv("),1)
        impl=(ROOT/"source/dino_guest_frame_clock.c").read_text(encoding="utf-8")
        self.assertNotIn("sdmc:/",impl)
        self.assertNotIn("audoutGetReleasedAudioOutBuffer",impl)


if __name__=="__main__":
    unittest.main()
