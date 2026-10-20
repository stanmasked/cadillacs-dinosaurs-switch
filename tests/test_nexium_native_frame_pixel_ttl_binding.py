"""Stage 267: actual guest CSV/trace consistency at token rollover.

Synthetic original-NRO-shaped files are strictly interface regression
fixtures. They do NOT prove a real NeXium run beyond frame 65535.
"""
import unittest

from test_nexium_host_frame_token import FrameTokenTests, write_csv
from tools import verify_nexium_host_frame_token as verifier


class NativePixelFrameBindingTests(unittest.TestCase):
    def setUp(self):
        f=FrameTokenTests('test_matching_real_submitted_render_id')
        f.setUp()
        self.addCleanup(f.doCleanups)
        self.f=f

    def write_trace(self):
        write_csv(self.f.trace,verifier.CSV_FIELDS,self.f.native)

    def write_pixels(self):
        write_csv(self.f.frame,verifier.GUEST_FIELDS,[self.f.sample])

    def test_unmodified_realistic_same_frame_trace_passes(self):
        proof=self.f.verify()
        self.assertEqual(proof['status'],verifier.SUCCESS)
        self.assertEqual(proof['matched_native_render_iteration'],3141)
        self.assertEqual(proof['matched_caption_ttl'],6)
        self.assertEqual(proof['matched_impact_ttl'],6)

    def test_first_16bit_wrap_with_native_trace_and_csv_passes(self):
        first=65536+3141
        self.f.native[0]['render_iteration']=str(first)
        self.f.native[1]['render_iteration']=str(first+1)
        self.f.sample['render_iteration']=str(first)
        self.write_trace();self.write_pixels()
        self.assertEqual(
            self.f.verify()['matched_native_render_iteration'],first)

    def test_second_16bit_wrap_with_native_trace_and_csv_passes(self):
        first=2*65536+3141
        self.f.native[0]['render_iteration']=str(first)
        self.f.native[1]['render_iteration']=str(first+1)
        self.f.sample['render_iteration']=str(first)
        self.write_trace();self.write_pixels()
        self.assertEqual(
            self.f.verify()['matched_native_render_iteration'],first)

    def test_guest_pixel_sample_may_precede_host_observed_token_frame(self):
        # Correct code MUST NOT demand the first guest pixel CSV frame
        # equal the later frame whose X11 token is observed on host.
        first=65536+3140
        self.f.native[0].update(render_iteration=str(first),
                                token_u16='3140')
        self.f.native[1].update(render_iteration=str(first+1),
                                token_u16='3141')
        self.f.sample['render_iteration']=str(first)
        self.write_trace();self.write_pixels()
        self.assertEqual(
            self.f.verify()['matched_native_render_iteration'],first+1)

    def test_two_native_frames_with_same_u16_token_rejected(self):
        self.f.native[1].update(render_iteration=str(65536+3141),
                                token_u16='3141')
        self.write_trace()
        with self.assertRaises(ValueError):self.f.verify()

    def test_forged_guest_frame_feedback_ttl_rejected(self):
        self.f.sample['feedback_ttl']='5'
        self.write_pixels()
        with self.assertRaises(ValueError):self.f.verify()

    def test_forged_guest_frame_impact_ttl_rejected(self):
        self.f.sample['impact_ttl']='5'
        self.write_pixels()
        with self.assertRaises(ValueError):self.f.verify()

    def test_forged_native_trace_feedback_ttl_rejected(self):
        self.f.native[0]['feedback_ttl']='5'
        self.write_trace()
        with self.assertRaises(ValueError):self.f.verify()

    def test_forged_native_trace_impact_ttl_rejected(self):
        self.f.native[0]['impact_ttl']='5'
        self.write_trace()
        with self.assertRaises(ValueError):self.f.verify()

    def test_noncanonical_guest_feedback_or_impact_refused(self):
        for col in ('feedback_ttl','impact_ttl'):
            for bad in ('00','07','-1','1.0','', 'not-an-integer'):
                with self.subTest(column=col,bad=bad):
                    good=self.f.sample[col]
                    self.f.sample[col]=bad
                    self.write_pixels()
                    with self.assertRaises(ValueError):self.f.verify()
                    self.f.sample[col]=good
        self.write_pixels()
        self.assertEqual(self.f.verify()['status'],verifier.SUCCESS)


if __name__=='__main__':
    unittest.main()
