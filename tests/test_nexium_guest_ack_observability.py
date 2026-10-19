"""ROM-free tests of what authenticated 150-tick guest ACKs CAN prove.

The fixtures deliberately contain fabricated guest reports and NRO headers;
they test strict binding, bounds, and underdetermination only. Production
CI consumes *actual* NeXium artifacts after both guest jobs succeed.
"""
import copy
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from tools import verify_nexium_guest_ack_observability as audit
from test_nexium_audio_paired_artifacts import PairedGuestAudioTests
from test_nexium_audio_mid_batch_ab import complete


class GuestACKResolutionTests(PairedGuestAudioTests):
    def profile(self,enabled=False,variation=0):
        return audit.guest_ack_profile(complete(enabled,variation),
                                       'extra-poll' if enabled else 'baseline')

    def analyze_ack(self):
        return audit.make_report(self.a,self.aa,self.b,self.bb,
                                 self.base_nro,self.extra_nro)

    def test_guest_900_tick_ack_windows_are_mode_and_nro_bound(self):
        result=self.analyze_ack()
        self.assertEqual(result['schema'],audit.SCHEMA)
        self.assertEqual(result['status'],
                         'BOUND_GUEST_ACK_COUNT_ENVELOPE_NO_SERVICE_TIMESTAMPS')
        self.assertEqual(result['window_size_ticks'],150)
        self.assertEqual(result['window_count'],6)
        self.assertTrue(result['real_guest_counter_provenance_validated'])
        self.assertEqual([p['selected_mode'] for p in result['profiles']],
                         ['baseline','extra-poll'])
        for profile in result['profiles']:
            self.assertEqual(profile['observed_guest_ticks'],900)
            self.assertEqual(len(profile['windows']),6)
            self.assertFalse(profile['exact_release_tick_timestamps_observed'])
            self.assertFalse(
                profile['exact_libnx_service_ack_arrival_timestamps_observed'])
            self.assertLessEqual(
                profile['release_bearing_ticks_conservative_lower_bound'],
                profile['release_bearing_ticks_conservative_upper_bound'])
            self.assertLessEqual(
                profile['release_bearing_ticks_conservative_upper_bound'],900)
            self.assertEqual(
                sum(w['observed_pages_released'] for w in profile['windows']),
                profile['observed_guest_released_pages'])
            for window in profile['windows']:
                self.assertEqual(len(window['groups']),3)
                self.assertEqual(
                    sum(g['ticks_in_group'] for g in window['groups']),150)
                self.assertEqual(
                    sum(g['released_pages'] for g in window['groups']),
                    window['observed_pages_released'])
                self.assertGreaterEqual(
                    window['release_bearing_ticks_upper_bound'],
                    window['release_bearing_ticks_lower_bound'])
        for key in ('exact_release_tick_timestamps_observed',
                    'libnx_service_policy_identified',
                    'guest_frame_exposure_matched_verified',
                    'guest_wall_clock_latency_verified',
                    'physical_switch_audio_verified',
                    'original_arcade_audio_verified',
                    'causal_audio_improvement_verified'):
            self.assertIs(result[key],False)

    def test_compatibility_with_independent_900_tick_mode_witnesses(self):
        for mode,enabled,variation in (('baseline',False,0),
                                       ('extra-poll',True,1)):
            with self.subTest(mode=mode):
                report=complete(enabled,variation)
                profile=audit.guest_ack_profile(report,mode)
                self.assertEqual(profile['observed_guest_released_pages'],
                                 report['audout_blocks_released'])
                self.assertEqual(profile['observed_full_pre_poll_recovery_ticks'],
                                 report['full_recovered_before_admission_ticks'])
                self.assertEqual(
                    sum(w['optional_mid_poll']['poll_calls']
                        for w in profile['windows']),
                    report['guest_mid_batch_extra_poll_calls'])
                self.assertEqual(
                    sum(w['optional_mid_poll']['released_pages']
                        for w in profile['windows']),
                    report['guest_mid_batch_extra_poll_released_pages'])

    def test_bound_is_conservative_not_exact_event_timestamps(self):
        for steps,pages,recovered,expect in (
                (10,0,0,(0,0)),
                (10,1,0,(1,1)),
                (10,2,0,(1,2)),
                (10,2,2,(2,2)),
                (10,7,1,(4,7)),
                (1,2,1,(1,1)),
                (0,0,0,(0,0))):
            result=audit.bounded_group(steps,pages,recovered)
            self.assertEqual((
                result['release_bearing_ticks_lower_bound'],
                result['release_bearing_ticks_upper_bound']),expect)
            self.assertIs(result['exact_release_tick_numbers_observed'],False)
        # Counts alone cannot determine which two of the ten ticks carried
        # two distinct release events: the counterexample has a wide bound.
        self.assertLess(
            audit.bounded_group(10,2,0)['release_bearing_ticks_lower_bound'],
            audit.bounded_group(10,2,0)['release_bearing_ticks_upper_bound'])

    def test_reject_impossible_events_recoveries_and_types(self):
        for a,b,c in ((0,1,0),(1,3,0),(1,1,2),(2,0,1),
                      (1,2,2),(-1,0,0),(True,0,0),(2,False,0),
                      (2,1,1.0),(2,1,-1),(901,0,0)):
            with self.subTest(args=(a,b,c)),self.assertRaises(ValueError):
                audit.bounded_group(a,b,c)
        forged=complete(True,1)
        forged['checkpoint_release_position_intervals'][0][
            'single_frame_released_pages']=False
        with self.assertRaises(ValueError):
            audit.guest_ack_profile(forged,'extra-poll')
        forged=complete(True,1)
        forged['checkpoint_guest_mid_batch_extra_poll_intervals'][0][
            'poll_calls']=999
        with self.assertRaises(ValueError):
            audit.guest_ack_profile(forged,'extra-poll')

    def test_reject_forged_or_swapped_nro_bound_inputs(self):
        with self.assertRaises(ValueError):
            audit.make_report(self.a,self.bb,self.b,self.aa,
                              self.base_nro,self.extra_nro)
        original=self.bb.read_bytes()
        forged=json.loads(original)
        forged['guest_report_sha256']='0'*64
        self.bb.write_text(json.dumps(forged)+'\n')
        try:
            with self.assertRaises(ValueError):
                self.analyze_ack()
        finally:
            self.bb.write_bytes(original)
        self.base_nro.write_bytes(self.base_nro.read_bytes()+b'X')
        with self.assertRaises(ValueError):
            self.analyze_ack()

    def test_cli_exclusive_output_no_rewrite_on_inconclusive(self):
        target=Path(self.temp.name)/'guest-ack-observability.json'
        args=[
            '--baseline-report',str(self.a),
            '--baseline-binding',str(self.aa),
            '--baseline-nro',str(self.base_nro),
            '--experimental-report',str(self.b),
            '--experimental-binding',str(self.bb),
            '--experimental-nro',str(self.extra_nro),
            '--out',str(target),
        ]
        with redirect_stdout(StringIO()):
            self.assertEqual(audit.main(args),0)
        saved=target.read_bytes()
        self.assertEqual(json.loads(saved),self.analyze_ack())
        with redirect_stdout(StringIO()) as trace:
            self.assertEqual(audit.main(args),1)
        self.assertIn('INCONCLUSIVE_GUEST_ACK_OBSERVABILITY',
                      trace.getvalue())
        self.assertEqual(target.read_bytes(),saved)


if __name__=='__main__':
    unittest.main()
