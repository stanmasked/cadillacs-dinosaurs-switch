import struct
import unittest
from tools.cps1_tiles import decode_tile, diagnostic_atlas, tile_count

def encode_pattern(width, height, pixel, half=0):
    """Synthetic 4bpp planar fixture matching MAME bit offsets."""
    size = 64 if width == 8 else width * height // 2
    row_stride = 8 if width == 8 else width // 2
    out = bytearray(size)
    for y in range(height):
        for x in range(width):
            pen = pixel(x, y)
            for bitplane in range(4):
                if pen & (1 << bitplane):
                    addr = y * row_stride + half + (x // 8) * 4 + (3 - bitplane)
                    out[addr] |= 1 << (7 - (x % 8))
    return bytes(out)

class TileTests(unittest.TestCase):
    def test_layout_capacities(self):
        region = bytes(0x400000)
        self.assertEqual(tile_count(region, '8x8-left'), 65536)
        self.assertEqual(tile_count(region, '8x8-right'), 65536)
        self.assertEqual(tile_count(region, '16x16'), 32768)
        self.assertEqual(tile_count(region, '32x32'), 8192)

    def test_decode_8x8_both_halves(self):
        left = encode_pattern(8, 8, lambda x,y: x, half=0)
        right = encode_pattern(8, 8, lambda x,y: 8+y, half=4)
        merged = bytes(a | b for a,b in zip(left,right))
        self.assertEqual(decode_tile(merged, '8x8-left', 0), bytes(x for y in range(8) for x in range(8)))
        self.assertEqual(decode_tile(merged, '8x8-right', 0), bytes(8+y for y in range(8) for x in range(8)))

    def test_decode_16x16_planes_and_rows(self):
        region = encode_pattern(16,16,lambda x,y: (x+y) % 16)
        self.assertEqual(decode_tile(region, '16x16', 0),bytes((x+y)%16 for y in range(16) for x in range(16)))

    def test_decode_32x32_planes_and_rows(self):
        region = encode_pattern(32,32,lambda x,y: (x//2+y//3)%16)
        self.assertEqual(decode_tile(region, '32x32', 0),bytes((x//2+y//3)%16 for y in range(32) for x in range(32)))

    def test_tile_index_and_unknown_layout(self):
        region = bytes(128)
        with self.assertRaises(IndexError):
            decode_tile(region,'16x16',1)
        with self.assertRaises(IndexError):
            decode_tile(region,'16x16',-1)
        with self.assertRaises(ValueError):
            decode_tile(region,'64x64',0)

    def test_atlas_png_roundtrip(self):
        region = encode_pattern(16,16,lambda x,y: (x+y)%16)
        png = diagnostic_atlas(region, '16x16', count=1, columns=1, scale=2)
        self.assertEqual(png[:8], b'\x89PNG\r\n\x1a\n')
        length = struct.unpack('>I',png[8:12])[0]
        self.assertEqual(png[12:16],b'IHDR')
        self.assertEqual(struct.unpack('>II',png[16:24]),(32,32))
        self.assertEqual(length,13)
        with self.assertRaises(ValueError):
            diagnostic_atlas(region, '16x16', count=2)

if __name__ == '__main__':
    unittest.main()
