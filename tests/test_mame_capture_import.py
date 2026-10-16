"""Synthetic verification only. Does not start MAME or bundle any game ROM."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

from tools.mame_capture_import import (GFX_BYTES,REF_W,REF_H,
    decode_reference_rgb24,import_capture,unpack_be_words,main)
from tools.cps1_scene_export import pack_scene
from tools.mame_capture_crc import CAPTURE_FILES, capture_checksums

STEM='frame-00000900'

class MameReferenceCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        metadata={'game':'dino','frame':900,'capture_hook':'frame_done',
            'gfxram_bytes':GFX_BYTES,'cps_a_bytes':64,'cps_b_bytes':64,
            'palette_bytes':9216,'reference_width':REF_W,
            'reference_height':REF_H,'reference_rgb_bytes':REF_W*REF_H*3,
            'obj_latch':'NOT_CAPTURED','pixel_parity_eligible':False,
            'palette_source':'MAME_effective_pen_color','raw_word_endianness':'big'}
        (self.directory/(STEM+'.manifest.json')).write_text(json.dumps(metadata))
        ram=[0]*(GFX_BYTES//2)
        ram[0x4000//2]=0x1234
        (self.directory/(STEM+'.gfxram-be.bin')).write_bytes(
            struct.pack('>'+str(len(ram))+'H',*ram))
        a=[0]*32
        a[0x04//2]=0x40
        a[0x06//2]=0x80
        (self.directory/(STEM+'.cps-a-be.bin')).write_bytes(struct.pack('>32H',*a))
        b=[0]*32
        b[0x0a//2]=0x16
        (self.directory/(STEM+'.cps-b-be.bin')).write_bytes(struct.pack('>32H',*b))
        (self.directory/(STEM+'.palette-rgb24.bin')).write_bytes(
            bytes(i%256 for i in range(3072*3)))
        (self.directory/(STEM+'.reference-rgb24.bin')).write_bytes(
            bytes((9,20,40))*(REF_W*REF_H))
        self._refresh_crc()

    def _refresh_crc(self):
        path=self.directory/(STEM+'.manifest.json')
        manifest=json.loads(path.read_text())
        blobs={name:(self.directory/(STEM+'.'+name)).read_bytes()
               for name in CAPTURE_FILES}
        manifest['file_crc32']=capture_checksums(blobs)
        path.write_text(json.dumps(manifest))

    def test_preserves_mapped_graphics_registers_and_palette(self):
        scene,png=import_capture(self.directory,STEM)
        self.assertEqual(scene['scroll2']['words'][0],0x1234)
        self.assertEqual(scene['palette_rgb'][0],[0,1,2])
        self.assertEqual(scene['buffered_obj_source'],'UNAVAILABLE_MAME_LUA')
        self.assertFalse(scene['pixel_parity_eligible'])
        self.assertEqual(scene['gfxram_mapped_bytes'],0x30000)
        self.assertEqual(len(scene['capture_file_crc32']),5)
        self.assertEqual(scene['buffered_obj_words'][3],0xff00)
        self.assertEqual(struct.unpack_from('>II',png,16),(REF_W,REF_H))

    def test_outputs_local_png_and_partial_metadata(self):
        out=self.directory/'result'
        self.assertEqual(main([str(self.directory),STEM,'--out-dir',str(out)]),0)
        self.assertTrue((out/(STEM+'.mame-reference.png')).is_file())
        doc=json.loads((out/(STEM+'.partial-snapshot.json')).read_text())
        self.assertFalse(doc['pixel_parity_eligible'])
        self.assertEqual(main([str(self.directory),STEM,'--out-dir',str(out)]),2)

    def test_reject_manifest_frame_number_mismatch(self):
        path=self.directory/(STEM+'.manifest.json')
        data=json.loads(path.read_text())
        data['frame']=901
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'frame number'):
            import_capture(self.directory,STEM)

    def test_reject_invalid_capture_hook_or_manifest_sizes(self):
        path=self.directory/(STEM+'.manifest.json')
        original=json.loads(path.read_text())
        for key,value in (('capture_hook','video_update'),
                          ('gfxram_bytes',0x40000),
                          ('reference_width',512),
                          ('reference_rgb_bytes',0)):
            with self.subTest(key=key):
                bad=dict(original)
                bad[key]=value
                path.write_text(json.dumps(bad))
                with self.assertRaisesRegex(ValueError,'manifest field'):
                    import_capture(self.directory,STEM)
        path.write_text(json.dumps(original))

    def test_frame_stem_path_traversal_is_rejected_before_io(self):
        for candidate in ('../frame-00000900','frame-00000900/../../other',
                          '/tmp/frame-00000900','frame-900'):
            with self.subTest(stem=candidate):
                with self.assertRaisesRegex(ValueError,'frame name'):
                    import_capture(self.directory,candidate)

    def test_reject_authenticity_claim(self):
        path=self.directory/(STEM+'.manifest.json')
        data=json.loads(path.read_text())
        data['pixel_parity_eligible']=True
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):import_capture(self.directory,STEM)

    def test_reject_same_size_reference_pixel_mutation(self):
        path=self.directory/(STEM+'.reference-rgb24.bin')
        data=bytearray(path.read_bytes())
        data[987]^=1
        path.write_bytes(data)
        with self.assertRaisesRegex(ValueError,'reference-rgb24.bin: CRC32 mismatch'):
            import_capture(self.directory,STEM)

    def test_reject_swap_of_cps_a_and_cps_b_equal_size_files(self):
        a=self.directory/(STEM+'.cps-a-be.bin')
        b=self.directory/(STEM+'.cps-b-be.bin')
        before_a,before_b=a.read_bytes(),b.read_bytes()
        self.assertEqual(len(before_a),len(before_b))
        a.write_bytes(before_b)
        b.write_bytes(before_a)
        with self.assertRaisesRegex(ValueError,'CRC32 mismatch'):
            import_capture(self.directory,STEM)

    def test_missing_crc32_manifest_is_rejected_before_import(self):
        path=self.directory/(STEM+'.manifest.json')
        metadata=json.loads(path.read_text())
        del metadata['file_crc32']
        path.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError,'five file_crc32'):
            import_capture(self.directory,STEM)

    def test_reject_wrong_gfx_size(self):
        (self.directory/(STEM+'.gfxram-be.bin')).write_bytes(bytes(GFX_BYTES-2))
        with self.assertRaises(ValueError):import_capture(self.directory,STEM)

    def test_reject_wrong_palette_size(self):
        (self.directory/(STEM+'.palette-rgb24.bin')).write_bytes(bytes(9215))
        with self.assertRaises(ValueError):import_capture(self.directory,STEM)

    def test_reject_truncated_reference_frame(self):
        (self.directory/(STEM+'.reference-rgb24.bin')).write_bytes(bytes(4))
        with self.assertRaises(ValueError):import_capture(self.directory,STEM)

    def test_endianness(self):
        self.assertEqual(unpack_be_words(b'\x12\x34\xab\xcd',4,'fixture'),
                         [0x1234,0xabcd])

    def test_reference_png_input_size(self):
        with self.assertRaises(ValueError):decode_reference_rgb24(b'bad')

    def test_reject_out_of_map_scroll_base(self):
        a=[0]*32
        a[0x02//2]=0x2c0
        a[0x04//2]=0x300
        (self.directory/(STEM+'.cps-a-be.bin')).write_bytes(struct.pack('>32H',*a))
        self._refresh_crc()
        with self.assertRaises(ValueError):import_capture(self.directory,STEM)

    def test_reject_out_of_map_rowscroll(self):
        a=[0]*32
        a[0x22//2]=1
        a[0x08//2]=0x300
        (self.directory/(STEM+'.cps-a-be.bin')).write_bytes(struct.pack('>32H',*a))
        self._refresh_crc()
        with self.assertRaises(ValueError):import_capture(self.directory,STEM)

    def test_native_scene_export_blocks_unlatched_sprite_state(self):
        scene,_=import_capture(self.directory,STEM)
        with self.assertRaisesRegex(ValueError,'buffered OBJ'):
            pack_scene(scene)

if __name__=='__main__':
    unittest.main()
