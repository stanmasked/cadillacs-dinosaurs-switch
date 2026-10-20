"""Stage 251 strict paired X11 guest verifier: synthetic parser fixtures ONLY."""
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools import verify_nexium_host_counter_window_paired as paired

class RequiredHostWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.guests={}
        self.nros={}
        for mode,seed in [('baseline',1),('extra-poll',2)]:
            guest=self.root/mode
            guest.mkdir()
            nro=self.root/(mode+'.nro')
            data=bytearray(100201)
            data[16:20]=b'NRO0'
            data[-1]=seed
            nro.write_bytes(data)
            sha=hashlib.sha256(data).hexdigest()
            (guest/'metadata.txt').write_text(
                'scope=REAL_NE_XIUM_GUEST_CI_NO_NINTENDO_ROM\nnro_sha256='+sha+'\n')
            (guest/'result.txt').write_text('PASS: actual NeXium NRO guest 180-tick replay')
            enabled=(mode=='extra-poll')
            calls=6 if enabled else 0
            stress={'simulation_ticks':900,'pcm_generated_ticks':900,
                    'guest_mid_batch_extra_poll_enabled':enabled,
                    'guest_mid_batch_extra_poll_calls':calls,
                    'guest_mid_batch_extra_poll_released_pages':0}
            raw=(json.dumps(stress,sort_keys=True)+'\n').encode('ascii')
            (guest/'guest-audio-stress-evidence.json').write_bytes(raw)
            binding={
                'schema':'dino-nexium-guest-audio-mode-binding-v1',
                'status':'SELECTED_AUDIO_MODE_WITNESSED_BY_GUEST',
                'selected_mode':mode,
                'guest_nro_sha256':sha,
                'guest_report_sha256':hashlib.sha256(raw).hexdigest(),
                'guest_poll_enabled':enabled,
                'guest_poll_calls':calls,
                'guest_poll_released_pages':0,
                'guest_simulation_ticks':900,
                'audio_latency_verified':False,
                'causal_audio_improvement_verified':False,
                'physical_switch_audio_verified':False,
            }
            (guest/'guest-audio-mode-binding.json').write_text(json.dumps(binding))
            host={
                'schema':'dino-nexium-host-counter-frame-v1',
                'status':paired.STATUS,
                'host_x11_window_counter_pixels_observed':True,
                'counter_transition_baseline_observed':True,
                'same_x11_image_four_pixel_match':True,
                'frames_sampled':7,'diagnostic_code':'',
                'native_guest_counter_event_bound':False,
                'host_window_pixel_latency_verified':False,
                'physical_display_verified':False,
                'physical_controller_verified':False,
                'original_arcade_graphics_verified':False,
            }
            (guest/'host-counter-window-evidence.json').write_text(json.dumps(host))
            (guest/'host-live-zr-attempt.json').write_text(json.dumps({
                'schema':'dino-nexium-host-live-counter-attempt-v1',
                'status':'HOST_LIVE_SCENE_ZR_ATTEMPT_AFTER_REAL_Y_X',
                'guest_live_counter_verified':False}))
            live={k:'0' for k in paired.LIVE_COLUMNS}
            live.update(event='LIVE_HID_COUNTER',tick='120',player_x='90',
                        enemy_x='134',pre_windup='9',hid_edge='1',pcm_nonzero='1')
            with (guest/'guest-live-counter-hid.csv').open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=paired.LIVE_COLUMNS)
                writer.writeheader();writer.writerow(live)
            fb={k:'0' for k in paired.PIXEL_COLUMNS}
            fb.update(event='SUBMITTED_COUNTER_FRAME',render_iteration='2250',
                      arena_tick='148',feedback_ttl='6',impact_ttl='6',**paired.PIXELS)
            with (guest/'guest-live-counter-framebuffer.csv').open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=paired.PIXEL_COLUMNS)
                writer.writeheader();writer.writerow(fb)
            (guest/'guest-live-counter-framebuffer-evidence.json').write_text(json.dumps({
                'status':'GUEST_SUBMITTED_COUNTER_FRAMEBUFFER_PIXELS_WITNESSED',
                'native_guest_framebuffer_pixels_verified':True,
                'host_emulator_screen_pixel_verified':False,
                'render_iteration':2250,'arena_tick':148,
                'counter_caption_feedback_ttl':6,'enemy_impact_flash_ttl':6}))
            self.guests[mode]=guest
            self.nros[mode]=nro

    def verify(self):
        return paired.verify(self.guests['baseline'],self.guests['extra-poll'],
                             self.nros['baseline'],self.nros['extra-poll'])

    def mutate(self,**updates):
        path=self.guests['baseline']/'host-counter-window-evidence.json'
        data=json.loads(path.read_text())
        data.update(updates)
        path.write_text(json.dumps(data))

    def test_both_nro_bound_host_pixel_windows_accepted(self):
        report=self.verify()
        self.assertTrue(report['both_nro_bound_host_x11_counter_pixels_verified'])
        self.assertFalse(report['physical_switch_display_verified'])
        self.assertFalse(report['exact_guest_frame_to_host_sample_identity_verified'])

    def test_missing_host_report_rejected(self):
        (self.guests['extra-poll']/'host-counter-window-evidence.json').unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_status_baseline_and_single_frame_fail_closed(self):
        for key,value in [('status','INCONCLUSIVE_NO_HOST_WINDOW_COUNTER_FRAME'),
                          ('host_x11_window_counter_pixels_observed',False),
                          ('same_x11_image_four_pixel_match',False),
                          ('counter_transition_baseline_observed',False),
                          ('diagnostic_code','PIXELS_NOT_OBSERVED')]:
            with self.subTest(field=key):
                path=self.guests['baseline']/'host-counter-window-evidence.json'
                old=path.read_text()
                self.mutate(**{key:value})
                with self.assertRaises(ValueError):self.verify()
                path.write_text(old)

    def test_no_invented_physical_or_latency_proof(self):
        for key in ('native_guest_counter_event_bound',
                    'host_window_pixel_latency_verified','physical_display_verified',
                    'physical_controller_verified','original_arcade_graphics_verified'):
            with self.subTest(field=key):
                path=self.guests['baseline']/'host-counter-window-evidence.json'
                old=path.read_text()
                self.mutate(**{key:True})
                with self.assertRaises(ValueError):self.verify()
                path.write_text(old)

    def test_strict_real_sample_count(self):
        for value in [0,1,201,True,'9',2.5]:
            with self.subTest(sample=value):
                path=self.guests['baseline']/'host-counter-window-evidence.json'
                old=path.read_text()
                self.mutate(frames_sampled=value)
                with self.assertRaises(ValueError):self.verify()
                path.write_text(old)

    def test_duplicate_json_fields_rejected(self):
        path=self.guests['baseline']/'host-counter-window-evidence.json'
        path.write_text(path.read_text().replace(
            '"status":','"status": "FAKE", "status":'))
        with self.assertRaises(ValueError):self.verify()

    def test_wrong_native_guest_pixel_rejected(self):
        path=self.guests['baseline']/'guest-live-counter-framebuffer.csv'
        path.write_text(path.read_text().replace('FFC9EB5B','FFFFFFFF'))
        with self.assertRaises(ValueError):self.verify()

    def test_complete_guest_and_matching_nro_mode_swap_rejected(self):
        # Older verifier incorrectly accepted a perfect baseline↔extra swap.
        with self.assertRaises(ValueError):
            paired.verify(self.guests['extra-poll'],self.guests['baseline'],
                          self.nros['extra-poll'],self.nros['baseline'])

    def test_selected_mode_field_cannot_be_forged(self):
        path=self.guests['baseline']/'guest-audio-mode-binding.json'
        binding=json.loads(path.read_text())
        binding['selected_mode']='extra-poll'
        path.write_text(json.dumps(binding))
        with self.assertRaises(ValueError):self.verify()

    def test_mode_stress_hash_tamper_rejected(self):
        path=self.guests['extra-poll']/'guest-audio-stress-evidence.json'
        report=json.loads(path.read_text())
        report['guest_mid_batch_extra_poll_calls']=0
        path.write_text(json.dumps(report))
        with self.assertRaises(ValueError):self.verify()

    def test_mode_900_tick_guest_report_required(self):
        path=self.guests['baseline']/'guest-audio-stress-evidence.json'
        path.unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_guest_poll_mode_not_a_self_reported_label_only(self):
        path=self.guests['extra-poll']/'guest-audio-mode-binding.json'
        binding=json.loads(path.read_text())
        binding['guest_poll_enabled']=False
        path.write_text(json.dumps(binding))
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_raw_stress_report_key_rejected(self):
        path=self.guests['baseline']/'guest-audio-stress-evidence.json'
        raw=path.read_text().replace(
            '"simulation_ticks":','"simulation_ticks": 900, "simulation_ticks":')
        path.write_text(raw)
        with self.assertRaises(ValueError):self.verify()

    def test_swapped_mode_nro_rejected(self):
        with self.assertRaises(ValueError):
            paired.verify(self.guests['baseline'],self.guests['extra-poll'],
                          self.nros['extra-poll'],self.nros['baseline'])

    def test_forged_guest_hid_counter_rejected(self):
        path=self.guests['baseline']/'guest-live-counter-hid.csv'
        path.write_text(path.read_text().replace('LIVE_HID_COUNTER','FORGED_COUNTER'))
        with self.assertRaises(ValueError):self.verify()

    def test_same_nro_in_both_modes_rejected(self):
        self.nros['extra-poll'].write_bytes(self.nros['baseline'].read_bytes())
        path=self.guests['extra-poll']/'metadata.txt'
        path.write_text('scope=REAL_NE_XIUM_GUEST_CI_NO_NINTENDO_ROM\nnro_sha256='+
                        hashlib.sha256(self.nros['baseline'].read_bytes()).hexdigest()+'\n')
        with self.assertRaises(ValueError):self.verify()

    def test_symlink_host_proof_rejected(self):
        path=self.guests['baseline']/'host-counter-window-evidence.json'
        contents=path.read_text()
        path.unlink()
        target=self.root/'external.json'
        target.write_text(contents)
        path.symlink_to(target)
        with self.assertRaises(ValueError):self.verify()

if __name__=='__main__':
    unittest.main()
