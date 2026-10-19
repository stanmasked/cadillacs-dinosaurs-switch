"""ROM-free synthetic tests for parsing guest-origin NeXium evidence.

Mock CSVs are NOT actual emulator execution or proof of Switch GPU/audio.
"""
import csv
from pathlib import Path
import tempfile
import unittest
from tools import verify_nexium_guest_replay as verifier


class NeXiumGuestEvidenceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='dino-guest-csv-mock-')
        self.file=Path(self.temp.name)/'synthetic-replay.csv'
        self.rows=[
            ['START','0','90','5','0','CBF29CE484222325',
             'CBF29CE484222325','0',
             '0','1','1','0','0','0','0','0'],
            ['FRAME_SUBMITTED','1','92','5','0','0123456789ABCDEF',
             'CBF29CE484222325','1',
             '1','1','1','1','1','0','0','0'],
            ['REPLAY_DONE','180','230','4','3',verifier.EXPECTED_STATE,
             verifier.EXPECTED_PCM,'180',
             '180','1','1','2','120','118','60','0'],
        ]
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self,columns=None):
        with self.file.open('w',newline='') as f:
            writer=csv.writer(f)
            writer.writerow(columns or verifier.COLUMNS)
            writer.writerows(self.rows)

    def test_synthetic_valid_shape_is_only_parser_evidence(self):
        result=verifier.verify(self.file)
        self.assertEqual(result['status'],'GUEST_REPLAY_WITNESSED')
        self.assertTrue(result['guest_frame_submitted'])
        self.assertEqual(result['guest_controller_trace_steps'],180)
        self.assertTrue(result['guest_audio_queue_valid'])
        self.assertTrue(result['guest_audio_service_active_at_end'])
        self.assertEqual(result['guest_audio_submitted_at_end'],120)
        self.assertEqual(result['guest_audio_released_at_end'],118)
        self.assertEqual(result['guest_audio_skipped_at_end'],60)
        self.assertFalse(result['device_audio_audible_verified'])
        self.assertFalse(result['host_screen_pixels_verified'])

    def test_missing_or_duplicate_frame_and_end_marker_rejected(self):
        for change in ('no_frame','no_done','repeat_frame','wrong_order'):
            with self.subTest(change=change):
                source=[list(r) for r in self.rows]
                if change=='no_frame':self.rows=[source[0],source[2]]
                elif change=='no_done':self.rows=source[:2]
                elif change=='repeat_frame':self.rows=[source[0],source[1],source[1]]
                else:self.rows=[source[1],source[0],source[2]]
                self.write()
                with self.assertRaises(ValueError):
                    verifier.verify(self.file)
                self.rows=source

    def test_game_state_and_pcm_digests_fail_independently(self):
        for index in (5,6):
            original=self.rows[2][index]
            self.rows[2][index]='0'*16
            self.write()
            with self.assertRaises(ValueError):
                verifier.verify(self.file)
            self.rows[2][index]=original

    def test_wrong_ticks_coordinates_hits_and_generated_pcm_frames(self):
        for column,wrong in ((1,'179'),(2,'231'),(3,'5'),(4,'2'),
                             (7,'179')):
            with self.subTest(column=column):
                prior=self.rows[2][column]
                self.rows[2][column]=wrong
                self.write()
                with self.assertRaises(ValueError):
                    verifier.verify(self.file)
                self.rows[2][column]=prior

    def test_ragged_columns_and_large_or_symlinked_files_fail_closed(self):
        self.rows[1].append('BAD')
        self.write()
        with self.assertRaises(ValueError):
            verifier.verify(self.file)
        self.rows[1].pop()
        self.write(columns=list(reversed(verifier.COLUMNS)))
        with self.assertRaises(ValueError):
            verifier.verify(self.file)
        self.file.write_text('x'*4097)
        with self.assertRaises(ValueError):
            verifier.verify(self.file)
        alias=Path(self.temp.name)/'aliased.csv'
        try:
            alias.symlink_to(self.file)
        except (OSError,NotImplementedError):
            return
        with self.assertRaises(ValueError):
            verifier.verify(alias)


    def test_audio_queue_pending_and_release_invariants(self):
        for index, bad in ((11,'3'),(11,'1'),(12,'181'),
                           (13,'121'),(13,'-1'),(14,'181')):
            with self.subTest(index=index,bad=bad):
                previous=self.rows[2][index]
                self.rows[2][index]=bad
                self.write()
                with self.assertRaises(ValueError):
                    verifier.verify(self.file)
                self.rows[2][index]=previous

    def test_guest_audio_tick_count_follows_simulation(self):
        for row_index in (0,1,2):
            with self.subTest(row=row_index):
                previous=self.rows[row_index][8]
                self.rows[row_index][8]='178'
                self.write()
                with self.assertRaises(ValueError):
                    verifier.verify(self.file)
                self.rows[row_index][8]=previous

    def test_audio_service_flags_and_error_bounds(self):
        for index,bad in ((9,'2'),(10,'0'),(15,'182'),(15,'-1')):
            with self.subTest(index=index,bad=bad):
                previous=self.rows[2][index]
                self.rows[2][index]=bad
                self.write()
                with self.assertRaises(ValueError):
                    verifier.verify(self.file)
                self.rows[2][index]=previous

    def test_valid_silent_fallback_does_not_claim_sound(self):
        # No host sound card is required for the generated-PCM witness.
        for index,row in enumerate(self.rows):
            ticks=int(row[1])
            row[9]='0'    # audout unavailable
            row[11]='0'   # pending
            row[12]='0'   # submitted
            row[13]='0'   # released
            row[14]=str(ticks)  # all generated ticks discarded
            row[15]='1'   # failed initialization recorded
        self.write()
        got=verifier.verify(self.file)
        self.assertEqual(got['guest_audio_submitted_at_end'],0)
        self.assertEqual(got['guest_audio_skipped_at_end'],180)
        self.assertFalse(got['guest_audio_service_active_at_end'])
        self.assertFalse(got['device_audio_audible_verified'])

    def test_idle_audio_backend_cannot_have_pending_buffers(self):
        self.rows[2][9]='0'
        self.write()
        with self.assertRaises(ValueError):
            verifier.verify(self.file)

    def test_audio_fields_must_be_complete_numeric_and_ordered(self):
        for bad in ('oops','','+1','1.1'):
            with self.subTest(bad=bad):
                old=self.rows[2][12]
                self.rows[2][12]=bad
                self.write()
                with self.assertRaises(ValueError):
                    verifier.verify(self.file)
                self.rows[2][12]=old
        self.write(columns=verifier.COLUMNS[:8]+
                   list(reversed(verifier.COLUMNS[8:])))
        with self.assertRaises(ValueError):
            verifier.verify(self.file)

    def test_cli_returns_inconclusive_with_only_safe_generic_message(self):
        self.rows[2][5]='BADHASH'
        self.write()
        out=Path(self.temp.name)/'result.txt'
        self.assertEqual(verifier.main(['--report',str(self.file),
                                        '--out',str(out)]),1)
        self.assertTrue(out.read_text().startswith('INCONCLUSIVE:'))
        self.assertNotIn(str(self.file),out.read_text())


if __name__=='__main__':
    unittest.main()
