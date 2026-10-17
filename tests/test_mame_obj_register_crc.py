"""ROM-free CRC evidence tests for CPS-A/B cross-hook register comparison.

This test intentionally keeps source capture provenance unverified and never
raises frame_sync_verified or pixel_parity_eligible.
"""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.mame_obj_register_audit import audit_registers, main

STEM = 'frame-00000900'
CAPTURE_NAMES = (
    'gfxram-be.bin', 'cps-a-be.bin', 'cps-b-be.bin',
    'palette-rgb24.bin', 'reference-rgb24.bin',
)


def fixture():
    obj = struct.pack('>1024H', *([0, 0, 0, 0xff00] + [0]*1020))
    cps_a = struct.pack('>32H', *(i * 97 for i in range(32)))
    cps_b = struct.pack('>32H', *(i * 23 for i in range(32)))
    return obj, cps_a + cps_b, cps_a, cps_b


def hashes(a, b):
    result = {name: '00000000' for name in CAPTURE_NAMES}
    result['cps-a-be.bin'] = f'{zlib.crc32(a) & 0xffffffff:08x}'
    result['cps-b-be.bin'] = f'{zlib.crc32(b) & 0xffffffff:08x}'
    return result


def scene(digests=True):
    _, _, a, b = fixture()
    result = {
        'reference_frame': STEM,
        'buffered_obj_source': 'UNAVAILABLE_MAME_LUA',
        'pixel_parity_eligible': False,
    }
    if digests:
        result['capture_file_crc32'] = hashes(a, b)
    return result


def check(snapshot=None, *, obj=None, regs=None, a=None, b=None):
    base_obj, base_reg, base_a, base_b = fixture()
    return audit_registers(
        scene() if snapshot is None else snapshot,
        STEM + '.buffered-obj-be.bin', base_obj if obj is None else obj,
        STEM + '.render-regs-be.bin', base_reg if regs is None else regs,
        STEM + '.cps-a-be.bin', base_a if a is None else a,
        STEM + '.cps-b-be.bin', base_b if b is None else b,
    )


class LuaRegisterCrcEvidenceTests(unittest.TestCase):
    def test_good_two_file_checksums_and_equal_raw_values(self):
        result = check()
        self.assertTrue(result['registers_match_exactly'])
        self.assertTrue(result['cross_hook_register_evidence_with_crc'])
        self.assertTrue(result['lua_register_integrity']['register_crc32_match'])
        self.assertEqual(result['lua_register_integrity']['verified_register_files'], 2)
        self.assertFalse(result['frame_sync_verified'])
        self.assertFalse(result['pixel_parity_eligible'])

    def test_legacy_snapshot_remains_diagnostic_but_not_crc_supported(self):
        result = check(scene(digests=False))
        self.assertTrue(result['registers_match_exactly'])
        self.assertFalse(result['cross_hook_register_evidence_with_crc'])
        self.assertEqual(result['lua_register_integrity']['verified_register_files'], 0)
        self.assertFalse(result['frame_sync_verified'])

    def test_crc_match_does_not_hide_mismatched_video_register(self):
        _, raw, a, b = fixture()
        changed = bytearray(raw)
        changed[4] ^= 1
        report = check(regs=bytes(changed))
        self.assertTrue(report['lua_register_integrity']['register_crc32_match'])
        self.assertFalse(report['registers_match_exactly'])
        self.assertFalse(report['cross_hook_register_evidence_with_crc'])
        self.assertEqual(report['cps_a']['first_mismatched_word_indices'], [2])

    def test_same_size_mutation_of_lua_cps_a_is_rejected(self):
        _, _, a, b = fixture()
        changed = bytearray(a)
        changed[0] ^= 1
        with self.assertRaisesRegex(ValueError, 'cps-a-be.bin'):
            check(a=bytes(changed))

    def test_same_size_mutation_of_lua_cps_b_is_rejected(self):
        _, _, a, b = fixture()
        changed = bytearray(b)
        changed[-1] ^= 1
        with self.assertRaisesRegex(ValueError, 'cps-b-be.bin'):
            check(b=bytes(changed))

    def test_swapped_a_b_same_length_is_rejected(self):
        _, _, a, b = fixture()
        self.assertEqual(len(a), len(b))
        with self.assertRaisesRegex(ValueError, 'CRC32'):
            check(a=b, b=a)

    def test_malformed_or_missing_manifest_fields_fail_closed(self):
        complete = scene()
        for bad in (None, {}, [], dict(complete['capture_file_crc32'], unknown='12345678')):
            snap = scene()
            snap['capture_file_crc32'] = bad
            # An absent field is different from an explicit malformed field.
            if bad is None:
                snap['capture_file_crc32'] = []
            with self.subTest(digests=bad):
                with self.assertRaisesRegex(ValueError, 'five capture_file_crc32'):
                    check(snap)
        snap = scene()
        del snap['capture_file_crc32']['reference-rgb24.bin']
        with self.assertRaisesRegex(ValueError, 'five capture_file_crc32'):
            check(snap)

    def test_bad_crc_format_is_rejected_even_for_other_file(self):
        for value in ('ABCDEF12', '1234567', '0x12345678',
                      '123456789', 'bad_____','00000000\\n', 0):
            snap = scene()
            snap['capture_file_crc32']['palette-rgb24.bin'] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'malformed'):
                    check(snap)

    def test_cli_require_flag_accepts_only_bound_register_inputs(self):
        obj, regs, a, b = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = [root / (STEM + suffix) for suffix in (
                '.partial-snapshot.json', '.buffered-obj-be.bin',
                '.render-regs-be.bin', '.cps-a-be.bin', '.cps-b-be.bin')]
            for path, data in zip(inputs, (json.dumps(scene()).encode(),
                                          obj, regs, a, b)):
                path.write_bytes(data)
            out = root/'evidence.json'
            args = [*(str(p) for p in inputs), '--out', str(out),
                    '--require-register-crc']
            self.assertEqual(main(args), 0)
            report = json.loads(out.read_text())
            self.assertTrue(report['cross_hook_register_evidence_with_crc'])
            self.assertFalse(report['frame_sync_verified'])
            out.unlink()
            inputs[0].write_text(json.dumps(scene(digests=False)))
            self.assertEqual(main(args), 2)
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main()
