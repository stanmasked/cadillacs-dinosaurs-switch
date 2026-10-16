"""ROM-free regression tests of local instrumented MAME capture orchestration.

A tiny stand-in process emulates -version, -verifyroms and six streams.
This explicitly does NOT exercise the actual MAME arcade emulator.
"""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_local_capture_run import validate_dump, run_capture, main


FAKE_MAME = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args=sys.argv[1:]
if '-version' in args:
    print('TEST STAND-IN v0.1 - NOT A REAL MAME BINARY')
    sys.exit(0)
if '-verifyroms' in args:
    if os.environ.get('FAKE_MAME_BAD_ROMS')=='1':
        sys.exit(2)
    print('romset dino is good (synthetic)')
    sys.exit(0)
if os.environ.get('FAKE_MAME_FAIL_RUN')=='1':
    sys.exit(3)
root=Path(os.environ['CPS1_RENDER_DUMP_DIR'])
start=int(os.environ['CPS1_RENDER_DUMP_START'])
count=int(os.environ['CPS1_RENDER_DUMP_COUNT'])
sizes={
    'gfxram-be.bin':196608,'cps-a-be.bin':64,'cps-b-be.bin':64,
    'buffered-obj-be.bin':2048,'palette-rgb24.bin':9216,
    'reference-rgb24.bin':258048,
}
for frame in range(start,start+count):
    stem=f'frame-{frame:08d}'
    for suffix,size in sizes.items():
        data=bytearray(size)
        data[0]=frame&255
        if suffix=='buffered-obj-be.bin' and os.environ.get('FAKE_MAME_BAD_OBJ')=='1':
            data=data[:-1]
        (root/(stem+'.'+suffix)).write_bytes(data)
    meta={
        'game':'dino','frame':frame,
        'capture_hook':'screen_update_cps1_complete',
        'full_cliprect':True,'buffered_obj_same_render_pass':True,
        'reference_pixel_encoding':'rgb24_palette_resolved',
        'raw_word_endianness':'big',
        'palette_source':'MAME_effective_pen_color',
        'reference_width':384,'reference_height':224,
        'pixel_parity_verified':False,
        'gfxram_bytes':196608,'cps_a_bytes':64,'cps_b_bytes':64,
        'buffered_obj_bytes':2048,'palette_bytes':9216,
        'reference_rgb_bytes':258048,
    }
    if os.environ.get('FAKE_MAME_BAD_META')=='1':
        meta['buffered_obj_same_render_pass']=False
    (root/(stem+'.manifest.json')).write_text(json.dumps(meta))
