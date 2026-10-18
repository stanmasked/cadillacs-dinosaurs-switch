"""Synthetic CSV tests; mock rows never prove emulator HID delivery."""
import csv
from pathlib import Path
import json
import tempfile
import unittest

from tools import verify_nexium_guest_controller as verifier


class GuestControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dino-hid-mock-')
        self.path = Path(self.temp.name) / 'mock.csv'
        self.rows = [['RESET', '1', '90', '0'],
                     ['INPUT_DONE', '31', '136', '1']]
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self, columns=None):
        with self.path.open('w', encoding='ascii', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(columns or verifier.COLUMNS)
            writer.writerows(self.rows)

    def test_full_effect_witness_passes_but_not_hardware_claim(self):
        result = verifier.verify(self.path)
        self.assertEqual(result['status'], 'GUEST_HID_EFFECTS_WITNESSED')
        self.assertEqual(result['buttons_and_effects_mask'], 31)
        self.assertEqual(result['player_x_after_input'], 136)
        self.assertFalse(result['physical_controller_hardware_verified'])
        self.assertFalse(result['host_to_guest_latency_verified'])

    def test_start_must_be_real_reset_state(self):
        for column, bad in ((1, '0'), (2, '91'), (3, '1')):
            with self.subTest(column=column):
                old = self.rows[0][column]
                self.rows[0][column] = bad
                self.write()
                with self.assertRaises(ValueError):
                    verifier.verify(self.path)
                self.rows[0][column] = old

    def test_missing_any_effect_fails_closed(self):
        for flags in ('1', '3', '7', '15', '30', '32', '0', '-1'):
            with self.subTest(flags=flags):
                self.rows[1][1] = flags
                self.write()
                with self.assertRaises(ValueError):
                    verifier.verify(self.path)
        self.rows[1][1] = '31'

    def test_missing_move_or_spar_fails_closed(self):
        for pos in ('90', '89', '369', '-1'):
            with self.subTest(position=pos):
                old=self.rows[1][2]
                self.rows[1][2] = pos
                self.write()
                with self.assertRaises(ValueError):
                    verifier.verify(self.path)
                self.rows[1][2] = old
        self.rows[1][3] = '0'
        self.write()
        with self.assertRaises(ValueError):
            verifier.verify(self.path)

    def test_missing_reordered_or_duplicate_rows_fail_closed(self):
        for replacement in ([], self.rows[:1],
                            list(reversed(self.rows)),
                            self.rows + [self.rows[1]]):
            with self.subTest(rows=replacement):
                before=self.rows
                self.rows=replacement
                self.write()
                with self.assertRaises(ValueError):
                    verifier.verify(self.path)
                self.rows=before

    def test_bad_integer_and_column_shape_refused(self):
        self.rows[1][2] = 'bad'
        self.write()
        with self.assertRaises(ValueError):
            verifier.verify(self.path)
        self.rows[1][2] = '136'
        self.write(columns=list(reversed(verifier.COLUMNS)))
        with self.assertRaises(ValueError):
            verifier.verify(self.path)
        self.rows[1].append('EXTRA')
        self.write()
        with self.assertRaises(ValueError):
            verifier.verify(self.path)

    def test_file_size_symlink_and_absence_refused(self):
        self.path.write_bytes(b'x' * 513)
        with self.assertRaises(ValueError):
            verifier.verify(self.path)
        self.path.unlink()
        with self.assertRaises(ValueError):
            verifier.verify(self.path)
        self.rows[1] = ['INPUT_DONE', '31', '136', '1']
        self.write()
        link = Path(self.temp.name) / 'alias.csv'
        try:
            link.symlink_to(self.path)
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(ValueError):
            verifier.verify(link)

    def test_missing_guest_trace_is_explicitly_inconclusive(self):
        self.path.unlink()
        out = Path(self.temp.name) / 'safe.json'
        self.assertEqual(verifier.main(['--report', str(self.path),
                                        '--out', str(out)]), 0)
        result = json.loads(out.read_text())
        self.assertEqual(result['status'], 'INCONCLUSIVE_NO_GUEST_HID_EFFECTS')
        self.assertNotIn(str(self.path), out.read_text())
        self.assertFalse(result['physical_controller_hardware_verified'])


if __name__ == '__main__':
    unittest.main()
