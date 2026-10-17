"""Synthetic V2 checksum pairing for private MAME OBJ latch observations.

No original game ROM, binary source or live MAME frame is used.
"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from tools.mame_obj_latch_evidence import latch_counter_diagnostic, obj_fnv1a64
from tools.mame_obj_sequence_alignment import main
from test_mame_obj_cli_end_to_end import make_capture
from test_mame_obj_latch_evidence import write_counts


def write_v2(root, objs, counts, *, first=900, step=2):
    for i, (blob, count) in enumerate(zip(objs, counts)):
        path = root / f'frame-{first+i*step:08d}.obj-latch-count.txt'
        path.write_bytes(
            f'CPS1_DINO_LATCH_V2 {count} {obj_fnv1a64(blob)}\n'.encode('ascii'))


class MameLatchObjFingerprintTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        make_capture(self.root)
        self.objs = [(
            self.root / f'frame-{900+i*2:08d}.buffered-obj-be.bin'
        ).read_bytes() for i in range(6)]

    def diagnose(self):
        return latch_counter_diagnostic(
            self.root, 900, 6, 2, [0] * 5, obj_frames=self.objs)

    def test_zero_obj_known_fingerprint_and_exact_sized_input(self):
        self.assertEqual(obj_fnv1a64(bytes(2048)), '28c31cf8df2ec325')
        self.assertEqual(len(obj_fnv1a64(bytes(2048))), 16)
        for invalid in [bytes(2047), bytes(2049), bytearray(2048), None]:
            with self.subTest(invalid_type=type(invalid).__name__):
                with self.assertRaises(ValueError):
                    obj_fnv1a64(invalid)

    def test_fingerprint_uses_bytes_in_serialized_big_endian_order(self):
        a = bytearray(2048)
        b = bytearray(2048)
        a[2:4] = b'\x12\x34'
        b[2:4] = b'\x34\x12'
        self.assertNotEqual(obj_fnv1a64(bytes(a)), obj_fnv1a64(bytes(b)))

    def test_all_v2_samples_bound_in_synthetic_complete_series(self):
        write_v2(self.root, self.objs, [21, 23, 25, 27, 29, 31])
        result = self.diagnose()
        self.assertEqual(result['sidecar_format_version'], 2)
        self.assertEqual(result['obj_byte_fingerprint_binding'],
                         'FNV1A64_ALL_SAMPLES_MATCHED')
        self.assertEqual(result['obj_byte_fingerprint_verified_count'], 6)
        self.assertFalse(result['obj_byte_fingerprint_is_cryptographic'])
        self.assertEqual(result['inter_sample_callback_deltas'], [2] * 5)
        self.assertFalse(result['frame_sync_verified'])

    def test_same_length_obj_mutation_is_rejected(self):
        write_v2(self.root, self.objs, [21, 23, 25, 27, 29, 31])
        changed = bytearray(self.objs[3])
        changed[100] = 1
        self.objs[3] = bytes(changed)
        with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'):
            self.diagnose()

    def test_swapped_obj_with_distinct_payload_is_rejected(self):
        varied = [bytearray(blob) for blob in self.objs]
        for i, blob in enumerate(varied):
            blob[i*7] = i+1
        self.objs = list(map(bytes, varied))
        write_v2(self.root, self.objs, [1, 2, 3, 4, 5, 6])
        self.objs[2], self.objs[3] = self.objs[3], self.objs[2]
        with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'):
            self.diagnose()

    def test_unbound_v2_without_buffer_is_rejected(self):
        write_v2(self.root, self.objs, [1, 2, 3, 4, 5, 6])
        with self.assertRaisesRegex(ValueError, 'requires original OBJ'):
            latch_counter_diagnostic(self.root, 900, 6, 2)

    def test_legacy_v1_remains_explicitly_unbound(self):
        write_counts(self.root, [1, 2, 3, 4, 5, 6])
        result = self.diagnose()
        self.assertEqual(result['sidecar_format_version'], 1)
        self.assertEqual(result['obj_byte_fingerprint_binding'],
                         'LEGACY_V1_NOT_BOUND')
        self.assertEqual(result['obj_byte_fingerprint_verified_count'], 0)

    def test_mixed_v1_v2_series_is_rejected(self):
        write_v2(self.root, self.objs, [1, 2, 3, 4, 5, 6])
        (self.root / 'frame-00000904.obj-latch-count.txt').write_text(
            'CPS1_DINO_LATCH_V1 3\n')
        with self.assertRaisesRegex(ValueError, 'mixed V1/V2'):
            self.diagnose()

    def test_modified_or_uppercase_hex_digest_is_rejected(self):
        write_v2(self.root, self.objs, [1, 2, 3, 4, 5, 6])
        target = self.root / 'frame-00000900.obj-latch-count.txt'
        valid = target.read_bytes()
        bad_lines = [
            valid[:-17]+b'G'+valid[-16:],
            b'CPS1_DINO_LATCH_V2 1 0000000000000000\n',
            b'CPS1_DINO_LATCH_V2 1 000000000000000\n',
            valid+b'\n',
        ]
        for bad in bad_lines:
            target.write_bytes(bad)
            with self.subTest(bad=bad[:33]):
                with self.assertRaises(ValueError):
                    self.diagnose()

    def test_counter_reset_still_fails_even_when_fingerprints_match(self):
        write_v2(self.root, self.objs, [9, 10, 11, 2, 3, 4])
        with self.assertRaisesRegex(ValueError, 'decreased'):
            self.diagnose()

    def test_invalid_obj_frames_series_rejected(self):
        write_v2(self.root, self.objs, [1, 2, 3, 4, 5, 6])
        for arr in [self.objs[:5], self.objs[:-1]+[bytearray(2048)],
                    self.objs[:-1]+[bytes(2047)]]:
            with self.subTest(length=len(arr)):
                with self.assertRaisesRegex(ValueError, 'fingerprint series'):
                    latch_counter_diagnostic(
                        self.root, 900, 6, 2, obj_frames=arr)

    def test_cli_v2_complete_report_is_diagnostic_only(self):
        write_v2(self.root, self.objs, [30, 32, 34, 36, 38, 40])
        output = self.root / 'passed.json'
        with contextlib.redirect_stdout(io.StringIO()):
            code = main([str(self.root), '--latch-count-evidence',
                         '--out', str(output)])
        self.assertEqual(code, 0)
        report = json.loads(output.read_text())
        metadata = report['obj_latch_count_evidence']
        self.assertEqual(metadata['sidecar_format_version'], 2)
        self.assertEqual(metadata['obj_byte_fingerprint_verified_count'], 6)
        self.assertFalse(metadata['obj_latch_age_verified'])
        self.assertFalse(metadata['frame_sync_verified'])
        self.assertFalse(report['pixel_parity_eligible'])
        self.assertNotIn('buffered_obj_words', output.read_text())

    def test_cli_corrupted_obj_refuses_to_write_result(self):
        write_v2(self.root, self.objs, [30, 32, 34, 36, 38, 40])
        path = self.root / 'frame-00000904.buffered-obj-be.bin'
        buf = bytearray(path.read_bytes())
        buf[100] ^= 0x80
        path.write_bytes(buf)
        output = self.root / 'refused.json'
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            code = main([str(self.root), '--latch-count-evidence',
                         '--out', str(output)])
        self.assertEqual(code, 2)
        self.assertFalse(output.exists())

    def test_v2_obj_changes_without_counter_increments_do_not_grant_parity(self):
        a = bytearray(self.objs[1])
        a[0] = 1
        self.objs[1] = bytes(a)
        write_v2(self.root, self.objs, [5, 5, 6, 7, 8, 9])
        data = latch_counter_diagnostic(
            self.root, 900, 6, 2, [1, 0, 0, 0, 0], obj_frames=self.objs)
        self.assertEqual(data['obj_changed_without_observed_latch_frames'], [902])
        self.assertEqual(data['obj_byte_fingerprint_verified_count'], 6)
        self.assertFalse(data['obj_latch_age_verified'])


if __name__ == '__main__':
    unittest.main()
