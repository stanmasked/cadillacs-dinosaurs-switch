import struct
import unittest
from tools.cps1_capture import (convert_capture,words_from_binary,base_byte,
                                GFX_RAM_BYTES,CPS_REG_BYTES,BUFFERED_OBJ_BYTES)
from tools.cps1_raster import scroll2_x_for_line,pen_blocks_sprite

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.g=[0]*(GFX_RAM_BYTES//2)
        self.a=[0]*32
        self.b=[0]*32
        self.o=[0xff00 if i%4==3 else 0 for i in range(BUFFERED_OBJ_BYTES//2)]
        self.a[0x02//2]=0x9000
        self.a[0x04//2]=0x9040
        self.a[0x06//2]=0x9080
        self.a[0x08//2]=0x9100
        self.a[0x0a//2]=0x9140
        self.a[0x22//2]=0xe
        self.b[0x0a//2]=0x16
        self.b[0x04//2]=0x3f
    def test_binary_explicit_endianness(self):
        self.assertEqual(words_from_binary(b'\x12\x34\xab\xcd',4,'big'),[0x1234,0xabcd])
        self.assertEqual(words_from_binary(b'\x12\x34\xab\xcd',4,'little'),[0x3412,0xcdab])
    def test_binary_rejects_truncation(self):
        with self.assertRaises(ValueError): words_from_binary(b'\x12',4,'big')
        with self.assertRaises(ValueError): words_from_binary(b'\x00\x00',2,'host')
    def test_base_alignment_wrap(self):
        self.assertEqual(base_byte(0x9040,0x4000),0x4000)
        self.assertEqual(base_byte(0x9080,0x4000),0x8000)
        self.assertEqual(base_byte(0xffff,0x400),0x3fc00)
    def test_layer_mapping_and_enables(self):
        self.g[0]=23
        self.g[0x4000//2]=47
        self.g[0x8000//2]=89
        snapshot=convert_capture(self.g,self.a,self.b,self.o)
        self.assertEqual(snapshot['scroll1']['words'][0],23)
        self.assertEqual(snapshot['scroll2']['words'][0],47)
        self.assertEqual(snapshot['scroll3']['words'][0],89)
        self.assertTrue(all(snapshot[n]['enabled'] for n in ('scroll1','scroll2','scroll3')))
        self.assertEqual(snapshot['palette_fidelity'],'approximate_current_source_not_latched')
        self.assertEqual(len(snapshot['palette_source']['words']),3072)
    def test_enable_video_control(self):
        self.a[0x22//2]=0
        s=convert_capture(self.g,self.a,self.b,self.o)
        self.assertTrue(s['scroll1']['enabled'])
        self.assertFalse(s['scroll2']['enabled'])
        self.assertFalse(s['scroll3']['enabled'])
    def test_rowscroll_ram_and_qs2_priority_ports(self):
        self.a[0x22//2]=0xf
        self.a[0x20//2]=3
        self.b[0x0c//2]=0x10
        self.b[0x0e//2]=0x20
        self.b[0x00//2]=0x40
        self.b[0x02//2]=0x80
        self.g[0x10000//2+5]=0x1234
        s=convert_capture(self.g,self.a,self.b,self.o)
        self.assertEqual(s['priority_masks'],[0x10,0x20,0x40,0x80])
        self.assertEqual(s['rowscroll'][5],0x1234)
        self.assertEqual(s['rowscroll_offset'],3)
    def test_effective_palette_provenance(self):
        pal=[[1,2,3]]*3072
        s=convert_capture(self.g,self.a,self.b,self.o,effective_palette=pal)
        self.assertEqual(s['palette_rgb'][0],[1,2,3])
        self.assertNotIn('palette_source',s)
        self.assertEqual(s['palette_fidelity'],'captured_effective_palette')
    def test_rejects_missing_buffered_obj(self):
        with self.assertRaises(ValueError): convert_capture(self.g,self.a,self.b,[0]*12)
    def test_palette_overflow_guard(self):
        self.a[0x0a//2]=0x93fc
        with self.assertRaises(ValueError): convert_capture(self.g,self.a,self.b,self.o)

class RasterTests(unittest.TestCase):
    def test_rowscroll_scanline_and_wrap(self):
        rs=[0]*1024
        rs[100]=99
        self.assertEqual(scroll2_x_for_line(10,95,rs,5),109)
        rs[0]=47
        self.assertEqual(scroll2_x_for_line(10,0,rs,1024),57)
    def test_rowscroll_rejects_short(self):
        with self.assertRaises(ValueError): scroll2_x_for_line(0,1,[0]*12,0)
    def test_priority_pens(self):
        self.assertTrue(pen_blocks_sprite(5,2,[0,0,0x20,0]))
        self.assertFalse(pen_blocks_sprite(4,2,[0,0,0x20,0]))
        self.assertFalse(pen_blocks_sprite(15,2,[0,0,0xffff,0]))
    def test_invalid_priority_group(self):
        with self.assertRaises(ValueError):pen_blocks_sprite(1,4,[0]*4)

if __name__=='__main__':unittest.main()
