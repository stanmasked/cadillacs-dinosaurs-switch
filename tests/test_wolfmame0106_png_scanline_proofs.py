"""Stage273: synthetic PNG scanline proofs; never loads game frames or ROM."""
import struct
import unittest
import zlib
from tools import wolfmame0106_replay_preflight as pre

def chunk(name,data):
    return (struct.pack('>I',len(data))+name+data+
            struct.pack('>I',zlib.crc32(name+data)&0xffffffff))

def png(width=2,height=2,colour=2,raw=None,palette=None,extra=None):
    channels={0:1,2:3,3:1,4:2,6:4}[colour]
    if raw is None:
        raw=b''.join(b'\0'+b'\x31'*(width*channels) for _ in range(height))
    ihdr=struct.pack('>IIBBBBB',width,height,8,colour,0,0,0)
    parts=[chunk(b'IHDR',ihdr)]
    if palette is not None:
        parts.append(chunk(b'PLTE',palette))
    if extra:
        parts.extend(extra)
    parts.extend((chunk(b'IDAT',zlib.compress(raw)),chunk(b'IEND',b'')))
    return pre.PNG_SIG+b''.join(parts)

class PngScanlineProofTests(unittest.TestCase):
    def test_rgb_scanline_length_and_filters(self):
        result=pre.png_integrity(png(2,3,2))
        self.assertEqual(result['idat_decoded_bytes'],(1+2*3)*3)
        self.assertTrue(result['scanline_size_and_filters_verified'])

    def test_rgba_scanline_length(self):
        result=pre.png_integrity(png(3,4,6))
        self.assertEqual(result['idat_decoded_bytes'],(1+3*4)*4)

    def test_reject_wrong_scanline_size(self):
        with self.assertRaisesRegex(ValueError,'scanline'):
            pre.png_integrity(png(2,2,2,raw=b'\x00'*(14-1)))

    def test_reject_invalid_filter_byte(self):
        data=b'\x05'+b'\x31'*6+b'\x00'+b'\x31'*6
        with self.assertRaisesRegex(ValueError,'filter'):
            pre.png_integrity(png(2,2,2,raw=data))

    def test_reject_indexed_image_without_palette(self):
        with self.assertRaisesRegex(ValueError,'palette'):
            pre.png_integrity(png(2,2,3))

    def test_accept_indexed_image_with_palette(self):
        result=pre.png_integrity(png(2,2,3,palette=b'\xff\x00\x00'))
        self.assertEqual(result['png_color_type'],3)

    def test_reject_palette_after_idat(self):
        ihdr=struct.pack('>IIBBBBB',1,1,8,3,0,0,0)
        raw=(pre.PNG_SIG+chunk(b'IHDR',ihdr)+
             chunk(b'IDAT',zlib.compress(b'\0\0'))+
             chunk(b'PLTE',b'\x00\x00\x00')+
             chunk(b'IEND',b''))
        with self.assertRaisesRegex(ValueError,'palette'):
            pre.png_integrity(raw)

    def test_reject_unknown_critical_chunk(self):
        with self.assertRaisesRegex(ValueError,'critical'):
            pre.png_integrity(png(2,2,2,extra=[chunk(b'ZZZZ',b'bad')]))

    def test_allow_standard_ancillary_chunk(self):
        result=pre.png_integrity(png(2,2,2,extra=[chunk(b'tEXt',b'k\x00v')]))
        self.assertTrue(result['scanline_size_and_filters_verified'])

    def test_reject_valid_deflate_with_excess_pixels(self):
        payload=b'\0'+b'\x00'*6+b'\0'+b'\x00'*6+b'\x00'*500
        with self.assertRaisesRegex(ValueError,'inflated|scanline'):
            pre.png_integrity(png(2,2,2,raw=payload))

    def test_reject_extra_bytes_after_zlib_stream(self):
        ihdr=struct.pack('>IIBBBBB',1,1,8,2,0,0,0)
        raw=(pre.PNG_SIG+chunk(b'IHDR',ihdr)+
             chunk(b'IDAT',zlib.compress(b'\0\x01\x02\x03')+b'bad')+
             chunk(b'IEND',b''))
        with self.assertRaisesRegex(ValueError,'trailing'):
            pre.png_integrity(raw)

    def test_reject_noncontiguous_idat(self):
        compressed=zlib.compress(b'\0\x01\x02\x03')
        ihdr=struct.pack('>IIBBBBB',1,1,8,2,0,0,0)
        raw=(pre.PNG_SIG+chunk(b'IHDR',ihdr)+
             chunk(b'IDAT',compressed[:4])+chunk(b'tEXt',b'k\x00v')+
             chunk(b'IDAT',compressed[4:])+chunk(b'IEND',b''))
        with self.assertRaisesRegex(ValueError,'noncontiguous'):
            pre.png_integrity(raw)

if __name__=='__main__':
    unittest.main()
