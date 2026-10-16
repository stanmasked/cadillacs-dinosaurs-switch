"""Synthetic RGB spatial error localization regression tests."""
import unittest
from tools.frame_error_profile import profile_rgba

class FrameErrorProfileTests(unittest.TestCase):
    def test_perfect_rgba(self):
        image=bytes((5,9,13,255))*16
        stats=profile_rgba(image,image,4,4)
        self.assertEqual(stats['different_rgb_pixels'],0)
        self.assertIsNone(stats['bounding_box_xyxy_inclusive'])
        self.assertEqual(stats['quadrant_mismatches_TL_TR_BL_BR'],[0]*4)

    def test_one_red_pixel(self):
        base=bytes((0,0,0,255))*16
        other=bytearray(base)
        other[(1*4+2)*4]=100
        stats=profile_rgba(base,other,4,4)
        self.assertEqual(stats['bounding_box_xyxy_inclusive'],[2,1,2,1])
        self.assertEqual(stats['row_mismatch_counts'],[0,1,0,0])
        self.assertEqual(stats['column_mismatch_counts'],[0,0,1,0])
        self.assertEqual(stats['rgb_absolute_error_totals'],dict(R=100,G=0,B=0))
        self.assertEqual(stats['quadrant_mismatches_TL_TR_BL_BR'],[0,1,0,0])

    def test_four_quadrants_and_channel_counts(self):
        a=bytes((0,0,0,255))*16
        b=bytearray(a)
        for index,channel in ((0,0),(3,1),(12,2),(15,0)):
            b[index*4+channel]=1
        p=profile_rgba(a,b,4,4)
        self.assertEqual(p['different_rgb_pixels'],4)
        self.assertEqual(p['bounding_box_xyxy_inclusive'],[0,0,3,3])
        self.assertEqual(p['quadrant_mismatches_TL_TR_BL_BR'],[1,1,1,1])
        self.assertEqual(p['rgb_channels_with_mismatches'],dict(R=2,G=1,B=1))

    def test_alpha_difference_is_not_rgb_error(self):
        original=bytes((1,2,3,255))*4
        modified=bytearray(original)
        modified[3]=0
        self.assertEqual(profile_rgba(original,modified,2,2)['different_rgb_pixels'],0)

    def test_reject_wrong_dimensions(self):
        with self.assertRaises(ValueError):profile_rgba(bytes(16),bytes(15),2,2)
        with self.assertRaises(ValueError):profile_rgba(bytes(16),bytes(16),0,2)
        with self.assertRaises(ValueError):profile_rgba(bytes(16),bytes(16),2.0,2)

if __name__=='__main__':unittest.main()
