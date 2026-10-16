"""ROM-free manifest authenticity and path safety checks."""
import unittest

from tools.mame_capture_manifest import (
    validate_capture_manifest, validate_frame_stem,
)


STEM = 'frame-00000900'


def manifest():
    return {
        'game': 'dino', 'frame': 900, 'capture_hook': 'frame_done',
        'gfxram_bytes': 0x30000, 'cps_a_bytes': 64, 'cps_b_bytes': 64,
        'palette_bytes': 9216, 'reference_width': 384, 'reference_height': 224,
        'reference_rgb_bytes': 258048, 'raw_word_endianness': 'big',
        'palette_source': 'MAME_effective_pen_color',
        'obj_latch': 'NOT_CAPTURED', 'pixel_parity_eligible': False,
    }


class CaptureManifestValidation(unittest.TestCase):
    def test_accepts_real_lua_capture_schema(self):
        self.assertEqual(validate_capture_manifest(manifest(), STEM), 900)
        self.assertEqual(validate_frame_stem('frame-99999999'), 99999999)

    def test_rejects_manifest_frame_mismatched_to_filename(self):
        bad = manifest()
        bad['frame'] = 901
        with self.assertRaisesRegex(ValueError, 'frame number'):
            validate_capture_manifest(bad, STEM)

    def test_rejects_bool_and_text_frame_numbers(self):
        for number in (True, 900.0, '900', None):
            with self.subTest(number=number):
                bad = manifest()
                bad['frame'] = number
                with self.assertRaisesRegex(ValueError, 'frame number'):
                    validate_capture_manifest(bad, STEM)

    def test_rejects_incomplete_manifest_and_nonobject(self):
        for data in (None, [], 'not JSON object', {}, {'frame': 900}):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    validate_capture_manifest(data, STEM)

    def test_rejects_changed_provenance_or_incorrect_byte_lengths(self):
        src = manifest()
        for key, value in src.items():
            if key == 'frame':
                continue
            with self.subTest(key=key):
                bad = manifest()
                bad[key] = None
                with self.assertRaisesRegex(ValueError, 'manifest field'):
                    validate_capture_manifest(bad, STEM)

    def test_rejects_type_coercion_for_numeric_fields(self):
        for value in (True, 384.0, '384'):
            with self.subTest(value=value):
                bad = manifest()
                bad['reference_width'] = value
                with self.assertRaisesRegex(ValueError, 'reference_width'):
                    validate_capture_manifest(bad, STEM)

    def test_rejects_path_traversal_or_ambiguous_names(self):
        for stem in ('../frame-00000900', 'frame-00000900/../outside',
                     'frame-00000900\\outside', '/tmp/frame-00000900',
                     'frame-00000900.json', 'frame-900',
                     'FRAME-00000900', 'frame-000009000',
                     'frame-00000900\n', '', None, 900):
            with self.subTest(stem=stem):
                with self.assertRaises(ValueError):
                    validate_frame_stem(stem)

    def test_rejects_parity_eligibility_upgrade(self):
        bad = manifest()
        bad['pixel_parity_eligible'] = True
        with self.assertRaisesRegex(ValueError, 'pixel_parity_eligible'):
            validate_capture_manifest(bad, STEM)


if __name__ == '__main__':
    unittest.main()
