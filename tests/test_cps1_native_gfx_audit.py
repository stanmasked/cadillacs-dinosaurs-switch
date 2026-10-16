"""ROM-free portable end-to-end native graphics audit of all CPS-1 layouts."""
import shutil
import unittest

from tools.cps1_native_gfx_audit import audit

GFX=bytes((i*31+(i//5)*17+7)&255 for i in range(4096))


@unittest.skipUnless(shutil.which('gcc'),'Host C compiler required')
class NativeGfxAuditTests(unittest.TestCase):
    def test_four_formats_and_zero_mismatches(self):
        report=audit(GFX,count=12)
        self.assertEqual(report['mismatched_tiles'],0)
        self.assertEqual(len(report['checks']),4)
        self.assertEqual([r['tested_tiles'] for r in report['checks']],[12]*4)
        self.assertEqual(report['tested_pixels'],12*(64+64+256+1024))
        self.assertTrue(all(len(r['decoded_sample_sha256'])==64 for r in report['checks']))

    def test_single_sample_does_not_oversample(self):
        report=audit(GFX,count=1)
        self.assertEqual(report['tested_pixels'],64+64+256+1024)
        self.assertTrue(all(item['tested_tiles']==1 for item in report['checks']))

    def test_bytearray_input_and_reproducibility(self):
        a=audit(GFX,count=9,seed=179)
        b=audit(bytearray(GFX),count=9,seed=179)
        self.assertEqual(a,b)

    def test_reject_malformed_region_and_sample_counts(self):
        for data in (b'',bytes(511)):
            with self.assertRaises(ValueError):audit(data)
        for n in (0,-1,65537,1.5,True):
            with self.assertRaises(ValueError):audit(GFX,count=n)


if __name__=='__main__':
    unittest.main()
