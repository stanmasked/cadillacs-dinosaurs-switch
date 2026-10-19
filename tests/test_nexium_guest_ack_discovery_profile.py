"""ROM-free regression for descriptive, bound ACK-discovery histograms.

Generated inputs below are synthetic; real guest reports enter only the
paired NeXium compare job after NRO-binding and 900-tick checks pass.
"""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import copy
import tempfile
import unittest

from tools import compare_nexium_guest_ack_discovery as profile
from test_nexium_audio_ack_tick_trace import fixture


class BoundGuestACKProfileTests(unittest.TestCase):
    def test_uniform_one_ack_per_tick_has_no_spurious_gaps(self):
        rows,_=fixture()
        result=profile.summarize(rows)
        self.assertEqual(result['simulated_ticks'],900)
        self.assertEqual(
            (result['one_page_discovery_ticks'],
             result['two_page_discovery_ticks'],
             result['zero_page_discovery_ticks']), (900,0,0))
        self.assertEqual(result['released_pages'],900)
        self.assertEqual(result['ack_discovery_ticks'],900)
        self.assertEqual(result['max_consecutive_ticks_without_ack_discovery'],0)
        self.assertEqual(result['max_consecutive_skipped_pcm_ticks'],0)
        self.assertEqual(len(result['windows']),6)
        for window in result['windows']:
            self.assertEqual(window['released_pages'],150)
            self.assertEqual(window['phases']['single']['simulation_ticks'],150)
            self.assertEqual(window['phases']['first']['simulation_ticks'],0)
            self.assertEqual(window['phases']['later']['simulation_ticks'],0)
        self.assertFalse(result['exact_service_release_timestamps_available'])

    def test_two_page_ack_on_one_tick_does_not_double_count_discovery_ticks(self):
        rows,_=fixture()
        for tick in (2,50,199,749):
            row=rows[tick]
            row['released']=2
        result=profile.summarize(rows)
        self.assertEqual(result['released_pages'],904)
        self.assertEqual(result['ack_discovery_ticks'],900)
        self.assertEqual(result['two_page_discovery_ticks'],4)
        self.assertEqual(result['one_page_discovery_ticks'],896)

    def test_long_zero_release_streak_and_skips_are_counted_in_simulated_ticks(self):
        rows,_=fixture()
        for tick in range(148,155):
            rows[tick]['released']=0
            rows[tick]['submitted']=0
            rows[tick]['skipped']=1
        result=profile.summarize(rows)
        self.assertEqual(result['released_pages'],893)
        self.assertEqual(result['ack_discovery_ticks'],893)
        self.assertEqual(result['max_consecutive_ticks_without_ack_discovery'],7)
        self.assertEqual(result['max_consecutive_skipped_pcm_ticks'],7)
        self.assertEqual(result['windows'][0]
                         ['max_consecutive_ticks_without_ack_discovery'],2)
        self.assertEqual(result['windows'][1]
                         ['max_consecutive_ticks_without_ack_discovery'],5)
        self.assertEqual(result['skipped_blocks'],7)

    def test_explicit_phase_partition_has_no_guesswork_from_render_frames(self):
        rows,_=fixture()
        # A complete synthetic frame with three simulation ticks.
        # This test exercises histogram grouping only, not valid service
        # ownership or actual NeXium pacing.
        rows[300]['batch_size']=3
        rows[300]['batch_position']=0
        rows[301]['batch_size']=3
        rows[301]['batch_position']=1
        rows[302]['batch_size']=3
        rows[302]['batch_position']=2
        rows[301]['released']=2
        result=profile.summarize(rows)
        win=result['windows'][2]
        self.assertEqual(win['phases']['first']['simulation_ticks'],1)
        self.assertEqual(win['phases']['later']['simulation_ticks'],2)
        self.assertEqual(win['phases']['later']['release_pages'],3)
        self.assertEqual(win['phases']['single']['simulation_ticks'],147)
        self.assertEqual(win['ack_discovery_ticks'],150)

    def test_wrong_trace_size_and_invalid_page_conservation_are_refused(self):
        rows,_=fixture()
        for sample in ([],rows[:899],None,()):
            with self.subTest(sample=str(type(sample))),self.assertRaises(ValueError):
                profile.summarize(sample)
        wrong=copy.deepcopy(rows)
        wrong[0]['skipped']=1
        with self.assertRaises(ValueError):
            profile.summarize(wrong)

    def test_two_invalid_bound_guest_inputs_fail_closed_without_writing_file(self):
        with tempfile.TemporaryDirectory() as d:
            tmp=Path(d)
            output=tmp/'profile.json'
            args=[]
            for field in ('baseline-trace','baseline-report','baseline-binding',
                          'baseline-nro','experimental-trace',
                          'experimental-report','experimental-binding',
                          'experimental-nro'):
                args.extend(['--'+field,str(tmp/field)])
            args.extend(['--out',str(output)])
            with redirect_stdout(StringIO()) as stdout:
                self.assertEqual(profile.main(args),1)
            self.assertIn('INCONCLUSIVE_GUEST_ACK_DISCOVERY_PROFILE',
                          stdout.getvalue())
            self.assertFalse(output.exists())


if __name__=='__main__':
    unittest.main()
