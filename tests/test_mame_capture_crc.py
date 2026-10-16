"""Synthetic, ROM-free checks for MAME frame CRC32 manifests."""
import unittest
import zlib

from tools.mame_capture_crc import (
    CAPTURE_FILES, capture_checksums, validate_capture_checksums,
)


def sample_files():
    return {name:bytes([i+1])* (11+i) for i,name in enumerate(CAPTURE_FILES)}


class MameCaptureIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.files=sample_files()
        self.manifest={'file_crc32':capture_checksums(self.files)}

    def test_standard_crc32_check_vector(self):
        self.files['gfxram-be.bin']=b'123456789'
        self.assertEqual(capture_checksums(self.files)['gfxram-be.bin'],'cbf43926')

    def test_round_trip_all_five_files(self):
        hashes=validate_capture_checksums(self.manifest,self.files)
        self.assertEqual(hashes,self.manifest['file_crc32'])
        self.assertEqual(set(hashes),set(CAPTURE_FILES))
        self.assertTrue(all(len(digest)==8 for digest in hashes.values()))

    def test_empty_file_crc32_is_eight_zeroes(self):
        self.files['cps-b-be.bin']=b''
        self.assertEqual(capture_checksums(self.files)['cps-b-be.bin'],'00000000')

    def test_same_size_corruption_is_rejected(self):
        for name in CAPTURE_FILES:
            with self.subTest(file=name):
                bad=dict(self.files)
                blob=bytearray(bad[name])
                blob[0]^=1
                bad[name]=bytes(blob)
                with self.assertRaisesRegex(ValueError, name):
                    validate_capture_checksums(self.manifest,bad)

    def test_swapping_same_size_files_is_rejected(self):
        bad=sample_files()
        # Different files can have exactly the same length in real captures.
        bad['cps-a-be.bin']=bytes([65])*64
        bad['cps-b-be.bin']=bytes([66])*64
        manifest={'file_crc32':capture_checksums(bad)}
        bad['cps-a-be.bin'],bad['cps-b-be.bin']=(
            bad['cps-b-be.bin'],bad['cps-a-be.bin'])
        with self.assertRaisesRegex(ValueError, 'CRC32 mismatch'):
            validate_capture_checksums(manifest,bad)

    def test_missing_extra_or_nonobject_manifest_digests_rejected(self):
        good=self.manifest['file_crc32']
        for bad in (None, [], {}, dict(list(good.items())[:-1]),
                    dict(good, extra='abcdef01')):
            with self.subTest(digests=bad):
                with self.assertRaisesRegex(ValueError, 'five file_crc32'):
                    validate_capture_checksums({'file_crc32':bad},self.files)
        with self.assertRaisesRegex(ValueError, 'manifest'):
            validate_capture_checksums(None,self.files)

    def test_strict_eight_lowercase_hex_crc_format(self):
        name='gfxram-be.bin'
        for value in ('ABCDEF01', '0x12345678', '1234567', '123456789',
                      'zzzzzzzz', 12345678, None, True, '0000000\n'):
            with self.subTest(value=value):
                manifest={'file_crc32':dict(self.manifest['file_crc32'])}
                manifest['file_crc32'][name]=value
                with self.assertRaisesRegex(ValueError, 'invalid file_crc32'):
                    validate_capture_checksums(manifest,self.files)

    def test_binary_payload_rejects_extra_missing_and_wrong_types(self):
        for files in ({}, dict(self.files, extra=b'hi'),
                      dict(self.files, **{'cps-a-be.bin':bytearray(b'123')})):
            with self.subTest(size=len(files)):
                with self.assertRaises(ValueError):
                    capture_checksums(files)

    def test_crc_results_match_python_zlib(self):
        data={name:bytes((i*17+offset) % 256 for i in range(1025))
              for offset,name in enumerate(CAPTURE_FILES)}
        expected={name:f'{zlib.crc32(blob) & 0xffffffff:08x}'
                  for name,blob in data.items()}
        self.assertEqual(capture_checksums(data),expected)


if __name__ == '__main__':
    unittest.main()
