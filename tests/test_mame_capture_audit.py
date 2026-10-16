"""Synthetic validation of local CPS-1 MAME capture audit; no ROMs."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.mame_capture_audit import FILES, read_frame, audit_capture, main


def write_frame(root, n, rgb=None, palette=None):
    stem=f'frame-{n:08d}'
    manifest={
        'game':'dino','frame':n,
        'gfxram_bytes':0x30000,'cps_a_bytes':64,'cps_b_bytes':64,
        'palette_bytes':9216,'reference_width':384,'reference_height':224,
        'reference_rgb_bytes':258048,'raw_word_endianness':'big',
        'reference_pixel_encoding':'rgb32_resolved',
        'reference_source_format':'indexed_bitmap',
        'palette_source':'MAME_effective_pen_color',
        'obj_latch':'NOT_CAPTURED','pixel_parity_eligible':False,
    }
    (root / f'{stem}.manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    for suffix,size in FILES.items():
        contents=(rgb if suffix=='reference-rgb24.bin' and rgb is not None else
                  palette if suffix=='palette-rgb24.bin' and palette is not None else
                  bytes(size))
        (root / f'{stem}.{suffix}').write_bytes(contents)
    return stem


class CaptureAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.a=write_frame(self.root,900)

    def test_checksum_and_provenance(self):
        item,_=read_frame(self.root,self.a)
        self.assertEqual(item['reference_unique_rgb_colors'],1)
        self.assertEqual(item['gfxram-be.bin']['bytes'],196608)
        self.assertEqual(len(item['gfxram-be.bin']['sha256']),64)
        self.assertFalse(item['pixel_parity_eligible'])

    def test_temporal_pixel_and_palette_differences(self):
        rgb=bytearray(258048)
        rgb[:3]=b'\x1e\x28\x32'
        rgb[15:18]=b'\x01\x02\x03'
        pal=bytearray(9216)
        pal[3:6]=b'\x09\x09\x09'
        b=write_frame(self.root,904,rgb,pal)
        report=audit_capture(self.root,[self.a,b])
        delta=report['frames'][1]['change_from_previous']
        self.assertEqual(delta['rgb_pixels_changed'],2)
        self.assertEqual(delta['palette_entries_changed'],1)
        self.assertEqual(delta['frame_gap'],4)
        self.assertFalse(report['pixel_parity_eligible'])

    def test_reject_truncated_capture(self):
        (self.root / (self.a+'.gfxram-be.bin')).write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError,'expected 196608'):
            read_frame(self.root,self.a)

    def test_reject_false_parity_claim(self):
        p=self.root/(self.a+'.manifest.json')
        manifest=json.loads(p.read_text())
        manifest['pixel_parity_eligible']=True
        p.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'pixel_parity_eligible'):
            read_frame(self.root,self.a)

    def test_reject_indexed_encoded_pixels(self):
        p=self.root/(self.a+'.manifest.json')
        manifest=json.loads(p.read_text())
        manifest['reference_pixel_encoding']='indexed'
        p.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError,'reference_pixel_encoding'):
            read_frame(self.root,self.a)

    def test_reject_unsafe_frame_stems(self):
        for stem in ('../secret','frame-1'):
            with self.subTest(stem=stem),self.assertRaises(ValueError):
                read_frame(self.root,stem)

    def test_reject_duplicate_stems(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            audit_capture(self.root,[self.a,self.a])

    def test_reject_empty_capture(self):
        with self.assertRaises(ValueError): audit_capture(self.root,[])

    def test_cli_json_and_refuse_overwrite(self):
        target=self.root/'audit.json'
        self.assertEqual(main([str(self.root),'--output',str(target)]),0)
        self.assertEqual(json.loads(target.read_text())['frame_count'],1)
        self.assertEqual(main([str(self.root),'--output',str(target)]),2)


if __name__=='__main__':
    unittest.main()
