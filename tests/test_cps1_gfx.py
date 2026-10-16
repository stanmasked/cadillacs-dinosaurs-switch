import unittest
from tools.cps1_gfx import LANES, ROM_SIZE, assemble_gfx

class GfxTests(unittest.TestCase):
    def test_region_layout(self):
        data = {name: bytes([10 + i]) * ROM_SIZE for i, (name, _) in enumerate(LANES)}
        gfx = assemble_gfx(data.__getitem__)
        self.assertEqual(len(gfx), 0x400000)
        self.assertEqual(gfx[:8], bytes([10, 10, 11, 11, 12, 12, 13, 13]))
        self.assertEqual(gfx[0x200000:0x200008], bytes([14,14,15,15,16,16,17,17]))
        self.assertEqual(gfx[0x1ffff8:0x200000], bytes([10,10,11,11,12,12,13,13]))
    def test_word_order(self):
        data = {name: bytes(ROM_SIZE) for name, _ in LANES}
        data[LANES[0][0]] = b'\x12\x34' * (ROM_SIZE//2)
        gfx = assemble_gfx(data.__getitem__)
        self.assertEqual(gfx[:2], b'\x12\x34')
        self.assertEqual(gfx[8:10], b'\x12\x34')
    def test_wrong_size(self):
        with self.assertRaises(ValueError):
            assemble_gfx(lambda name: b'bad')

if __name__ == '__main__':
    unittest.main()
