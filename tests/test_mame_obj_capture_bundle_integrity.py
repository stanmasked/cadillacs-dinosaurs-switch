"""ROM-free MAME five-component capture integrity and fail-closed CLI tests.

Every test creates complete synthetic binaries; no real game data required.
"""
import json
from pathlib import Path
import tempfile
import unittest

from test_mame_obj_cli_end_to_end import make_capture, invoke
from tools.mame_obj_sequence_alignment import CAPTURE_SIZES


class FullCaptureCrcTests(unittest.TestCase):
    def test_complete_real_shape_files_allow_diagnostic_only(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            make_capture(root)
            status, report = invoke(root)
            self.assertEqual(status, 0)
            self.assertEqual(report['diagnostic_verdict']['status'],
                             'CONSISTENT_BUT_UNVERIFIED')
            self.assertFalse(report['frame_sync_verified'])
            self.assertFalse(report['pixel_parity_eligible'])

    def test_each_large_capture_component_crc_mutation_is_rejected(self):
        for name in ('gfxram-be.bin', 'palette-rgb24.bin', 'reference-rgb24.bin'):
            with tempfile.TemporaryDirectory() as path:
                root = Path(path)
                make_capture(root)
                component = root / ('frame-00000904.' + name)
                data = bytearray(component.read_bytes())
                data[len(data) // 2] ^= 1
                component.write_bytes(data)
                with self.subTest(name=name):
                    status, result = invoke(root)
                    self.assertEqual(status, 2)
                    self.assertIsNone(result)
                    self.assertFalse((root / 'audit.json').exists())

    def test_missing_component_for_any_of_three_large_files_is_rejected(self):
        for name in ('gfxram-be.bin', 'palette-rgb24.bin', 'reference-rgb24.bin'):
            with tempfile.TemporaryDirectory() as path:
                root = Path(path)
                make_capture(root)
                (root / ('frame-00000908.' + name)).unlink()
                with self.subTest(name=name):
                    self.assertEqual(invoke(root)[0], 2)
                    self.assertFalse((root / 'audit.json').exists())

    def test_truncated_large_component_is_rejected(self):
        for name in ('gfxram-be.bin', 'palette-rgb24.bin', 'reference-rgb24.bin'):
            with tempfile.TemporaryDirectory() as path:
                root = Path(path)
                make_capture(root)
                file = root / ('frame-00000902.' + name)
                file.write_bytes(file.read_bytes()[:-1])
                with self.subTest(name=name):
                    self.assertEqual(invoke(root)[0], 2)

    def test_oversize_component_is_rejected_without_output(self):
        for name in ('gfxram-be.bin', 'palette-rgb24.bin', 'reference-rgb24.bin'):
            with tempfile.TemporaryDirectory() as path:
                root = Path(path)
                make_capture(root)
                file = root / ('frame-00000900.' + name)
                with file.open('ab') as output:
                    output.write(b'\xff')
                with self.subTest(name=name):
                    self.assertEqual(invoke(root)[0], 2)
                    self.assertFalse((root / 'audit.json').exists())

    def test_swap_same_length_gfx_ram_between_frames_is_rejected(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            make_capture(root)
            first = root / 'frame-00000900.gfxram-be.bin'
            second = root / 'frame-00000902.gfxram-be.bin'
            x, y = first.read_bytes(), second.read_bytes()
            self.assertEqual(len(x), CAPTURE_SIZES['gfxram-be.bin'])
            self.assertEqual(len(x), len(y))
            self.assertNotEqual(x, y)
            first.write_bytes(y)
            second.write_bytes(x)
            self.assertEqual(invoke(root)[0], 2)
            self.assertFalse((root / 'audit.json').exists())

    def test_claimed_checksum_is_required_to_match_actual_bytes(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            make_capture(root)
            path = root / 'frame-00000900.manifest.json'
            metadata = json.loads(path.read_text())
            metadata['file_crc32']['reference-rgb24.bin'] = '00000000'
            path.write_text(json.dumps(metadata))
            self.assertEqual(invoke(root)[0], 2)
            self.assertFalse((root / 'audit.json').exists())

    def test_no_capture_payload_dumps_in_valid_report(self):
        with tempfile.TemporaryDirectory() as path:
            root = Path(path)
            make_capture(root)
            status, result = invoke(root)
            self.assertEqual(status, 0)
            report = (root / 'audit.json').read_text()
            for key in ('gfxram_bytes_data', 'palette_rgb24', 'reference_rgb24',
                        'cps_a_raw', 'cps_b_raw', 'buffered_obj_bytes'):
                with self.subTest(key=key):
                    self.assertNotIn(key, report)
            self.assertFalse(result['diagnostic_verdict']['pixel_parity_eligible'])


if __name__ == '__main__':
    unittest.main()
