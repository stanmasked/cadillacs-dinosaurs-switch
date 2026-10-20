"""Stage 265 exhaustive sub-microsecond host sampling-bound proof.

Use exact integer nanosecond clocks independently of the production
microsecond verifier and refuse claims of guest HID/physical LCD latency.
"""
import unittest

from tools import verify_nexium_host_first_sample_gap_paired as witness


class RoundingHostBlindIntervalTests(unittest.TestCase):
    def test_every_nanosecond_completion_phase_with_eleven_delays(self):
        # Test every 0..999ns phase of host xdotool subprocess return.
        # The sampler starts no earlier than the command completed.
        delays=(0, 1, 2, 499, 500, 999, 1000, 1001, 1499, 9000, 20000)
        for complete_ns in range(1000):
            cmd_floor=complete_ns//1000
            cmd_ceil=(complete_ns+999)//1000
            for gap_ns in delays:
                sample_ns=complete_ns+gap_ns
                start_floor=sample_ns//1000
                low,high=witness.conservative_initial_gap_bounds_us(
                    start_floor,cmd_floor,cmd_ceil)
                # The real gap is known only to this synthetic oracle,
                # not to real NeXium which stores rounded host offsets.
                self.assertLessEqual(low*1000,gap_ns)
                self.assertGreaterEqual(high*1000,gap_ns)
                self.assertLessEqual(high-low,3)
                self.assertGreaterEqual(low,0)

    def test_submicrosecond_command_origin_does_not_change_bounds(self):
        for origin in (1, 9, 499, 999, 1001, 502_731, 999_999):
            for duration in (0, 1, 999, 1000, 1001, 12_345):
                for gap in (0, 1, 4, 511, 1000, 11_111):
                    # The stored offsets are relative to command BEGIN,
                    # not to global monotonic epoch or X11 window lifetime.
                    stop=origin+duration
                    sample=stop+gap
                    d=stop-origin
                    s=sample-origin
                    low,high=witness.conservative_initial_gap_bounds_us(
                        s//1000,d//1000,(d+999)//1000)
                    self.assertLessEqual(low*1000,gap)
                    self.assertGreaterEqual(high*1000,gap)

    def test_clock_phase_boundaries_exactly_at_microsecond(self):
        self.assertEqual(
            witness.conservative_initial_gap_bounds_us(5000,500,500),
            (4500,4501))
        self.assertEqual(
            witness.conservative_initial_gap_bounds_us(5000,500,501),
            (4499,4501))
        self.assertEqual(
            witness.conservative_initial_gap_bounds_us(0,0,0),
            (0,1))
        self.assertEqual(
            witness.conservative_initial_gap_bounds_us(500,500,501),
            (0,1))

    def test_reversed_command_envelope_rejected(self):
        with self.assertRaises(ValueError):
            witness.conservative_initial_gap_bounds_us(5000,502,501)

    def test_noncanonical_more_than_one_us_floor_ceil_rejected(self):
        with self.assertRaises(ValueError):
            witness.conservative_initial_gap_bounds_us(5000,500,502)

    def test_capture_floor_earlier_than_command_completion_rejected(self):
        with self.assertRaises(ValueError):
            witness.conservative_initial_gap_bounds_us(499,500,501)

    def test_negative_and_out_of_range_host_offsets_rejected(self):
        for args in ((-1,0,0),(0,-1,0),(0,0,-1),
                     (2_500_002,0,0),(2_500_001,0,2_500_002)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    witness.conservative_initial_gap_bounds_us(*args)

    def test_float_string_and_bool_values_rejected(self):
        for args in ((True,0,0),(0,False,0),(0,0,True),
                     (0.0,0,0),(1,0.0,0),(1,0,0.0),
                     ('1',0,0),(1,'0',0),(1,0,'0')):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    witness.conservative_initial_gap_bounds_us(*args)

    def test_endpoint_bound_does_not_claim_exact_first_frame(self):
        low,high=witness.conservative_initial_gap_bounds_us(6500,500,501)
        self.assertEqual((low,high),(5999,6001))
        # This helper has NO physical display/guest frame data at all.
        self.assertNotEqual(low,high)

if __name__ == '__main__':
    unittest.main()
