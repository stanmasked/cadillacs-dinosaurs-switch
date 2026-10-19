"""Synthetic-only ROM-free tests for capped frame clock PCM skip cross-tabs.

Real NeXium results require NRO/mode/SHA attestation through paired CI;
these fixtures are not game/audio measurements.
"""
import copy
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from tools import nexium_guest_frame_interval_pcm_bins as bins


def fixture():
    clock = [
        dict(frame_id=i+1, elapsed_ns_capped=16_666_666,
             frame_game_ticks=1, stress_game_ticks=1)
        for i in range(900)
    ]
    guest = [
        dict(frame_id=i+1, batch_size=1, batch_position=0,
             released=1, submitted=1, skipped=0)
        for i in range(900)
    ]
    return clock, guest


class IntervalPCMExposureTests(unittest.TestCase):
    def test_uniform_900_frames_rate_conserved(self):
        frames, guest = fixture()
        result = bins.summarize(frames, guest)
        self.assertEqual(result['total']['render_iterations'], 900)
        self.assertEqual(result['total']['measured_game_ticks'], 900)
        self.assertEqual(result['total']['ack_pages'], 900)
        self.assertEqual(result['total']['pcm_skipped'], 0)
        self.assertEqual(result['by_existing_capped_frame_interval'][
            '15_to_below_20ms']['measured_game_ticks'], 900)
        self.assertIsNone(result['by_declared_game_steps_per_render_iteration'][
            'zero']['pcm_skip_rate_per_measured_game_tick'])
        self.assertFalse(result['within_batch_comparison_causal'])

    def test_four_bin_edges_exact_rates_and_long_frame_run(self):
        frames, guest = fixture()
        boundaries = [14_999_999, 15_000_000, 19_999_999,
                      20_000_000, 24_999_999, 25_000_000, 250_000_000]
        for i, ns in enumerate(boundaries):
            frames[i]['elapsed_ns_capped'] = ns
            guest[i]['skipped'] = int(i in (0, 3, 4, 5, 6))
            guest[i]['submitted'] = 1 - guest[i]['skipped']
        result = bins.summarize(frames, guest)
        self.assertEqual(result['total']['pcm_skipped'], 5)
        self.assertEqual(result['below_20ms']['pcm_skipped'], 1)
        self.assertEqual(result['at_least_20ms']['pcm_skipped'], 4)
        self.assertEqual(result['at_least_20ms']['measured_game_ticks'], 4)
        self.assertEqual(result['render_intervals_at_existing_250ms_cap'], 1)
        self.assertEqual(result['longest_render_interval_run_at_least_20ms'], 4)
        self.assertEqual(result['render_interval_runs_at_least_20ms'], 1)
        self.assertEqual(result['at_least_20ms'][
            'pcm_skip_rate_per_measured_game_tick'],
            {'numerator': 4, 'denominator': 4})

    def test_zero_tick_render_frames_and_two_tick_frame_not_double_counted(self):
        _, guest = fixture()
        frames = []
        i = 0
        while i < 900:
            count = 2 if i == 2 else 1
            fid = len(frames) + 1
            frames.append(dict(frame_id=fid,
                               elapsed_ns_capped=20_000_000 if count == 2
                               else 16_000_000,
                               frame_game_ticks=count,
                               stress_game_ticks=count))
            for j in range(count):
                guest[i+j].update(frame_id=fid, batch_size=count,
                                  batch_position=j)
            i += count
        for at in (1, 300, 600):
            frames.insert(at, dict(frame_id=0,
                                   elapsed_ns_capped=10_000_000,
                                   frame_game_ticks=0, stress_game_ticks=0))
        offset = 0
        for i, frame in enumerate(frames):
            frame['frame_id'] = i + 1
            for j in range(frame['stress_game_ticks']):
                guest[offset+j]['frame_id'] = i + 1
            offset += frame['stress_game_ticks']
        result = bins.summarize(frames, guest)
        self.assertEqual(result['total']['render_iterations'], 902)
        self.assertEqual(result['total']['measured_game_ticks'], 900)
        self.assertEqual(result['by_declared_game_steps_per_render_iteration'][
            'multiple']['measured_game_ticks'], 2)
        self.assertEqual(result['by_declared_game_steps_per_render_iteration'][
            'zero']['render_iterations'], 3)
        self.assertIsNone(result['by_declared_game_steps_per_render_iteration'][
            'zero']['pcm_skip_rate_per_measured_game_tick'])

    def test_observation_boundaries_are_not_imputed(self):
        frames, guest = fixture()
        frames[0]['frame_game_ticks'] = 2
        frames[-1]['frame_game_ticks'] = 2
        guest[0].update(batch_size=2, batch_position=1)
        guest[-1].update(batch_size=2, batch_position=0)
        result = bins.summarize(frames, guest)
        self.assertEqual(result['boundary_frames_with_unobserved_game_steps'], 2)
        self.assertEqual(result['total']['full_game_ticks'], 902)
        self.assertEqual(result['total']['measured_game_ticks'], 900)

    def test_skip_rates_keep_original_guest_denominator(self):
        frames, guest = fixture()
        for i in (1, 22, 50):
            guest[i]['skipped'] = 1
            guest[i]['submitted'] = 0
        result = bins.summarize(frames, guest)
        self.assertEqual(result['total']['pcm_skipped'], 3)
        self.assertEqual(result['total']['pcm_submitted'], 897)
        self.assertEqual(result['below_20ms'][
            'pcm_skip_rate_per_measured_game_tick'],
            {'numerator': 3, 'denominator': 900})

    def test_forged_frame_intervals_and_pcm_claims_rejected(self):
        frames, guest = fixture()
        for key, value in (('frame_id', 900),
                           ('elapsed_ns_capped', 250000001),
                           ('frame_game_ticks', 16),
                           ('frame_game_ticks', True),
                           ('stress_game_ticks', 2),
                           ('stress_game_ticks', 0)):
            fraud = copy.deepcopy(frames)
            fraud[10][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                bins.summarize(fraud, guest)
        for key, value in (('frame_id', 999), ('batch_position', 1),
                           ('batch_size', 2), ('released', 3),
                           ('skipped', 2), ('submitted', True)):
            fraud = copy.deepcopy(guest)
            fraud[9][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                bins.summarize(frames, fraud)

    def test_interior_missing_ticks_and_truncated_evidence_rejected(self):
        frames, guest = fixture()
        frames[8]['frame_game_ticks'] = 2
        frames[8]['stress_game_ticks'] = 1
        with self.assertRaises(ValueError):
            bins.summarize(frames, guest)
        for bad_frames, bad_guest in (
            (frames[:8], guest), (frames, guest[:-1]), ([], guest),
            (None, guest),
        ):
            with self.assertRaises(ValueError):
                bins.summarize(bad_frames, bad_guest)

    def test_missing_nro_bound_inputs_never_publish_success_report(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            args = []
            for key in ('baseline-clock', 'baseline-trace',
                        'baseline-report', 'baseline-binding', 'baseline-nro',
                        'experimental-clock', 'experimental-trace',
                        'experimental-report', 'experimental-binding',
                        'experimental-nro'):
                args += ['--' + key, str(root / key)]
            output = root / 'invalid.json'
            args += ['--out', str(output)]
            with redirect_stdout(StringIO()) as stream:
                self.assertEqual(bins.main(args), 1)
            self.assertIn('INCONCLUSIVE_GUEST_INTERVAL_PCM_BINS',
                          stream.getvalue())
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
