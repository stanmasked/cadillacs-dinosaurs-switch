"""ROM-free binding of the selected NRO audio mode to guest witnesses."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from tools import verify_nexium_audio_mode_binding as binding
from test_nexium_audio_mid_batch_ab import complete


class GuestAudioModeBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='dino-audio-mode-')
        self.report=Path(self.temp.name)/'guest.json'

    def tearDown(self):
        self.temp.cleanup()

    def write(self,enabled=False,variation=0):
        report=complete(enabled,variation)
        self.report.write_text(json.dumps(report,sort_keys=True)+'\n',
                               encoding='ascii')
        return report

    def test_baseline_mode_requires_zero_guest_extra_polls(self):
        self.write(False)
        result=binding.attest('baseline',self.report)
        self.assertEqual(result['status'],'SELECTED_AUDIO_MODE_WITNESSED_BY_GUEST')
        self.assertEqual(result['selected_mode'],'baseline')
        self.assertFalse(result['guest_poll_enabled'])
        self.assertEqual(result['guest_poll_calls'],0)
        self.assertEqual(result['guest_poll_released_pages'],0)
        self.assertEqual(result['guest_simulation_ticks'],900)
        self.assertFalse(result['audio_latency_verified'])
        self.assertFalse(result['causal_audio_improvement_verified'])

    def test_experimental_mode_requires_guest_extra_poll_evidence(self):
        self.write(True,1)
        result=binding.attest('extra-poll',self.report)
        self.assertEqual(result['status'],'SELECTED_AUDIO_MODE_WITNESSED_BY_GUEST')
        self.assertEqual(result['selected_mode'],'extra-poll')
        self.assertTrue(result['guest_poll_enabled'])
        self.assertEqual(result['guest_poll_calls'],150)
        self.assertEqual(result['guest_poll_released_pages'],6)
        self.assertEqual(result['guest_later_batch_steps'],150)
        self.assertFalse(result['physical_switch_audio_verified'])

    def test_requested_mode_must_equal_guest_report_mode(self):
        for requested,enabled in (('baseline',True),('extra-poll',False)):
            with self.subTest(requested=requested):
                self.write(enabled)
                with self.assertRaises(ValueError):
                    binding.attest(requested,self.report)

    def test_guest_poll_forgery_is_rejected_even_when_flag_matches(self):
        report=self.write(True,1)
        report['guest_mid_batch_extra_poll_calls']-=1
        self.report.write_text(json.dumps(report)+'\n',encoding='ascii')
        with self.assertRaises(ValueError):
            binding.attest('extra-poll',self.report)

    def test_report_needs_full_guest_900tick_invariants(self):
        report=self.write(False)
        report['audout_blocks_skipped']+=1
        self.report.write_text(json.dumps(report)+'\n',encoding='ascii')
        with self.assertRaises(ValueError):
            binding.attest('baseline',self.report)

    def test_missing_or_invalid_mode_is_never_assumed_baseline(self):
        self.write(False)
        for requested in ('','experimental','BASELINE',None):
            with self.subTest(requested=requested):
                with self.assertRaises(ValueError):
                    binding.attest(requested,self.report)
        with self.assertRaises(ValueError):
            binding.attest('baseline',self.report.with_name('absent.json'))

    def test_cli_valid_mode_reports_success_with_no_hardware_claims(self):
        self.write(True,1)
        captured=StringIO()
        with redirect_stdout(captured):
            rc=binding.main(['--selected-mode','extra-poll',
                             '--report',str(self.report)])
        self.assertEqual(rc,0)
        report=json.loads(captured.getvalue())
        self.assertEqual(report['selected_mode'],'extra-poll')
        self.assertFalse(report['original_arcade_audio_verified'])
        self.assertFalse(report['physical_switch_audio_verified'])

    def test_cli_guest_mode_mismatch_fails_closed(self):
        self.write(False)
        captured=StringIO()
        with redirect_stdout(captured):
            rc=binding.main(['--selected-mode','extra-poll',
                             '--report',str(self.report)])
        self.assertEqual(rc,1)
        report=json.loads(captured.getvalue())
        self.assertEqual(report['status'],
                         'INCONCLUSIVE_AUDIO_MODE_NOT_GUEST_BOUND')
        self.assertFalse(report['causal_audio_improvement_verified'])


if __name__=='__main__':
    unittest.main()
