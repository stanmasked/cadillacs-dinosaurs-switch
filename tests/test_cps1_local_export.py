import contextlib
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools.cps1_gfx import LANES, ROM_SIZE, assemble_gfx, main, metadata


class LocalSwitchExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / 'dino-fixture.zip'
        with zipfile.ZipFile(self.archive, 'w', zipfile.ZIP_DEFLATED) as z:
            for index, (name, lane) in enumerate(LANES):
                # Synthetic bytes, never commercial ROM contents.
                z.writestr(name, bytes([index + 1]) * ROM_SIZE)
        self.path = Path(self.temp.name) / 'gfx.bin'

    def test_export_exact_4mib_and_lane_order(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.archive), '--out-local', str(self.path)]), 0)
        region = self.path.read_bytes()
        self.assertEqual(len(region), 0x400000)
        self.assertEqual(region[:8], bytes((1,1,2,2,3,3,4,4)))
        self.assertEqual(region[0x200000:0x200008], bytes((5,5,6,6,7,7,8,8)))
        self.assertEqual(len(metadata(region)['sha256']), 64)

    def test_refuse_overwrite_existing_local_region(self):
        self.path.write_bytes(b'custom user data')
        with self.assertRaises(FileExistsError):
            with contextlib.redirect_stdout(io.StringIO()):
                main([str(self.archive), '--out-local', str(self.path)])
        self.assertEqual(self.path.read_bytes(), b'custom user data')

    def test_default_audit_writes_no_assets(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([str(self.archive)]), 0)
        self.assertFalse(self.path.exists())


if __name__ == '__main__':
    unittest.main()
