import unittest
from tools.cps1_program import assemble_program, swap_16, program_metadata

class ProgramMapTests(unittest.TestCase):
    def test_swap(self):
        self.assertEqual(swap_16(bytes.fromhex('00112233')), bytes.fromhex('11003322'))
    def test_odd_size(self):
        with self.assertRaises(ValueError):
            swap_16(b'abc')
    def test_layout(self):
        names = ('cde_23a.8f', 'cde_22a.7f', 'cde_21a.6f')
        data = {n: bytes([i*16+1,i*16+2])*(0x80000//2) for i,n in enumerate(names)}
        result = assemble_program(data.__getitem__)
        self.assertEqual(len(result), 0x180000)
        self.assertEqual(result[:2], b'\x02\x01')
        self.assertEqual(result[0x80000:0x80002], b'\x12\x11')
        self.assertEqual(result[0x100000:0x100002], b'\x22\x21')
    def test_size_rejection(self):
        with self.assertRaises(ValueError):
            assemble_program(lambda _: b'\x00\x00')
    def test_vectors(self):
        meta = program_metadata(bytes.fromhex('00ff0e660000041a')+bytes(24))
        self.assertEqual(meta['initial_sp'], '0x00FF0E66')
        self.assertEqual(meta['reset_pc'], '0x0000041A')
        self.assertFalse(meta['reset_pc_inside_region'])

if __name__ == '__main__':
    unittest.main()
