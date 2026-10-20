"""Stage 266 field-failure regression: real two-tick frame crosses a window.

Synthetic, ROM-free 150-tick aggregate witnesses. A one-tick LATER half
in the following window is structurally possible only if the preceding
window contains a FIRST tick; it is not proof of the same native frame.
The per-900-tick guest ACK verifier separately checks raw frame IDs.
"""
import copy
import unittest

from tools import compare_nexium_audio_stress_runs as check


def boundary_report():
    windows = [
        {'tick_start':150*i, 'tick_end':150*(i+1),
         'first_tick_steps':1, 'later_tick_steps':1}
        for i in range(6)
    ]
    # A two-tick frame starts at simulation tick 300 and concludes at
    # tick 301. The 300..450 window has one LATER tick but no new start.
    windows[2]['first_tick_steps'] = 0
    windows[2]['later_tick_steps'] = 1
    return {
        'batch_tick_position_probe_present':True,
        'checkpoint_batch_position_intervals':windows,
    }


class SplitFrameWindowRegressionTests(unittest.TestCase):
    def test_valid_one_tick_carry_across_300tick_boundary(self):
        self.assertTrue(check.possible_one_tick_boundary_carry(
            boundary_report(), 2, 1, 0))

    def test_only_exactly_one_later_tick_is_permitted(self):
        r = boundary_report()
        for b, frames in ((0,0),(2,0),(1,1),(3,0),(1,2)):
            with self.subTest(b=b, frames=frames):
                self.assertFalse(check.possible_one_tick_boundary_carry(
                    r, 2, b, frames))

    def test_first_window_cannot_carry_without_previous(self):
        self.assertFalse(check.possible_one_tick_boundary_carry(
            boundary_report(),0,1,0))

    def test_missing_position_proof_refused(self):
        r=boundary_report()
        for value in (None, False, 0, 'true'):
            t=copy.deepcopy(r)
            t['batch_tick_position_probe_present']=value
            with self.subTest(value=value):
                self.assertFalse(check.possible_one_tick_boundary_carry(
                    t,2,1,0))
        t=boundary_report()
        del t['checkpoint_batch_position_intervals']
        self.assertFalse(check.possible_one_tick_boundary_carry(t,2,1,0))

    def test_forged_or_incomplete_window_carry_refused(self):
        for mutation in (
            lambda w: w[2].update(first_tick_steps=1),
            lambda w: w[2].update(later_tick_steps=0),
            lambda w: w[2].update(later_tick_steps=2),
            lambda w: w[1].update(first_tick_steps=0),
            lambda w: w[1].update(tick_end=299),
            lambda w: w[2].update(tick_start=301),
            lambda w: w[2].update(later_tick_steps=True),
        ):
            r=boundary_report()
            mutation(r['checkpoint_batch_position_intervals'])
            self.assertFalse(check.possible_one_tick_boundary_carry(
                r,2,1,0))

    def test_legacy_aggregate_without_frame_positions_fails_closed(self):
        report={'batch_tick_position_probe_present':False,
                'checkpoint_batch_position_intervals':None}
        self.assertFalse(check.possible_one_tick_boundary_carry(
            report,3,1,0))


if __name__=='__main__':
    unittest.main()