'''

GAME_REPORT = {
    'core_complete':True, 'all_archival_plds_known':True,
}
DEVICE_REPORT={'valid':True,'status':'validated'}


class MameLocalCaptureRunnerTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.roms=self.root/'roms'
        self.roms.mkdir()
        (self.roms/'dino.zip').write_bytes(b'fake test bytes only')
        self.output=self.root/'capture'
        self.executable=self.root/'mame-stand-in'
        self.executable.write_text(FAKE_MAME)
        self.executable.chmod(self.executable.stat().st_mode|stat.S_IXUSR)
        self.mock1=patch('tools.mame_local_capture_run.audit_game',return_value=GAME_REPORT)
        self.mock2=patch('tools.mame_local_capture_run.check_device',return_value=DEVICE_REPORT)
        self.mock1.start();self.mock2.start()
        self.addCleanup(self.mock1.stop);self.addCleanup(self.mock2.stop)

    def run_fake(self,**options):
        return run_capture(
            mame=self.executable,rom_dir=self.roms,output_dir=self.output,
            start=900,count=2,seconds=25,wall_timeout=20,**options)

    def test_full_capture_has_only_hashes_and_exact_sizes(self):
        report=self.run_fake()
        self.assertTrue(report['capture_format_valid'])
        self.assertFalse(report['pixel_parity_verified'])
        self.assertFalse(report['gameplay_reconstructed'])
        self.assertEqual([e['frame'] for e in report['captured_frames']],[900,901])
        for frame in report['captured_frames']:
            self.assertEqual(len(frame['streams']),6)
            self.assertTrue(all(len(f['sha256'])==64 for f in frame['streams'].values()))
            self.assertEqual(frame['streams']['buffered-obj-be.bin']['bytes'],2048)
        self.assertNotIn('palette_rgb',json.dumps(report))

    def test_probe_only_does_not_run_game_or_write_captures(self):
        result=self.run_fake(probe_only=True)
        self.assertEqual(result['status'],'verified_roms_only_no_game_launched')
        self.assertEqual(result['captured_frames'],[])
        self.assertFalse(self.output.exists())

    def test_reject_missing_device_when_strict(self):
        with patch('tools.mame_local_capture_run.check_device',
                   return_value={'valid':False,'status':'not_supplied'}):
            with self.assertRaisesRegex(ValueError,'qsound_hle'):
                self.run_fake()
        self.assertFalse(self.output.exists())

    def test_allow_missing_device_for_emulator_verify(self):
        with patch('tools.mame_local_capture_run.check_device',
                   return_value={'valid':False,'status':'not_supplied'}):
            result=self.run_fake(require_device=False,probe_only=True)
        self.assertFalse(result['qsound_device_valid'])

    def test_invalid_core_rom_aborts_before_executable(self):
        with patch('tools.mame_local_capture_run.audit_game',
                   return_value={'core_complete':False,'all_archival_plds_known':False}):
            with self.assertRaisesRegex(ValueError,'CRC'):
                self.run_fake()
        self.assertFalse(self.output.exists())

    def test_detect_missing_mame_binary(self):
        with self.assertRaises(FileNotFoundError):
            run_capture(mame=self.root/'missing',rom_dir=self.roms,
                        output_dir=self.output,start=900,count=1,seconds=25)

    def test_reject_truncated_obj_even_if_fake_manifest_says_valid(self):
        with patch.dict(os.environ,{'FAKE_MAME_BAD_OBJ':'1'}):
            with self.assertRaisesRegex(ValueError,'buffered-obj-be.bin'):
                self.run_fake()
        self.assertTrue((self.output/'frame-00000900.manifest.json').exists())

    def test_reject_false_same_pass_claim(self):
        with patch.dict(os.environ,{'FAKE_MAME_BAD_META':'1'}):
            with self.assertRaisesRegex(ValueError,'buffered_obj_same_render_pass'):
                self.run_fake()

    def test_no_overwrite_capture_dir(self):
        self.run_fake()
        with self.assertRaises(FileExistsError):
            self.run_fake()

    def test_reject_fake_mame_romset_verify_failure(self):
        with patch.dict(os.environ,{'FAKE_MAME_BAD_ROMS':'1'}):
            with self.assertRaisesRegex(ValueError,'verifyroms'):
                self.run_fake()
        self.assertFalse(self.output.exists())

    def test_reject_invalid_ranges_before_execution(self):
        for start,count,seconds in ((-1,2,25),(900,121,25),
                                    (900,0,25),(900,2,0),(99999999,2,25)):
            with self.subTest(start=start,count=count,seconds=seconds):
                with self.assertRaises(ValueError):
                    run_capture(mame=self.executable,rom_dir=self.roms,
                        output_dir=self.output,start=start,count=count,seconds=seconds)

    def test_cli_report_and_no_overwrite(self):
        report=self.root/'run-report.json'
        args=['--mame',str(self.executable),'--rom-dir',str(self.roms),
              '--capture-dir',str(self.output),'--start','900','--count','2',
              '--seconds-to-run','25','--report',str(report)]
        self.assertEqual(main(args),0)
        data=json.loads(report.read_text())
        self.assertTrue(data['capture_format_valid'])
        self.assertEqual(main(args),2)


if __name__=='__main__':
    unittest.main()
