"""Pure synthetic CSV negatives. NOT evidence of a real emulated NRO."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import verify_nexium_audio_stress as check


class LongGuestAudioStressTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory(prefix='synthetic-audout-stress-')
        self.root=Path(self.t.name)
        self.path=self.root/'stress.csv'
        self.timeline=self.root/'hid.csv'
        self.controller=self.root/'controller.csv'
        self.out=self.root/'result.json'
        self.rows=[]
        for index,ticks in enumerate(check.CHECKPOINTS):
            # A real device's per-tick admission rates vary, but this
            # bounded fixture intentionally has one in-flight page.
            submitted=180+index*100
            released=179+index*100
            skipped=60+index*50
            self.rows.append([
                check.EVENTS[index],str(ticks),str(210+ticks),
                str(240+ticks),str(240+ticks),'1','1','1',
                str(submitted),str(released),str(skipped),'0',
                f'{index+1:016X}',str(skipped),'0','0','2',
                str(index*100),str(index*50),
                str(index*20),str(index*30),
                str(index*25),str(2 if index else 0),
            ])
        self.timeline.write_text(
            'event,tick,player_x,sparring,event_mask\n'
            'RESET,0,90,0,0\n'
            'MOVE,25,96,0,0\n'
            'ATTACK,80,180,0,8\n'
            'JUMP,112,180,0,2\n'
            'SPAR,143,180,1,1\n'
            'DONE,143,180,1,1\n',encoding='ascii')
        self.controller.write_text(
            'event,flags,player_x,sparring\nRESET,1,90,0\n'
            'INPUT_DONE,31,180,1\n',encoding='ascii')
        self.write()

    def tearDown(self):
        self.t.cleanup()

    def write(self,fields=None):
        with self.path.open('w',encoding='ascii',newline='') as stream:
            w=csv.writer(stream)
            w.writerow(fields if fields is not None else check.COLUMNS)
            w.writerows(self.rows)

    def mutate(self,index,column,bad):
        original=self.rows[index][column]
        self.rows[index][column]=bad
        self.write()
        try:
            with self.assertRaises(ValueError):
                check.verify(self.path,self.timeline,self.controller)
        finally:
            self.rows[index][column]=original
            self.write()

    def test_valid_900_ticks_with_bounded_queue_and_native_HID_binding(self):
        result=check.verify(self.path,self.timeline,self.controller)
        self.assertEqual(result['status'],'GUEST_900TICK_AUDOUT_FRAME_BATCH_CORRELATION_WITNESSED')
        self.assertEqual(result['simulation_ticks'],900)
        self.assertEqual(result['checkpoints'],7)
        self.assertEqual(result['audout_blocks_submitted'],600)
        self.assertEqual(result['audout_blocks_released'],600)
        self.assertEqual(result['audout_blocks_skipped'],300)
        self.assertEqual(result['peak_observed_pending'],1)
        self.assertEqual(result['full_queue_skips'],300)
        self.assertEqual(result['inactive_backend_skips'],0)
        self.assertEqual(result['unexpected_slot_skips'],0)
        self.assertEqual(result['max_skip_streak_since_audio_open'],2)
        self.assertEqual(result['checkpoint_skipped_deltas'],[50]*6)
        self.assertEqual(result['single_tick_render_steps'],600)
        self.assertEqual(result['batched_render_steps'],300)
        self.assertEqual(result['skips_in_single_tick_render_frames'],120)
        self.assertEqual(result['skips_in_batched_render_frames'],180)
        self.assertEqual(result['render_frames_with_batched_steps'],150)
        self.assertEqual(result['largest_scheduled_tick_batch'],2)
        self.assertEqual(result['single_skip_percent_rounded'],20)
        self.assertEqual(result['batched_skip_percent_rounded'],60)
        self.assertFalse(result['catchup_causality_verified'])
        self.assertFalse(result['host_wall_clock_real_time_verified'])
        self.assertFalse(result['sound_device_audible_verified'])
        self.assertFalse(result['audio_latency_verified'])

    def test_missing_duplicate_out_of_order_and_partial_checkpoints(self):
        before=self.rows
        for rows in (before[:-1],before+[before[-1]],
                     [before[1],before[0]]+before[2:],
                     before[:3]+before[4:],
                     before[:3]+[before[2]]+before[4:]):
            with self.subTest(size=len(rows)):
                self.rows=rows
                self.write()
                with self.assertRaises(ValueError):
                    check.verify(self.path,self.timeline,self.controller)
        self.rows=before
        self.write()

    def test_frozen_audio_ticks_and_pcm_clock_are_rejected(self):
        for column,bad in ((2,'359'),(3,'359'),(4,'359'),
                           (1,'149'),(1,'151')):
            with self.subTest(column=column,bad=bad):
                self.mutate(1,column,bad)

    def test_audout_queue_balance_and_cap_cannot_be_bypassed(self):
        for column,bad in ((7,'3'),(8,'281'),(9,'278'),
                           (9,'283'),(10,'109'),(11,'1')):
            with self.subTest(column=column,bad=bad):
                self.mutate(1,column,bad)

    def test_stalled_submission_rejected_even_when_all_ticks_dropped(self):
        # Starting at t=150, subsequent 150 ticks all get dropped.
        # Preserve the per-tick submitted+skipped sum; even so, there
        # must be at least one actual audout buffer accepted per span.
        prev=self.rows[1]
        self.rows[2][8]=prev[8]
        self.rows[2][9]=prev[9]
        self.rows[2][10]=str(int(prev[10])+150)
        self.write()
        with self.assertRaises(ValueError):
            check.verify(self.path,self.timeline,self.controller)

    def test_service_inactive_or_reset_while_stressing_is_inconclusive(self):
        for column,bad in ((5,'0'),(6,'0'),(11,'1')):
            with self.subTest(column=column):
                self.mutate(3,column,bad)

    def test_witness_must_keep_changing_and_be_uppercase_hash(self):
        self.mutate(2,12,self.rows[1][12])
        for bad in ('bad','abcde1234567890g','0'*15,'a'*16):
            with self.subTest(bad=bad):
                self.mutate(3,12,bad)

    def test_guest_HID_mismatch_blocks_audio_queue_claim(self):
        self.controller.write_text(
            'event,flags,player_x,sparring\nRESET,1,90,0\n'
            'INPUT_DONE,31,190,1\n',encoding='ascii')
        with self.assertRaises(ValueError):
            check.verify(self.path,self.timeline,self.controller)

    def test_refuse_missing_symlinked_oversized_and_extra_columns(self):
        self.write(fields=list(reversed(check.COLUMNS)))
        with self.assertRaises(ValueError):
            check.verify(self.path,self.timeline,self.controller)
        self.rows[0].append('forged')
        self.write()
        with self.assertRaises(ValueError):
            check.verify(self.path,self.timeline,self.controller)
        self.rows[0].pop()
        self.path.write_bytes(b'x'*4097)
        with self.assertRaises(ValueError):
            check.verify(self.path,self.timeline,self.controller)
        self.path.unlink()
        with self.assertRaises(ValueError):
            check.verify(self.path,self.timeline,self.controller)
        other=self.root/'alias.csv'
        self.write()
        other.symlink_to(self.path)
        with self.assertRaises(ValueError):
            check.verify(other,self.timeline,self.controller)

    def test_noncanonical_or_overflow_counters_rejected(self):
        for bad in ('+150','0150','-1','x','4294967296'):
            with self.subTest(bad=bad):
                self.mutate(1,1,bad)

    def test_tampered_classified_skip_total_is_refused(self):
        for i,col,value in ((2,13,'171'),(2,14,'1'),(2,15,'1'),
                             (1,13,'109'),(4,13,'999')):
            with self.subTest(row=i,column=col):
                self.mutate(i,col,value)

    def test_decreasing_or_impossible_consecutive_skip_streak_refused(self):
        for i,bad in ((1,'1'),(2,'301'),(1,'0'),(3,'2000')):
            with self.subTest(i=i,bad=bad):
                self.mutate(i,16,bad)
        # A maximum may increase, but must never decrease thereafter.
        self.rows[2][16]='3'
        self.write()
        with self.assertRaises(ValueError):
            check.verify(self.path,self.timeline,self.controller)
        self.rows[2][16]='2'
        self.write()

    def test_classification_must_agree_with_stress_deltas(self):
        # Splitting 50 skipped ticks between full and inactive while
        # preserving the sum is still a failed active-backend trial.
        self.rows[3][13]=str(int(self.rows[3][13])-1)
        self.rows[3][14]='1'
        self.write()
        with self.assertRaises(ValueError):
            check.verify(self.path,self.timeline,self.controller)
        self.rows[3][13]=str(int(self.rows[3][13])+1)
        self.rows[3][14]='0'
        self.write()

    def test_render_batch_ticks_must_partition_all_900_guest_ticks(self):
        for col,bad in ((17,'99'),(18,'49'),(17,'101'),(18,'0')):
            with self.subTest(column=col,value=bad):
                self.mutate(1,col,bad)

    def test_render_batch_skips_must_match_actual_queue_drop_counts(self):
        for col,bad in ((19,'19'),(20,'29'),(19,'101'),(20,'51')):
            with self.subTest(column=col,value=bad):
                self.mutate(1,col,bad)

    def test_render_batch_frames_and_largest_batch_must_be_bounded(self):
        for col,bad in ((21,'51'),(21,'0'),(22,'16'),(22,'1'),
                        (22,'0')):
            with self.subTest(column=col,value=bad):
                self.mutate(1,col,bad)

    def test_render_batch_counters_must_never_move_backwards(self):
        for col,bad in ((17,'99'),(18,'49'),(19,'19'),
                        (20,'29'),(21,'24'),(22,'1')):
            with self.subTest(column=col,value=bad):
                self.mutate(2,col,bad)

    def test_fake_batched_only_schedule_with_no_batched_frames_rejected(self):
        for idx in range(len(self.rows)):
            self.rows[idx][17]='0'
            self.rows[idx][18]=str(idx*150)
            self.rows[idx][19]='0'
            self.rows[idx][20]=str(idx*50)
            self.rows[idx][21]='0'
            self.rows[idx][22]=str(2 if idx else 0)
        self.write()
        with self.assertRaises(ValueError):
            check.verify(self.path,self.timeline,self.controller)

    def test_direct_CLI_missing_trace_stays_inconclusive_and_path_free(self):
        script=Path(__file__).resolve().parents[1]/'tools'/'verify_nexium_audio_stress.py'
        cmd=[sys.executable,str(script),'--report',str(self.path),
             '--timeline',str(self.timeline),'--controller',str(self.controller),
             '--out',str(self.out)]
        ok=subprocess.run(cmd,cwd=self.root,capture_output=True,text=True)
        self.assertEqual(ok.returncode,0,ok.stderr)
        self.assertEqual(json.loads(self.out.read_text())['status'],
                         'GUEST_900TICK_AUDOUT_FRAME_BATCH_CORRELATION_WITNESSED')
        self.path.unlink()
        fail=subprocess.run(cmd,cwd=self.root,capture_output=True,text=True)
        self.assertEqual(fail.returncode,0,fail.stderr)
        report=json.loads(self.out.read_text())
        self.assertEqual(report['status'],
                         'INCONCLUSIVE_NO_GUEST_AUDIO_RENDER_BATCH_EVIDENCE')
        self.assertNotIn(str(self.root),self.out.read_text())


if __name__=='__main__':
    unittest.main()
