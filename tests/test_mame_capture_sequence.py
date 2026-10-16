"""ROM-free integration: verified MAME render captures to native CPS1SEQ1."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.mame_capture_sequence import (build_timeline,export_timeline,
                                         main,SUFFIXES)
from tools.mame_render_import import SIZES


def make_capture(root,n):
    stem=f'frame-{n:08d}'
    manifest={
        'game':'dino','frame':n,'capture_hook':'screen_update_cps1_complete',
        'full_cliprect':True,'buffered_obj_same_render_pass':True,
        'reference_pixel_encoding':'rgb24_palette_resolved',
        'raw_word_endianness':'big','palette_source':'MAME_effective_pen_color',
        'gfxram_bytes':196608,'cps_a_bytes':64,'cps_b_bytes':64,
        'buffered_obj_bytes':2048,'palette_bytes':9216,
        'reference_rgb_bytes':258048,'reference_width':384,'reference_height':224,
        'pixel_parity_verified':False,
    }
    (root/(stem+'.manifest.json')).write_text(json.dumps(manifest))
    for suffix,size in SIZES.items():
        buf=bytearray(size)
        if suffix=='gfxram-be.bin':
            buf[:2]=struct.pack('>H',n&65535)
        if suffix=='cps-a-be.bin':
            registers=[0]*32
            registers[1:4]=[0x40,0x80,0xc0]
            buf[:]=struct.pack('>32H',*registers)
        if suffix=='buffered-obj-be.bin':
            words=[0]*1024
            words[:8]=[64+n%8,16,256,1,0,0,0,0xff00]
            buf[:]=struct.pack('>1024H',*words)
        if suffix=='palette-rgb24.bin':
            buf[:3]=bytes((n&255,7,17))
        if suffix=='reference-rgb24.bin':
            buf[:3]=bytes((n&255,3,9))
        (root/(stem+'.'+suffix)).write_bytes(buf)


class MameCaptureToSwitchTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root=Path(self.folder.name)
        for n in (900,901,902,904):
            make_capture(self.root,n)

    def test_three_frames_roundtrip_and_crc(self):
        data,report=build_timeline(self.root,900,3)
        self.assertEqual(len(data),20+3*62510)
        self.assertEqual(data[:8],b'CPS1SEQ1')
        self.assertEqual(struct.unpack_from('<HH',data,8),(3,60))
        self.assertEqual(zlib.crc32(data[20:]),struct.unpack_from('<I',data,12)[0])
        for i in range(3):
            blob=data[20+i*62510:20+(i+1)*62510]
            self.assertEqual(blob[:8],b'CPS1SCN1')
            self.assertEqual(zlib.crc32(blob[16:]),struct.unpack_from('<I',blob,12)[0])
            self.assertEqual(report['frames'][i]['scene_blob_sha256'],hashlib.sha256(blob).hexdigest())
            self.assertEqual(report['frames'][i]['mame_frame'],900+i)
        self.assertFalse(report['pixel_parity_verified'])
        self.assertFalse(report['gameplay_reconstructed'])

    def test_explicit_stride(self):
        data,report=build_timeline(self.root,900,3,stride=2,fps=30)
        self.assertEqual([r['mame_frame'] for r in report['frames']],[900,902,904])
        self.assertEqual(struct.unpack_from('<HH',data,8),(3,30))

    def test_refuses_missing_capture_instead_of_interpolation(self):
        with self.assertRaises(FileNotFoundError):
            build_timeline(self.root,901,3)

    def test_reject_partial_capture(self):
        p=self.root/'frame-00000902.manifest.json'
        meta=json.loads(p.read_text());meta['full_cliprect']=False
        p.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError,'full_cliprect'):
            build_timeline(self.root,900,3)

    def test_reject_missing_buffered_sprites(self):
        (self.root/'frame-00000901.buffered-obj-be.bin').write_bytes(bytes(2047))
        with self.assertRaisesRegex(ValueError,'2048'):
            build_timeline(self.root,900,2)

    def test_reject_pre_verified_parity_claim(self):
        p=self.root/'frame-00000901.manifest.json'
        meta=json.loads(p.read_text());meta['pixel_parity_verified']=True
        p.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError,'pixel_parity_verified'):
            build_timeline(self.root,900,2)

    def test_source_hashes_not_game_payloads(self):
        _,report=build_timeline(self.root,900,1)
        entry=report['frames'][0]
        self.assertEqual(set(entry['captured_stream_sha256']),set(SUFFIXES))
        self.assertTrue(all(len(v)==64 for v in entry['captured_stream_sha256'].values()))
        self.assertNotIn('palette_rgb',json.dumps(report))

    def test_strict_range_rejections(self):
        for first,count,stride,fps in [(-1,1,1,60),(0,0,1,60),
                                        (0,121,1,60),(900,2,0,60),
                                        (900,1,1,61),(True,1,1,60),
                                        (900,True,1,60),(99999999,2,2,60)]:
            with self.subTest(first=first,count=count,stride=stride,fps=fps):
                with self.assertRaises(ValueError):
                    build_timeline(self.root,first,count,stride=stride,fps=fps)

    def test_export_sha256_and_refuse_overwrite(self):
        out=self.root/'out'
        report=export_timeline(self.root,900,2,out,fps=12)
        data=(out/'sequence.bin').read_bytes()
        self.assertEqual(len(data),20+2*62510)
        self.assertEqual(report['timeline_sha256'],hashlib.sha256(data).hexdigest())
        self.assertEqual(json.loads((out/'sequence-provenance.json').read_text())['frame_count'],2)
        with self.assertRaises(FileExistsError):
            export_timeline(self.root,900,1,out)
        self.assertEqual((out/'sequence.bin').read_bytes(),data)

    def test_no_output_on_invalid_source(self):
        (self.root/'frame-00000901.manifest.json').unlink()
        out=self.root/'uncommitted'
        with self.assertRaises(FileNotFoundError):
            export_timeline(self.root,900,2,out)
        self.assertFalse((out/'sequence.bin').exists())
        self.assertFalse((out/'sequence-provenance.json').exists())

    def test_cli_creates_then_refuses_overwrite(self):
        out=self.root/'cli'
        argv=[str(self.root),'--first-frame','900','--count','2',
              '--fps','12','--out-dir',str(out)]
        self.assertEqual(main(argv),0)
        self.assertEqual(main(argv),2)


if __name__=='__main__':
    unittest.main()
