"""Synthetic tests: compare CPS-A/B capture registers at two MAME hooks.

Registers alone cannot establish same-frame timing. No ROMs/MAME needed.
"""
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tools.mame_obj_register_audit import (
    REG_BYTES, audit_registers, main,
)


STEM = 'frame-00000900'
OBJ_NAME = STEM + '.buffered-obj-be.bin'
REG_NAME = STEM + '.render-regs-be.bin'
A_NAME = STEM + '.cps-a-be.bin'
B_NAME = STEM + '.cps-b-be.bin'


def snapshot():
    return {
        'reference_frame': STEM,
        'buffered_obj_source': 'UNAVAILABLE_MAME_LUA',
        'pixel_parity_eligible': False,
    }


def components():
    obj = struct.pack('>1024H', *([0, 0, 0, 0xff00] + [0] * 1020))
    a = struct.pack('>32H', *(i * 19 for i in range(32)))
    b = struct.pack('>32H', *(i * 11 for i in range(32)))
    return obj, a + b, a, b


def audit(*, snapshot_data=None, obj_name=OBJ_NAME, reg_name=REG_NAME,
          a_name=A_NAME, b_name=B_NAME, obj=None, reg=None, a=None, b=None):
    baseline_obj, baseline_reg, baseline_a, baseline_b = components()
    return audit_registers(
        snapshot() if snapshot_data is None else snapshot_data,
        obj_name, baseline_obj if obj is None else obj,
        reg_name, baseline_reg if reg is None else reg,
        a_name, baseline_a if a is None else a,
        b_name, baseline_b if b is None else b,
    )


class MameObjRegisterAuditTests(unittest.TestCase):
    def test_equal_cps_a_and_b_registers_are_not_sync_proof(self):
        result = audit()
        self.assertTrue(result['registers_match_exactly'])
        self.assertTrue(result['frame_number_labels_match'])
        self.assertFalse(result['frame_sync_verified'])
        self.assertFalse(result['pixel_parity_eligible'])
        self.assertEqual(result['cps_a']['matching_words'], 32)
        self.assertEqual(result['cps_b']['matching_words'], 32)
        self.assertEqual(result['obj_first_end_marker_slot'], 0)
        self.assertEqual(len(result['obj_probe_sha256']), 64)
        self.assertEqual(len(result['register_probe_sha256']), 64)

    def test_single_cps_a_word_difference_identified(self):
        _, reg, a, b = components()
        changed = bytearray(a)
        changed[12] ^= 1
        report = audit(a=bytes(changed))
        self.assertFalse(report['registers_match_exactly'])
        self.assertEqual(report['cps_a']['mismatching_words'], 1)
        self.assertEqual(report['cps_a']['first_mismatched_word_indices'], [6])
        self.assertEqual(report['cps_b']['mismatching_words'], 0)
        self.assertFalse(report['frame_sync_verified'])

    def test_cps_b_mismatch_is_independent(self):
        _, _, _, b = components()
        changed = bytearray(b)
        changed[63] ^= 255
        result = audit(b=bytes(changed))
        self.assertEqual(result['cps_a']['mismatching_words'], 0)
        self.assertEqual(result['cps_b']['first_mismatched_word_indices'], [31])

    def test_first_eight_mismatch_locations_are_bounded(self):
        _, _, a, _ = components()
        changed = bytes(v ^ 0xff for v in a)
        result = audit(a=changed)
        self.assertEqual(result['cps_a']['mismatching_words'], 32)
        self.assertEqual(result['cps_a']['first_mismatched_word_indices'], list(range(8)))

    def test_reject_mismatched_frame_labels_and_path_names(self):
        for changed in (
                dict(obj_name='frame-00000901.buffered-obj-be.bin'),
                dict(reg_name='frame-00000901.render-regs-be.bin'),
                dict(a_name='frame-00000901.cps-a-be.bin'),
                dict(b_name='frame-00000901.cps-b-be.bin'),
                dict(reg_name='../' + REG_NAME)):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    audit(**changed)

    def test_reject_truncated_or_wrong_type_registers(self):
        for changed in (dict(reg=bytes(REG_BYTES - 1)),
                        dict(reg=bytes(REG_BYTES + 1)),
                        dict(a=bytes(63)), dict(b=bytes(65)),
                        dict(reg=bytearray(REG_BYTES))):
            with self.subTest(changed=list(changed)):
                with self.assertRaisesRegex(ValueError, 'expected exactly'):
                    audit(**changed)

    def test_reject_ineligible_or_faked_lua_capture(self):
        for field, value in (('pixel_parity_eligible', True),
                             ('buffered_obj_source', 'MAME_0289_CPP_OBJ_PROBE_UNSYNCED'),
                             ('reference_frame', 'frame-00000901')):
            bad = snapshot()
            bad[field] = value
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    audit(snapshot_data=bad)

    def test_cli_exclusive_file_output_and_metadata_only(self):
        obj, regs, a, b = components()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            paths = [root / (STEM + suffix) for suffix in (
                '.partial-snapshot.json', '.buffered-obj-be.bin',
                '.render-regs-be.bin', '.cps-a-be.bin', '.cps-b-be.bin')]
            for path, data in zip(paths, (json.dumps(snapshot()).encode(),
                                          obj, regs, a, b)):
                path.write_bytes(data)
            destination = root / 'frame-00000900.alignment-audit.json'
            args = [*(str(p) for p in paths), '--out', str(destination)]
            self.assertEqual(main(args), 0)
            report = json.loads(destination.read_text())
            self.assertFalse(report['frame_sync_verified'])
            self.assertNotIn('buffered_obj_words', report)
            self.assertEqual(main(args), 2)
            self.assertEqual(main([*(str(p) for p in paths),
                                   '--out', str(paths[0])]), 2)
            self.assertEqual(paths[1].read_bytes(), obj)


if __name__ == '__main__':
    unittest.main()
