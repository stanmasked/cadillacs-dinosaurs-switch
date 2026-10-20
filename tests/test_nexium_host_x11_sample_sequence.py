"""Stage 261 optional X11 RGB sample sequence and native frame binding tests."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

from tools import nexium_host_live_counter_pixel as pixels
from tools import verify_nexium_host_x11_sample_sequence as sequence
from test_nexium_host_x11_transition import (
    NativeBoundTransitionVerifierTests,TwoPhaseX11Sampler,
    ImmediatePositiveX11Sampler,NEG,
)


class X11SeriesCaptureTests(unittest.TestCase):
    def test_native_sampler_collects_one_negative_and_exact_positive(self):
        w=pixels.CounterWindowWatcher('987',sampler_factory=TwoPhaseX11Sampler,
                                      seconds=0.2)
        self.assertTrue(w.start())
        w.begin_keydown_command()
        w.trigger()
        self.assertEqual(w.finish()['status'],pixels.STATUS)
        rec=w.sample_sequence_result()
        self.assertEqual(rec['status'],sequence.RAW_SUCCESS)
        self.assertEqual(len(rec['samples']),2)
        self.assertEqual(rec['samples'][0]['four_counter_point_rgb']['caption'],list(NEG['caption']))
        self.assertFalse(rec['samples'][0]['counter_four_pixels_present'])
        self.assertTrue(rec['samples'][1]['counter_four_pixels_present'])
        self.assertEqual(rec['samples'][1]['frame_token_u16'],2250)
        self.assertFalse(rec['precise_first_visible_frame_onset_verified'])
        self.assertNotIn('host_window_id',str(rec))

    def test_immediate_positive_never_fabricates_earlier_negative(self):
        w=pixels.CounterWindowWatcher('987',sampler_factory=ImmediatePositiveX11Sampler,
                                      seconds=0.2)
        self.assertTrue(w.start())
        w.begin_keydown_command()
        w.trigger()
        self.assertEqual(w.finish()['status'],pixels.STATUS)
        rec=w.sample_sequence_result()
        self.assertEqual(rec['status'],'INCONCLUSIVE_NO_ORDERED_X11_SAMPLE_SEQUENCE')
        self.assertFalse(rec['ordered_host_x11_samples_observed'])

    def test_explicit_empty_series_is_honestly_inconclusive(self):
        rec=pixels.empty_sample_sequence_result()
        self.assertEqual(rec['samples'],[])
        self.assertFalse(rec['physical_display_verified'])
        self.assertIsNone(rec['matching_positive_frame_token_u16'])


class RawBoundedSequenceTests(unittest.TestCase):
    def setUp(self):
        fixture=NativeBoundTransitionVerifierTests(
            'test_real_guest_synthetic_source_is_consistent')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root=fixture.root
        self.guests=fixture.guests
        self.nros=fixture.nros
        self.mode='baseline'
        for mode,guest in self.guests.items():
            samples=[
                {'index':1,'capture_begin_offset_us':5000,
                 'capture_end_offset_us':5100,'counter_four_pixels_present':False,
                 'four_counter_point_rgb':{k:list(v) for k,v in NEG.items()},
                 'frame_token_u16':None},
                {'index':2,'capture_begin_offset_us':6000,
                 'capture_end_offset_us':6100,'counter_four_pixels_present':False,
                 'four_counter_point_rgb':{k:list(v) for k,v in NEG.items()},
                 'frame_token_u16':None},
                {'index':3,'capture_begin_offset_us':6500,
                 'capture_end_offset_us':6770,'counter_four_pixels_present':True,
                 'four_counter_point_rgb':{
                     k:list(v) for k,v in pixels.EXPECTED.items()},
                 'frame_token_u16':2250},
            ]
            (guest/'host-x11-sample-sequence-evidence.json').write_text(
                json.dumps({
                    'schema':sequence.SCHEMA,'status':sequence.RAW_SUCCESS,
                    'ordered_host_x11_samples_observed':True,
                    'post_command_negative_samples':2,
                    'matching_positive_frame_token_u16':2250,
                    'samples':samples,
                    'clock_domain':'HOST_MONOTONIC_ONLY',
                    **{k:False for k in sequence.FALSE_FLAGS},
                }),encoding='ascii')
            # Stage 259 standalone fixture has only one last negative
            # sample. Change it to count the two genuine saved records.
            transition=guest/'host-x11-transition-bracket-evidence.json'
            saved=json.loads(transition.read_text())
            saved['post_trigger_absent_x11_images']=2
            transition.write_text(json.dumps(saved),encoding='ascii')

    def path(self):
        return self.guests[self.mode]/'host-x11-sample-sequence-evidence.json'

    def mutate(self,change):
        s=json.loads(self.path().read_text())
        change(s)
        self.path().write_text(json.dumps(s),encoding='ascii')

    def verify(self):
        return sequence.verify(self.guests[self.mode],self.nros[self.mode],self.mode)

    def test_correct_all_three_x11_samples_bind_to_native_guest(self):
        p=self.verify()
        self.assertEqual(p['status'],sequence.SUCCESS)
        self.assertEqual(p['negative_x11_samples'],2)
        self.assertEqual(p['total_post_command_samples'],3)
        self.assertEqual(p['guest_submitted_render_iteration'],2250)
        self.assertFalse(p['exact_first_visible_frame_onset_verified'])

    def test_extra_poll_selected_nro_mode_independently_passes(self):
        self.mode='extra-poll'
        self.assertEqual(self.verify()['status'],sequence.SUCCESS)

    def test_missing_intermediate_x11_image_rejected(self):
        self.mutate(lambda s:s['samples'].pop(0))
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_or_out_of_order_index_rejected(self):
        self.mutate(lambda s:s['samples'][1].update(index=1))
        with self.assertRaises(ValueError):self.verify()

    def test_overlapping_host_xgetimage_calls_rejected(self):
        self.mutate(lambda s:s['samples'][1].update(capture_begin_offset_us=5001))
        with self.assertRaises(ValueError):self.verify()

    def test_negative_x11_pixel_claiming_four_point_counter_rejected(self):
        self.mutate(lambda s:s['samples'][0].update(
            four_counter_point_rgb={k:list(v) for k,v in pixels.EXPECTED.items()}))
        with self.assertRaises(ValueError):self.verify()

    def test_positive_x11_pixel_color_forgery_rejected(self):
        self.mutate(lambda s:s['samples'][2].update(
            four_counter_point_rgb={k:list(v) for k,v in NEG.items()}))
        with self.assertRaises(ValueError):self.verify()

    def test_positive_native_frame_token_forgery_rejected(self):
        self.mutate(lambda s:s['samples'][2].update(frame_token_u16=900))
        with self.assertRaises(ValueError):self.verify()

    def test_last_negative_sample_must_match_stage260_raw(self):
        self.mutate(lambda s:s['samples'][1].update(capture_end_offset_us=6099))
        with self.assertRaises(ValueError):self.verify()

    def test_total_guest_frame_mode_swap_rejected(self):
        with self.assertRaises(ValueError):
            sequence.verify(self.guests['extra-poll'],self.nros['extra-poll'],'baseline')

    def test_mutated_real_guest_nro_rejected(self):
        p=self.nros['baseline']
        p.write_bytes(p.read_bytes()+b'changed')
        with self.assertRaises(ValueError):self.verify()

    def test_false_first_frame_onset_claim_refused(self):
        self.mutate(lambda s:s.update(precise_first_visible_frame_onset_verified=True))
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_json_key_rejected(self):
        p=self.path()
        p.write_text(p.read_text().replace('"status":',
                                            '"status":"FORGED","status":'))
        with self.assertRaises(ValueError):self.verify()

    def test_independent_cli_without_pythonpath(self):
        tool=(Path(__file__).resolve().parents[1]/
              'tools/verify_nexium_host_x11_sample_sequence.py')
        outfile=self.root/'series.json'
        env=os.environ.copy()
        env.pop('PYTHONPATH',None)
        call=subprocess.run([sys.executable,str(tool),
            '--guest-dir',str(self.guests['baseline']),
            '--nro',str(self.nros['baseline']),
            '--mode','baseline','--out',str(outfile)],
            cwd=self.root,env=env,capture_output=True,text=True,timeout=10)
        self.assertEqual(call.returncode,0,call.stdout+call.stderr)
        self.assertEqual(json.loads(outfile.read_text())['status'],sequence.SUCCESS)

    def test_optional_cli_missing_trace_outputs_inconclusive(self):
        self.path().unlink()
        out=self.root/'missing-series.json'
        self.assertEqual(sequence.main([
            '--guest-dir',str(self.guests['baseline']),
            '--nro',str(self.nros['baseline']),
            '--mode','baseline','--out',str(out)]),0)
        report=json.loads(out.read_text())
        self.assertEqual(report['status'],sequence.INCONCLUSIVE)
        self.assertFalse(report['physical_display_verified'])


if __name__=='__main__':
    unittest.main()
