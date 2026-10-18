"""ROM-free integration smoke: compile and execute the actual Switch
training-room C simulation/SFX on a native host and capture RGB frames.

This is real execution of portable game code, NOT Nintendo Switch emulation
or verification of the NRO's GPU and hardware audio implementation.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest

from tools import dino_host_preview as host

@unittest.skipUnless(shutil.which('gcc'), 'GCC required for native ROM-free gameplay smoke')
class HostGameExecutionTests(unittest.TestCase):
    def test_demo_executes_180_native_c_ticks_with_genuine_audio_state(self):
        report=host.headless(180)
        self.assertEqual((report['schema'],report['ticks']),
                         ('dino-native-host-smoke-v1',180))
        self.assertEqual(report['runtime'],'native_host_not_switch_emulator')
        self.assertEqual(report['player_x'],230)
        self.assertGreaterEqual(report['successful_hits'],3)
        self.assertTrue(report['sparring'])
        self.assertEqual(len(report['frame_rgb_sha256']),64)
        self.assertEqual(len(report['pcm_fnv64']),16)
        self.assertFalse(report['switch_gpu_verified'])
        self.assertFalse(report['switch_audio_verified'])
        self.assertFalse(report['switch_emulator_verified'])

    def test_180_tick_frame_and_pcm_checksums_are_repeatable(self):
        first=host.headless(180)
        second=host.headless(180)
        self.assertEqual(first,second)

    def test_real_rgb_buffer_contains_actor_dummy_and_depth_lanes(self):
        engine=host.HostArena()
        try:
            pixels=engine.render_rgb()
            self.assertEqual(len(pixels),384*224*3)
            def pixel(x,y):
                i=(y*384+x)*3
                return tuple(pixels[i:i+3])
            self.assertEqual(pixel(0,0),(30,61,70))
            self.assertEqual(pixel(0,80),(86,108,94))
            self.assertEqual(pixel(0,151),(62,83,74))
            self.assertEqual(pixel(90,126),(62,180,208))
            self.assertEqual(pixel(250,127),(190,126,74))
            self.assertNotEqual(engine.ppm()[:2],b'P3')
            self.assertTrue(engine.ppm().startswith(b'P6\n384 224\n255\n'))
        finally:
            engine.close()

    def test_native_gameplay_steps_and_three_hit_finisher(self):
        game=host.HostArena()
        try:
            for _ in range(70):game.step(host.RIGHT)
            self.assertEqual(game.status().x,230)
            for i in range(3):
                game.step(0,host.ATTACK)
                if i<2:
                    for _ in range(14):game.step()
            s=game.status()
            self.assertEqual((s.combo,s.enemy_hp,s.successful_hits),
                             (3,0,3))
            self.assertEqual(s.enemy_pose,5)
            self.assertEqual(s.ticks,101)
        finally:
            game.close()

    def test_sparring_chase_player_damage_and_jump_are_native_c(self):
        game=host.HostArena()
        try:
            game.step(0,host.SPAR)
            self.assertTrue(game.status().sparring)
            self.assertEqual(game.status().dummy_x,249)
            for _ in range(65):game.step()
            self.assertLess(game.status().dummy_x,220)
            self.assertEqual(game.status().ticks,66)
            game.step(0,host.JUMP)
            self.assertGreater(game.status().z,0)
        finally:
            game.close()

    def test_reset_restores_visual_state_and_audio_digest(self):
        game=host.HostArena()
        try:
            untouched=game.render_rgb()
            start=game.status()
            game.step(host.RIGHT,host.ATTACK)
            self.assertNotEqual(game.status().pcm_digest,start.pcm_digest)
            game.reset()
            self.assertEqual(game.status().ticks,0)
            self.assertEqual(game.status().x,90)
            self.assertEqual(game.status().pcm_digest,start.pcm_digest)
            self.assertEqual(game.render_rgb(),untouched)
        finally:
            game.close()

    def test_explicit_ppm_frame_is_written_once_without_overwrite(self):
        with tempfile.TemporaryDirectory(prefix='dino-host-frame-') as td:
            path=Path(td)/'private-original-preview.ppm'
            state=host.headless(150,path)
            frame=path.read_bytes()
            self.assertTrue(frame.startswith(b'P6\n384 224\n255\n'))
            header=b'P6\n384 224\n255\n'
            self.assertEqual(len(frame),len(header)+384*224*3)
            self.assertEqual(hashlib.sha256(frame[len(header):]).hexdigest(),
                             state['frame_rgb_sha256'])
            with self.assertRaises(FileExistsError):
                host.headless(150,path)
            self.assertEqual(frame,path.read_bytes())

    def test_invalid_run_lengths_fail_before_compiling_game(self):
        for count in (0,-1,3601,1.5):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    host.headless(count)

    def test_keyboard_edges_match_training_controls(self):
        keys=host.KeyboardInput()
        self.assertEqual(keys.tick_input(),(0,0))
        keys.key_down('Right')
        keys.key_down('Up')
        keys.key_down('j')
        keys.key_down('j')  # OS key-repeat does not double fire
        self.assertEqual(keys.tick_input(),
                         (host.RIGHT|host.UP,host.ATTACK))
        self.assertEqual(keys.tick_input(),(host.RIGHT|host.UP,0))
        keys.key_up('J')
        keys.key_down('j')
        self.assertEqual(keys.tick_input(),
                         (host.RIGHT|host.UP,host.ATTACK))
        keys.key_up('Right')
        keys.key_up('Up')
        keys.key_down('r')
        keys.key_down('r')
        self.assertTrue(keys.reset_requested)
        keys.key_down('Escape')
        self.assertTrue(keys.exit_requested)

    @unittest.skipUnless(os.environ.get('DISPLAY'),
                         'Actual Tk pixel and key smoke needs X11/Xvfb')
    def test_real_tk_widget_pixel_and_key_events_without_emulator_claim(self):
        # This executes genuine tkinter Canvas + PhotoImage + X11 key events,
        # not a fake root or a Nintendo Switch emulator.
        try:
            import tkinter
        except ImportError:
            self.skipTest('Tkinter not installed on this host')
        result=host.gui_smoke()
        self.assertEqual(result['schema'],'dino-native-gui-smoke-v1')
        self.assertEqual(result['runtime'],'tk_desktop_not_switch_emulator')
        self.assertEqual((result['ticks'],result['player_x']),(9,98))
        self.assertEqual(result['image_dimensions'],[768,448])
        self.assertTrue(result['tk_image_rendered'])
        self.assertTrue(result['edge_input_verified'])
        self.assertTrue(result['held_input_verified'])
        self.assertFalse(result['switch_emulator_verified'])
        self.assertFalse(result['switch_gpu_verified'])
        self.assertFalse(result['switch_audio_verified'])

    def test_fixed_60hz_scheduler_preserves_fractional_tick_budget(self):
        clock=host.FixedTickScheduler()
        self.assertEqual(clock.advance(0),0)
        self.assertEqual(clock.advance(16_000_000),0)
        self.assertEqual(clock.advance(666_667),1)
        self.assertEqual(clock.advance(83_333_333),5)
        self.assertEqual(clock.advance(0),0)
        self.assertEqual(clock.dropped_ticks,0)

    def test_fixed_scheduler_clamps_huge_delay_without_runaway_catchup(self):
        clock=host.FixedTickScheduler()
        self.assertEqual(clock.advance(5_000_000_000),8)
        self.assertEqual(clock.dropped_ticks,7)
        self.assertEqual(clock.carry,0)
        self.assertEqual(clock.advance(-123),0)
        self.assertEqual(clock.advance(16_666_667),1)

    def test_cli_machine_report_does_not_claim_emulator(self):
        text=io.StringIO()
        with contextlib.redirect_stdout(text):
            code=host.main(['--headless','--ticks','30'])
        self.assertEqual(code,0)
        result=json.loads(text.getvalue())
        self.assertEqual(result['ticks'],30)
        self.assertFalse(result['switch_emulator_verified'])
        self.assertNotIn('/mnt',text.getvalue())
        self.assertNotIn('prod.keys',text.getvalue())

if __name__=='__main__':
    unittest.main()
