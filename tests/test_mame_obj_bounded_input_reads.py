"""ROM-free boundaries for on-disk MAME manifests and small probe files."""
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from tools.mame_obj_sequence_alignment import read_frames, CAPTURE_SCHEMA, CAPTURE_SIZES


def make_frames(root):
    for index in range(4):
        frame = 900 + index * 2
        stem = f'frame-{frame:08d}'
        payload = {name: bytes([index+1])*size for name, size in CAPTURE_SIZES.items()}
        manifest = {
            'game': 'dino', 'frame': frame, 'capture_hook': 'frame_done',
            'pixel_parity_eligible': False, 'obj_latch': 'NOT_CAPTURED',
            'file_crc32': {name: f'{zlib.crc32(blob)&0xffffffff:08x}'
                           for name, blob in payload.items()},
            **CAPTURE_SCHEMA,
        }
        for name, blob in payload.items():
            (root / (stem + '.' + name)).write_bytes(blob)
        (root / (stem + '.render-regs-be.bin')).write_bytes(bytes(128))
        (root / (stem + '.buffered-obj-be.bin')).write_bytes(bytes(2048))
        (root / (stem + '.manifest.json')).write_text(json.dumps(manifest))


class BoundedInputsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_frames(self.root)

    def read(self):
        return read_frames(self.root, 900, 4, 2)

    def test_complete_real_shape_series_still_loads(self):
        render, lua = self.read()
        self.assertEqual(len(render), 4)
        self.assertEqual(len(lua), 4)
        self.assertTrue(all(len(item) == 128 for item in render + lua))

    def test_manifest_at_exact_16k_boundary_is_accepted(self):
        path = self.root / 'frame-00000900.manifest.json'
        original = path.read_bytes()
        self.assertLess(len(original), 16384)
        path.write_bytes(original + b' ' * (16384-len(original)))
        self.assertEqual(len(path.read_bytes()), 16384)
        self.assertEqual(len(self.read()[0]), 4)

    def test_manifest_above_16k_is_rejected_before_json_decode(self):
        path = self.root / 'frame-00000900.manifest.json'
        original = path.read_bytes()
        path.write_bytes(original + b' ' * (16385-len(original)))
        with self.assertRaisesRegex(ValueError, 'manifest exceeds 16384'):
            self.read()

    def test_oversize_registers_and_sidecars_are_rejected(self):
        names = ('cps-a-be.bin', 'cps-b-be.bin',
                 'render-regs-be.bin', 'buffered-obj-be.bin')
        for name in names:
            with self.subTest(name=name):
                path = self.root / ('frame-00000902.' + name)
                saved = path.read_bytes()
                path.write_bytes(saved + b'Z'*1024*1024)
                with self.assertRaisesRegex(ValueError, 'incomplete or oversized'):
                    self.read()
                path.write_bytes(saved)

    def test_truncated_registers_and_sidecars_are_rejected(self):
        names = ('cps-a-be.bin', 'cps-b-be.bin',
                 'render-regs-be.bin', 'buffered-obj-be.bin')
        for name in names:
            with self.subTest(name=name):
                path = self.root / ('frame-00000904.' + name)
                saved = path.read_bytes()
                path.write_bytes(saved[:-1])
                with self.assertRaisesRegex(ValueError, 'incomplete or oversized'):
                    self.read()
                path.write_bytes(saved)

    def test_manifest_invalid_utf8_is_refused(self):
        path = self.root / 'frame-00000900.manifest.json'
        path.write_bytes(b'{"game":"dino","bad":"\xff"}')
        with self.assertRaises(UnicodeDecodeError):
            self.read()


if __name__ == '__main__':
    unittest.main()
