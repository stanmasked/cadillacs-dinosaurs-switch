"""ROM-free checks for two uncontrolled NeXium baseline audio runs."""
import json
from pathlib import Path
import tempfile
import unittest

from tools import compare_nexium_audio_baseline_repeats as repeats
from test_nexium_audio_mid_batch_ab import complete


class BaselineRepeatabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='dino-baseline-repeat-')
        folder=Path(self.tmp.name)
        self.first=folder/'first.json'
        self.second=folder/'second.json'
        self.save(self.first,complete(False,0))
        self.save(self.second,complete(False,1))

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def save(path,report):
        path.write_text(json.dumps(report,sort_keys=True)+'\n',
                        encoding='ascii')

    def test_distinct_baselines_show_variation_not_treatment_effect(self):
        result=repeats.compare(self.first,self.second)
        self.assertEqual(result['status'],
                         'UNCONTROLLED_GUEST_BASELINE_REPEATS_DESCRIPTIVE_ONLY')
        self.assertTrue(result['optional_mid_batch_poll_disabled_in_both'])
        self.assertEqual(result['total_ticks_per_run'],900)
        self.assertEqual(result['second_minus_first_skips'],0)
        self.assertEqual(result['second_minus_first_later_batch_skips'],-6)
        self.assertEqual([x['second_minus_first_skips']
                          for x in result['per_150tick_deltas']],[0]*6)
        self.assertEqual([x['tick_start']
                          for x in result['per_150tick_deltas']],
                         [0,150,300,450,600,750])
        self.assertFalse(result['independent_guest_execution_authenticated'])
        self.assertFalse(result['host_workloads_matched'])
        self.assertFalse(result['exact_frame_pacing_matched'])
        self.assertFalse(result['causal_audio_improvement_verified'])
        self.assertFalse(result['physical_switch_audio_verified'])
        self.assertFalse(result['audio_latency_verified'])

    def test_baselines_can_have_different_initial_queue_occupancy(self):
        from test_compare_nexium_audio_stress_runs import with_fixed_ack_headroom
        report=with_fixed_ack_headroom(complete(False,1),start=2)
        self.save(self.second,report)
        result=repeats.compare(self.first,self.second)
        diag=result['exposure_and_queue_diagnostics']
        self.assertTrue(diag['per_150tick_batch_exposure_matched'])
        self.assertFalse(diag['matched_exposure_initial_queue_occupancy_matched'])
        self.assertTrue(diag[
            'matched_exposure_initial_queue_shift_confounds_skip_comparison'])
        self.assertIsNone(diag[
            'matched_exposure_and_returns_later_skip_count_delta'])
        self.assertEqual(
            diag['experimental_queue_150tick_boundaries'][0]['pending_at_start'],2)

    def test_missing_fixed_ack_witness_fails_closed(self):
        # Stage 157 baseline pairing requires a complete headroom witness.
        # An older report without endpoints is inconclusive, never zero.
        report=complete(False,1)
        from tools import compare_nexium_audio_stress_runs as cross
        for name in cross.FIXED_ACK_FIELDS:
            report.pop(name)
        self.save(self.second,report)
        with self.assertRaisesRegex(ValueError,'fixed-ACK queue witness'):
            repeats.compare(self.first,self.second)

    def test_experimental_poll_variant_must_not_masquerade_as_baseline(self):
        self.save(self.second,complete(True,1))
        with self.assertRaises(ValueError):
            repeats.compare(self.first,self.second)

    def test_identical_metadata_does_not_count_as_two_repeats(self):
        self.save(self.second,complete(False,0))
        with self.assertRaises(ValueError):
            repeats.compare(self.first,self.second)

    def test_forged_queue_endpoints_rejected_before_descriptive_comparison(self):
        report=complete(False,1)
        report['queue_pending_at_stress_end']=2
        self.save(self.second,report)
        with self.assertRaises(ValueError):
            repeats.compare(self.first,self.second)

    def test_cli_creates_new_output_preserving_guest_inputs(self):
        from contextlib import redirect_stdout
        from io import StringIO
        out=Path(self.tmp.name)/'result.json'
        inputs=(self.first.read_bytes(),self.second.read_bytes())
        stream=StringIO()
        with redirect_stdout(stream):
            rc=repeats.main([
                '--first',str(self.first),'--second',str(self.second),
                '--out',str(out)])
        self.assertEqual(rc,0)
        self.assertEqual(self.first.read_bytes(),inputs[0])
        self.assertEqual(self.second.read_bytes(),inputs[1])
        self.assertEqual(out.read_text(encoding='ascii'),stream.getvalue())
        self.assertEqual(json.loads(stream.getvalue())['status'],
                         'UNCONTROLLED_GUEST_BASELINE_REPEATS_DESCRIPTIVE_ONLY')

    def test_cli_refuses_to_overwrite_source_guest_report(self):
        from contextlib import redirect_stdout
        from io import StringIO
        for target in (self.first,self.second):
            with self.subTest(target=target.name):
                before=target.read_bytes()
                stream=StringIO()
                with redirect_stdout(stream):
                    rc=repeats.main([
                        '--first',str(self.first),'--second',str(self.second),
                        '--out',str(target)])
                self.assertEqual(rc,1)
                self.assertEqual(target.read_bytes(),before)
                self.assertEqual(json.loads(stream.getvalue())['status'],
                                 'INCONCLUSIVE_UNVERIFIED_BASELINE_REPEATABILITY')

    def test_cli_refuses_to_replace_previous_analysis(self):
        from contextlib import redirect_stdout
        from io import StringIO
        out=Path(self.tmp.name)/'earlier-report.json'
        out.write_text('PREVIOUS_RESULT_MUST_SURVIVE\n',encoding='ascii')
        stream=StringIO()
        with redirect_stdout(stream):
            rc=repeats.main([
                '--first',str(self.first),'--second',str(self.second),
                '--out',str(out)])
        self.assertEqual(rc,1)
        self.assertEqual(out.read_text(encoding='ascii'),
                         'PREVIOUS_RESULT_MUST_SURVIVE\n')
        self.assertEqual(json.loads(stream.getvalue())['reason'],
                         'FileExistsError')

    def test_cli_refuses_symlink_output_to_guest_source(self):
        from contextlib import redirect_stdout
        from io import StringIO
        import os
        if not hasattr(os,'symlink'):
            self.skipTest('symlink unavailable')
        out=Path(self.tmp.name)/'linked-input.json'
        before=self.first.read_bytes()
        out.symlink_to(self.first)
        stream=StringIO()
        with redirect_stdout(stream):
            rc=repeats.main([
                '--first',str(self.first),'--second',str(self.second),
                '--out',str(out)])
        self.assertEqual(rc,1)
        self.assertTrue(out.is_symlink())
        self.assertEqual(self.first.read_bytes(),before)
        self.assertEqual(json.loads(stream.getvalue())['reason'],
                         'FileExistsError')

    def test_cli_missing_report_fails_closed_without_false_claims(self):
        from contextlib import redirect_stdout
        from io import StringIO
        stream=StringIO()
        with redirect_stdout(stream):
            rc=repeats.main([
                '--first',str(self.first),
                '--second',str(self.second)+'-absent'])
        self.assertEqual(rc,1)
        report=json.loads(stream.getvalue())
        self.assertEqual(report['status'],
                         'INCONCLUSIVE_UNVERIFIED_BASELINE_REPEATABILITY')
        self.assertFalse(report['causal_audio_improvement_verified'])
        self.assertFalse(report['physical_switch_audio_verified'])


if __name__=='__main__':
    unittest.main()
