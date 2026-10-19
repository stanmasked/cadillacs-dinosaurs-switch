"""Host-only fixtures: they do NOT establish external emulator HID input."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import verify_nexium_hid_timeline as checker


class OrderedHidTimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='romfree-hid-order-fixture-')
        self.root = Path(self.temp.name)
        self.path = self.root / 'mock-timeline.csv'
        self.summary = self.root / 'mock-guest-controller.csv'
        self.rows = [
            ['RESET','0','90','0','0'],
            ['MOVE','3','96','0','0'],
            ['ATTACK','60','184','0','8'],
            ['JUMP','82','184','0','2'],
            ['SPAR','102','184','1','1'],
            ['DONE','102','184','1','1'],
        ]
        self.write()
        self.summary.write_text(
            'event,flags,player_x,sparring\n'
            'RESET,1,90,0\n'
            'INPUT_DONE,31,184,1\n', encoding='ascii'
        )

    def tearDown(self):
        self.temp.cleanup()

    def write(self, cols=None):
        with self.path.open('w', encoding='ascii', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(cols or checker.COLUMNS)
            writer.writerows(self.rows)

    def test_valid_ordered_trace_has_tick_intervals_but_no_latency_claim(self):
        result = checker.verify(self.path, self.summary)
        self.assertEqual(result['status'], 'GUEST_HID_ORDER_WITNESSED')
        self.assertEqual(result['events'], 6)
        self.assertEqual(result['guest_tick_intervals'], {
            'reset_to_move': 3, 'move_to_attack': 57,
            'attack_to_jump': 22, 'jump_to_spar': 20})
        self.assertFalse(result['host_to_guest_latency_verified'])
        self.assertFalse(result['physical_audio_latency_verified'])
        self.assertFalse(result['hardware_controller_verified'])

    def test_wrong_order_missing_duplicate_and_extra_rows(self):
        original = [list(r) for r in self.rows]
        cases = [
            original[:3]+original[4:],
            original[:4]+[original[3]]+original[4:],
            original[:2]+[original[3],original[2]]+original[4:],
            original+[original[5]],
            list(reversed(original)),
        ]
        for i, rows in enumerate(cases):
            with self.subTest(i=i):
                self.rows=rows
                self.write()
                with self.assertRaises(ValueError):
                    checker.verify(self.path, self.summary)
        self.rows=original

    def test_missing_required_guest_combat_events_rejected(self):
        for idx in (2,3,4):
            with self.subTest(idx=idx):
                orig=self.rows[idx][4]
                self.rows[idx][4]='0'
                self.write()
                with self.assertRaises(ValueError):
                    checker.verify(self.path, self.summary)
                self.rows[idx][4]=orig

    def test_tick_duplicates_regressions_and_unbounded_rejected(self):
        for idx, value in ((1,'0'),(2,'3'),(3,'60'),(4,'82'),
                           (4,'1801'),(2,'9999999999999999999')):
            with self.subTest(index=idx,value=value):
                old=self.rows[idx][1]
                self.rows[idx][1]=value
                self.write()
                with self.assertRaises(ValueError):
                    checker.verify(self.path, self.summary)
                self.rows[idx][1]=old

    def test_rightward_position_and_spar_state_invariants(self):
        for idx, col, value in ((1,2,'90'),(2,2,'50'),(3,2,'183'),
                                (4,2,'500'),(1,3,'1'),(3,3,'1'),
                                (4,3,'0'),(5,3,'0')):
            with self.subTest(idx=idx,col=col,value=value):
                old=self.rows[idx][col]
                self.rows[idx][col]=value
                self.write()
                with self.assertRaises(ValueError):
                    checker.verify(self.path, self.summary)
                self.rows[idx][col]=old

    def test_done_must_equal_spar_checkpoint(self):
        for col,val in ((1,'103'),(2,'185'),(3,'0'),(4,'3')):
            with self.subTest(col=col):
                old=self.rows[5][col]
                self.rows[5][col]=val
                self.write()
                with self.assertRaises(ValueError):
                    checker.verify(self.path, self.summary)
                self.rows[5][col]=old

    def test_summary_binding_refuses_different_guest_x(self):
        self.summary.write_text(
            'event,flags,player_x,sparring\n'
            'RESET,1,90,0\n'
            'INPUT_DONE,31,200,1\n',encoding='ascii')
        with self.assertRaises(ValueError):
            checker.verify(self.path, self.summary)

    def test_missing_corrupt_and_symlinked_summary_fail_closed(self):
        self.summary.unlink()
        with self.assertRaises(ValueError):
            checker.verify(self.path, self.summary)
        self.summary.write_text('not,csv\n',encoding='ascii')
        with self.assertRaises(ValueError):
            checker.verify(self.path, self.summary)
        self.summary.unlink()
        self.summary.symlink_to(self.path)
        with self.assertRaises(ValueError):
            checker.verify(self.path, self.summary)

    def test_column_mismatch_and_ragged_records_rejected(self):
        self.write(cols=list(reversed(checker.COLUMNS)))
        with self.assertRaises(ValueError):
            checker.verify(self.path)
        self.rows[3].append('BAD')
        self.write()
        with self.assertRaises(ValueError):
            checker.verify(self.path)

    def test_canonical_integer_and_mask_bounds_rejected(self):
        for idx,col,val in ((1,1,'+3'),(2,1,'03'),(4,4,'2048'),
                            (3,4,'0x2'),(4,2,'-5'),(1,2,'NaN')):
            with self.subTest(idx=idx,col=col,val=val):
                old=self.rows[idx][col]
                self.rows[idx][col]=val
                self.write()
                with self.assertRaises(ValueError):
                    checker.verify(self.path)
                self.rows[idx][col]=old

    def test_missing_symlinked_and_oversized_timeline_rejected(self):
        self.path.unlink()
        with self.assertRaises(ValueError):
            checker.verify(self.path)
        self.write()
        alias=self.root/'alias.csv'
        alias.symlink_to(self.path)
        with self.assertRaises(ValueError):
            checker.verify(alias)
        self.path.write_bytes(b'X'*1025)
        with self.assertRaises(ValueError):
            checker.verify(self.path)

    def test_direct_script_mode_works_outside_tools_package(self):
        self.path.unlink()
        output = self.root / 'direct-mode.json'
        script = Path(__file__).resolve().parents[1] / 'tools' / 'verify_nexium_hid_timeline.py'
        proc = subprocess.run(
            [sys.executable, str(script), '--report', str(self.path),
             '--summary', str(self.summary), '--out', str(output)],
            cwd=self.root, capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(output.read_text())
        self.assertEqual(report['status'],
                         'INCONCLUSIVE_NO_ORDERED_GUEST_HID_TRACE')
        self.assertFalse(report['host_to_guest_latency_verified'])

    def test_cli_inconclusive_never_reports_paths_or_latency(self):
        self.path.unlink()
        output=self.root/'result.json'
        self.assertEqual(checker.main([
            '--report',str(self.path), '--summary',str(self.summary),
            '--out',str(output)]),0)
        data=json.loads(output.read_text())
        self.assertEqual(data['status'],'INCONCLUSIVE_NO_ORDERED_GUEST_HID_TRACE')
        self.assertNotIn(str(self.path),output.read_text())
        self.assertFalse(data['host_to_guest_latency_verified'])


if __name__=='__main__':
    unittest.main()
