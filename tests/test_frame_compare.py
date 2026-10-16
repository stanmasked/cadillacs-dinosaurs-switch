import struct
import unittest
import zlib

from tools.frame_compare import load_rgba_png,compare_frames,_paeth
from tools.cps1_tiles import _png_rgba

def chunk(kind,payload):
    return (struct.pack('>I',len(payload))+kind+payload+
            struct.pack('>I',zlib.crc32(kind+payload)))

def encoded_png(rgba,width,height,filter_type):
    stride=width*4
    previous=bytes(stride)
    raw=bytearray()
    for row in range(height):
        source=rgba[row*stride:(row+1)*stride]
        encoded=bytearray(stride)
        for i,v in enumerate(source):
            a=source[i-4] if i>=4 else 0
            b=previous[i]
            c=previous[i-4] if i>=4 else 0
            pred=(0,a,b,(a+b)//2,_paeth(a,b,c))[filter_type]
            encoded[i]=(v-pred)&255
        raw.extend(bytes([filter_type])+encoded)
        previous=source
    return (b'\x89PNG\r\n\x1a\n' +
            chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0)) +
            chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

class FrameComparisonTests(unittest.TestCase):
    def setUp(self):
        self.rgba=bytes([0,10,200,255,255,32,0,255,99,33,14,1,12,34,56,78])
    def test_existing_png_encoder_roundtrip(self):
        png=_png_rgba(2,2,self.rgba,'synthetic fixture')
        self.assertEqual(load_rgba_png(png),(2,2,self.rgba))
    def test_five_standard_png_filters(self):
        for kind in range(5):
            with self.subTest(filter=kind):
                self.assertEqual(load_rgba_png(encoded_png(self.rgba,2,2,kind)),
                                 (2,2,self.rgba))
    def test_identical_frames(self):
        metrics,diff=compare_frames(self.rgba,self.rgba,2,2)
        self.assertTrue(metrics['identical'])
        self.assertEqual(metrics['different_pixels'],0)
        self.assertEqual(diff[:4],bytes((0,0,0,255)))
    def test_one_pixel_change(self):
        altered=bytearray(self.rgba)
        altered[7]=50
        metrics,diff=compare_frames(self.rgba,altered,2,2)
        self.assertEqual(metrics['different_pixels'],1)
        self.assertEqual(metrics['first_difference_xy'],[1,0])
        self.assertEqual(metrics['max_channel_error'],205)
        self.assertEqual(metrics['different_ratio'],0.25)
        self.assertEqual(diff[4:8],bytes((205,0,0,255)))
    def test_optional_alpha_ignore(self):
        altered=bytearray(self.rgba)
        altered[3]=0
        self.assertTrue(compare_frames(self.rgba,altered,2,2,ignore_alpha=True)[0]['identical'])
        self.assertFalse(compare_frames(self.rgba,altered,2,2)[0]['identical'])
    def test_bad_frame_length(self):
        with self.assertRaises(ValueError):
            compare_frames(b'bad',self.rgba,2,2)
    def test_corrupt_png_crc(self):
        png=bytearray(_png_rgba(2,2,self.rgba,'fixture'))
        png[20]^=1
        with self.assertRaises(ValueError): load_rgba_png(png)
    def test_truncated_png(self):
        png=_png_rgba(2,2,self.rgba,'fixture')
        with self.assertRaises(ValueError): load_rgba_png(png[:-7])
    def test_unsupported_color_mode(self):
        png=bytearray(encoded_png(self.rgba,2,2,0))
        png[25]=0  # grayscale instead of RGBA
        png[29:33]=struct.pack('>I',zlib.crc32(png[12:29]))
        with self.assertRaises(ValueError): load_rgba_png(png)

if __name__=='__main__':
    unittest.main()
