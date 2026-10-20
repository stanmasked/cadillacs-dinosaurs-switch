"""Stage 259 synthetic checks: sampled negative X11 to positive guest-frame."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

from tools import nexium_host_live_counter_pixel as pixel
from tools import verify_nexium_host_x11_transition as transition
from test_nexium_host_keydown_bracket import StandaloneBracketVerifierTests


NEG={
    'caption':(11,18,29),'impact':(62,83,74),
    'player':(62,180,208),'ground':(62,83,74)
}


class TwoPhaseX11Sampler:
    def __init__(self,window):
        if window!='987':raise ValueError('fake-only X11 window')
        self.count=0
    def sample(self):
        self.count+=1
        time.sleep(.001)
        return (dict(NEG) if self.count<=2 else
                {**pixel.EXPECTED,'frame_token_u16':2250})
    def close(self):pass


class ImmediatePositiveX11Sampler(TwoPhaseX11Sampler):
    def sample(self):
        self.count+=1
        return (dict(NEG) if self.count==1 else
                {**pixel.EXPECTED,'frame_token_u16':2250})


class HostTransitionSamplerTests(unittest.TestCase):
    def test_two_successive_x11_samples_bracket_transition(self):
        w=pixel.CounterWindowWatcher('987',sampler_factory=TwoPhaseX11Sampler,
                                     seconds=.2)
        self.assertTrue(w.start())
        w.begin_keydown_command()
        w.trigger()
        self.assertEqual(w.finish()['status'],pixel.STATUS)
        p=w.transition_bracket_result()
        self.assertEqual(p['status'],transition.RAW_SUCCESS)
        self.assertEqual(p['post_trigger_absent_x11_images'],1)
        self.assertEqual(p['x11_positive_frame_token_u16'],2250)
        self.assertLessEqual(p['last_negative_xgetimage_end_offset_us'],
                             p['first_positive_xgetimage_begin_offset_us'])
        self.assertEqual(p['last_negative_x11_pixel_rgb']['caption'],list(NEG['caption']))
        self.assertFalse(p['first_visible_frame_onset_verified'])
        self.assertFalse(p['precise_input_to_display_latency_verified'])

    def test_first_post_command_x11_positive_is_inconclusive(self):
        w=pixel.CounterWindowWatcher('987',sampler_factory=ImmediatePositiveX11Sampler,
                                     seconds=.2)
        self.assertTrue(w.start())
        w.begin_keydown_command()
        w.trigger()
        self.assertEqual(w.finish()['status'],pixel.STATUS)
        self.assertEqual(w.transition_bracket_result()['status'],
                         'INCONCLUSIVE_NO_POST_TRIGGER_ABSENT_SAMPLE')

    def test_empty_transition_report_has_no_latency_claim(self):
        p=pixel.empty_transition_bracket_result()
        self.assertFalse(p['host_x11_transition_sample_bracket_observed'])
        self.assertIsNone(p['x11_positive_frame_token_u16'])
        self.assertFalse(p['physical_display_verified'])


class NativeBoundTransitionVerifierTests(unittest.TestCase):
    def setUp(self):
        fixture=StandaloneBracketVerifierTests(
            'test_consistent_host_bounds_and_guest_frame_accepted')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root=fixture.root
        self.guests=fixture.guests
        self.nros=fixture.nros
        self.mode='baseline'
        self.good={
            'schema':transition.SCHEMA,
            'status':transition.RAW_SUCCESS,
            'post_trigger_absent_x11_images':2,
            'host_x11_transition_sample_bracket_observed':True,
            'x11_positive_frame_token_u16':2250,
            'last_negative_x11_pixel_rgb':{k:list(v) for k,v in NEG.items()},
            'last_negative_xgetimage_begin_offset_us':6000,
            'last_negative_xgetimage_end_offset_us':6100,
            'first_positive_xgetimage_begin_offset_us':6500,
            'first_positive_xgetimage_end_offset_us':6770,
            'clock_domain':'HOST_MONOTONIC_ONLY',
            'first_visible_frame_onset_verified':False,
            'precise_input_to_display_latency_verified':False,
            'guest_input_delivery_timestamp_verified':False,
            'physical_controller_verified':False,
            'physical_display_verified':False,
            'gpu_scanout_timestamp_verified':False,
            'cross_mode_causal_comparison_verified':False,
        }
        for g in self.guests.values():
            (g/'host-x11-transition-bracket-evidence.json').write_text(
                json.dumps(self.good),encoding='ascii')

    def target(self):
        return self.guests[self.mode]/'host-x11-transition-bracket-evidence.json'

    def edit(self,**kwargs):
        p=self.target()
        d=json.loads(p.read_text())
        d.update(kwargs)
        p.write_text(json.dumps(d),encoding='ascii')

    def verify(self):
        return transition.verify(self.guests[self.mode],
                                 self.nros[self.mode],self.mode)

    def test_real_guest_synthetic_source_is_consistent(self):
        p=self.verify()
        self.assertEqual(p['status'],transition.SUCCESS)
        self.assertEqual(p['guest_render_iteration'],2250)
        self.assertEqual(p['conservative_observed_pixel_transition_interval_start_us'],6000)
        self.assertEqual(p['conservative_observed_pixel_transition_interval_end_us'],6770)
        self.assertFalse(p['first_visible_frame_onset_verified'])

    def test_both_native_audio_modes_individually_valid(self):
        self.mode='extra-poll'
        self.assertEqual(self.verify()['status'],transition.SUCCESS)

    def test_no_post_command_negative_sample_fail_closed(self):
        self.edit(post_trigger_absent_x11_images=0)
        with self.assertRaises(ValueError):self.verify()

    def test_negative_sample_not_really_negative_fails(self):
        self.edit(last_negative_x11_pixel_rgb={
            k:list(v) for k,v in pixel.EXPECTED.items()})
        with self.assertRaises(ValueError):self.verify()

    def test_reversed_negative_and_positive_x11_order_fails(self):
        self.edit(last_negative_xgetimage_begin_offset_us=8000)
        with self.assertRaises(ValueError):self.verify()

    def test_positive_window_must_match_stage258_report(self):
        self.edit(first_positive_xgetimage_begin_offset_us=6600)
        with self.assertRaises(ValueError):self.verify()

    def test_guest_frame_token_must_match_x11(self):
        self.edit(x11_positive_frame_token_u16=2251)
        with self.assertRaises(ValueError):self.verify()

    def test_physical_input_or_display_claim_is_refused(self):
        for k in transition.FALSE:
            with self.subTest(flag=k):
                before=self.target().read_text()
                self.edit(**{k:True})
                with self.assertRaises(ValueError):self.verify()
                self.target().write_text(before)

    def test_no_unsupported_guest_mode_swap(self):
        with self.assertRaises(ValueError):
            transition.verify(self.guests['baseline'],self.nros['baseline'],
                              'extra-poll')

    def test_nro_digest_tamper_detected(self):
        p=self.nros['baseline']
        p.write_bytes(p.read_bytes()+b'fake')
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_host_json_keys_rejected(self):
        p=self.target()
        p.write_text(p.read_text().replace(
            '"status":','"status":"FAKE","status":'),encoding='ascii')
        with self.assertRaises(ValueError):self.verify()

    def test_direct_subprocess_cli_with_no_pythonpath(self):
        script=(Path(__file__).resolve().parents[1]/
                'tools/verify_nexium_host_x11_transition.py')
        target=self.root/'transition-output.json'
        env=os.environ.copy();env.pop('PYTHONPATH',None)
        result=subprocess.run(
            [sys.executable,str(script),'--guest-dir',str(self.guests['baseline']),
             '--nro',str(self.nros['baseline']),'--mode','baseline',
             '--out',str(target)],
            cwd=self.root,env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(target.read_text())['status'],transition.SUCCESS)

    def test_inconclusive_cli_stays_honest(self):
        self.target().unlink()
        out=self.root/'inconclusive.json'
        self.assertEqual(transition.main([
            '--guest-dir',str(self.guests['baseline']),
            '--nro',str(self.nros['baseline']),
            '--mode','baseline','--out',str(out)]),0)
        p=json.loads(out.read_text())
        self.assertEqual(p['status'],transition.INCONCLUSIVE)
        self.assertFalse(p['first_visible_frame_onset_verified'])


if __name__=='__main__':
    unittest.main()
