"""ROM-free tests of the portable C graphics decoder against Python."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

from tools.cps1_gfx import LANES, ROM_SIZE
from tools.cps1_private_native_tile_parity import (
    TILE_COUNT,compare_private_rom_native_tiles,sampled_codes,main,
)


@unittest.skipUnless(shutil.which('gcc'),'host gcc unavailable')
class PrivateTileParitySyntheticTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.zip=self.root/'SYNTHETIC_NOT_COMMERCIAL_ROM.zip'

    def make_zip(self,missing=(),short=()):
        with zipfile.ZipFile(self.zip,'w',zipfile.ZIP_DEFLATED) as z:
            for i,(name,_) in enumerate(LANES):
                if name in missing:
                    continue
                length=ROM_SIZE-1 if name in short else ROM_SIZE
                pattern=bytes(((p*7+i*23)^(p//101))&255 for p in range(512))
                z.writestr(name,(pattern*((length+511)//512))[:length])

    def invoke(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            rc=main([str(self.zip)])
        return rc,json.loads(output.getvalue()),output.getvalue()

    def test_fixed_sample_spans_all_gfx_code_banks(self):
        codes=sampled_codes()
        self.assertEqual(codes[0],0)
        self.assertEqual(codes[-1],TILE_COUNT-1)
        self.assertIn(TILE_COUNT//2,codes)
        self.assertGreater(len(codes),1000)
        self.assertEqual(len(codes),len(set(codes)))

    def test_native_c_agrees_with_python_on_synthetic_eight_lane_zip(self):
        self.make_zip()
        rc,obj,raw=self.invoke()
        self.assertEqual(rc,0)
        self.assertEqual(obj['status'],'PRIVATE_DINO_NATIVE_TILE_PARITY_PASSED')
        self.assertEqual(obj['assembled_gfx_bytes'],4194304)
        self.assertEqual(obj['mismatching_tiles'],0)
        self.assertEqual(obj['compared_pixels'],obj['sampled_tiles']*256)
        self.assertTrue(obj['native_bounds_rejected'])
        self.assertFalse(obj['switch_pixel_parity_verified'])
        self.assertNotIn(str(self.root),raw)

    def test_corrupt_python_decoder_forces_mismatch(self):
        self.make_zip()
        from tools import cps1_private_native_tile_parity as target
        reference=target.python_reference_tile
        def tampered(region,code):
            pixels=bytearray(reference(region,code))
            pixels[0]^=1
            return bytes(pixels)
        with patch.object(target,'python_reference_tile',side_effect=tampered):
            out=compare_private_rom_native_tiles(self.zip)
        self.assertEqual(out['status'],'PRIVATE_DINO_NATIVE_TILE_PARITY_FAILED')
        self.assertEqual(out['sampled_tiles'],out['mismatching_tiles'])

    def test_missing_lane_does_not_report_source_path(self):
        self.make_zip(missing={LANES[3][0]})
        rc,out,raw=self.invoke()
        self.assertEqual(rc,2)
        self.assertEqual(out['status'],'PRIVATE_NATIVE_TILE_INPUT_REFUSED')
        self.assertNotIn(str(self.zip),raw)
        self.assertNotIn(LANES[3][0],raw)

    def test_wrong_rom_entry_length_refused(self):
        self.make_zip(short={LANES[-1][0]})
        rc,out,raw=self.invoke()
        self.assertEqual(rc,2)
        self.assertEqual(out['status'],'PRIVATE_NATIVE_TILE_INPUT_REFUSED')
        self.assertNotIn(str(self.root),raw)

    def test_duplicate_zip_member_refused(self):
        self.make_zip()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(self.zip,'a') as z:
                z.writestr(LANES[0][0],b'fake')
        rc,out,raw=self.invoke()
        self.assertEqual(rc,2)
        self.assertEqual(out['status'],'PRIVATE_NATIVE_TILE_INPUT_REFUSED')

    def test_missing_archive_hides_private_filename(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            rc=main([str(self.root/'PRIVATE_ORIGINAL_SECRET.zip')])
        self.assertEqual(rc,2)
        self.assertNotIn('PRIVATE_ORIGINAL_SECRET',output.getvalue())

    def test_no_original_graphics_written_to_directory(self):
        self.make_zip()
        previous=set(self.root.iterdir())
        out=compare_private_rom_native_tiles(self.zip)
        self.assertEqual(out['status'],'PRIVATE_DINO_NATIVE_TILE_PARITY_PASSED')
        self.assertEqual(set(self.root.iterdir()),previous)
        self.assertFalse(out['original_rom_bytes_written_to_disk'])

    def test_compiler_exception_redacted(self):
        self.make_zip()
        import subprocess
        output=io.StringIO()
        with patch('tools.cps1_private_native_tile_parity.compile_native_decoder',
                   side_effect=subprocess.CalledProcessError(
                       1,'private ROM secret build',stderr=b'GAME SECRET')),\
             contextlib.redirect_stdout(output):
            rc=main([str(self.zip)])
        self.assertEqual(rc,2)
        self.assertEqual(json.loads(output.getvalue())['status'],
                         'PRIVATE_NATIVE_DECODER_BUILD_REFUSED')
        self.assertNotIn('GAME SECRET',output.getvalue())


if __name__=='__main__':
    unittest.main()
