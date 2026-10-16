"""ROM-free buffered OBJ probe import and parity-safety regressions."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tools.mame_obj_probe_import import (
    OBJ_BYTES, PROBE_SUFFIX, attach_probe, decode_probe, main,
)
from tools.cps1_scene_export import pack_scene


STEM = 'frame-00000900'


def sample():
    return {'reference_frame': STEM, 'pixel_parity_eligible': False,
            'buffered_obj_source': 'UNAVAILABLE_MAME_LUA',
            'buffered_obj_words': [0, 0, 0, 0xff00]}


def buffer_words():
    words = [0] * 1024
    words[:8] = [0x120, 0x034, 0x5123, 0x0008,
                 0x120, 0x034, 0x0100, 0xff00]
    return words


def big_endian_blob(words):
    return struct.pack('>1024H', *words)


class MameObjProbeImportTests(unittest.TestCase):
    def test_exact_2048_byte_buffer_and_endian_preserved(self):
        words = buffer_words()
        output, marker = decode_probe(big_endian_blob(words))
        self.assertEqual(len(output), 1024)
        self.assertEqual(output[:8], words[:8])
        self.assertEqual(marker, 1)
        self.assertEqual(len(big_endian_blob(words)), OBJ_BYTES)

    def test_no_terminator_is_valid_full_buffer(self):
        words = [0x1234] * 1024
        output, marker = decode_probe(big_endian_blob(words))
        self.assertEqual(output[0], 0x1234)
        self.assertIsNone(marker)

    def test_empty_marker_in_first_obj_slot(self):
        words = [0] * 1024
        words[3] = 0xff00
        _, marker = decode_probe(big_endian_blob(words))
        self.assertEqual(marker, 0)

    def test_wrong_length_and_nonbytes_data_rejected(self):
        for blob in (b'', bytes(OBJ_BYTES-1), bytes(OBJ_BYTES+1),
                     bytearray(OBJ_BYTES), None):
            with self.subTest(blob_type=type(blob).__name__, length=len(blob) if blob is not None else None):
                with self.assertRaisesRegex(ValueError, 'exactly 2048'):
                    decode_probe(blob)

    def test_attach_preserves_source_and_does_not_mark_parity_eligible(self):
        original = sample()
        old = dict(original)
        new = attach_probe(original, STEM+PROBE_SUFFIX, big_endian_blob(buffer_words()))
        self.assertEqual(original, old)
        self.assertIsNot(original, new)
        self.assertEqual(new['buffered_obj_words'][:8], buffer_words()[:8])
        self.assertEqual(new['obj_probe_first_end_marker_slot'], 1)
        self.assertEqual(new['obj_probe_frame'], STEM)
        self.assertEqual(new['obj_probe_sha256'],
                         hashlib.sha256(big_endian_blob(buffer_words())).hexdigest())
        self.assertEqual(new['obj_probe_frame_alignment'], 'NOT_INDEPENDENTLY_VERIFIED')
        self.assertFalse(new['pixel_parity_eligible'])
        self.assertIn('UNSYNCED', new['buffered_obj_source'])

    def test_mismatched_name_and_path_traversal_rejected(self):
        data = big_endian_blob(buffer_words())
        for name in ('frame-00000901'+PROBE_SUFFIX, '../'+STEM+PROBE_SUFFIX,
                     STEM+'.gfxram-be.bin', '', None):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, 'filename'):
                    attach_probe(sample(), name, data)

    def test_reject_eligibility_upgrade_or_wrong_provenance(self):
        data = big_endian_blob(buffer_words())
        for key, value in (('pixel_parity_eligible', True),
                           ('pixel_parity_eligible', None),
                           ('buffered_obj_source', 'UNVERIFIED')):
            bad = sample()
            bad[key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaisesRegex(ValueError, 'partial MAME'):
                    attach_probe(bad, STEM+PROBE_SUFFIX, data)

    def test_bogus_or_missing_reference_frame_rejected(self):
        data = big_endian_blob(buffer_words())
        for frame in ('../'+STEM, 'frame-900', '', 900, None):
            bad = sample()
            bad['reference_frame'] = frame
            with self.subTest(frame=frame):
                with self.assertRaisesRegex(ValueError, 'reference_frame'):
                    attach_probe(bad, STEM+PROBE_SUFFIX, data)

    def test_still_rejected_by_native_scene_exporter(self):
        snap = attach_probe(sample(), STEM+PROBE_SUFFIX,
                            big_endian_blob(buffer_words()))
        with self.assertRaisesRegex(ValueError, 'buffered OBJ'):
            pack_scene(snap)

    def test_cli_writes_only_private_new_file_and_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            input_json = d / (STEM + '.partial-snapshot.json')
            input_blob = d / (STEM + PROBE_SUFFIX)
            output = d / (STEM + '.obj-diagnostic.json')
            input_json.write_text(json.dumps(sample()))
            original_blob = big_endian_blob(buffer_words())
            input_blob.write_bytes(original_blob)
            args = [str(input_json), str(input_blob), '--out', str(output)]
            self.assertEqual(main(args), 0)
            content = json.loads(output.read_text())
            self.assertFalse(content['pixel_parity_eligible'])
            self.assertEqual(content['buffered_obj_words'][:8], buffer_words()[:8])
            self.assertEqual(main(args), 2)
            self.assertEqual(main([str(input_json), str(input_blob),
                                   '--out', str(input_json)]), 2)
            self.assertEqual(input_blob.read_bytes(), original_blob)


if __name__ == '__main__':
    unittest.main()
