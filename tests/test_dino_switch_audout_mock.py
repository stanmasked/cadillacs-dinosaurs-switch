"""Compile the unchanged production libnx adapter against host audout mocks.

No commercial ROM, audio samples or device are opened. Deterministic
release credits are a C test-double stimulus, NOT speaker timing.
"""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class Diagnostics(ctypes.Structure):
    _fields_=[
        ('simulated_ticks',ctypes.c_uint32),
        ('audio_errors',ctypes.c_uint32),
        ('pending',ctypes.c_uint32),
        ('submitted',ctypes.c_uint32),
        ('released',ctypes.c_uint32),
        ('skipped',ctypes.c_uint32),
        ('active',ctypes.c_uint8),
        ('queue_valid',ctypes.c_uint8),
        ('full_queue_skips',ctypes.c_uint32),
        ('pre_poll_full_steps',ctypes.c_uint32),
        ('pre_poll_recovered_steps',ctypes.c_uint32),
        ('inactive_backend_skips',ctypes.c_uint32),
        ('unexpected_slot_skips',ctypes.c_uint32),
        ('max_consecutive_skips',ctypes.c_uint32),
    ]


@unittest.skipUnless(shutil.which('gcc'), 'Host GCC needed for adapter mock')
class ProductionAudioAdapterMockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dino-audout-host-double-')
        lib=Path(cls.tmp.name)/'libaudoutmock.so'
        sources=[
            'source/dino_switch_sound.c','source/dino_audio_queue.c',
            'source/dino_sfx.c','source/dino_pcm_witness.c',
            'tests/mocks/mock_audout.c',
        ]
        cmd=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-DDINO_EMULATOR_SELFTEST',
             '-DDINO_AUDIO_EXPERIMENT_MID_BATCH_POLL',
             '-fPIC','-shared','-Itests/mocks','-Isource',
             *sources,'-o',str(lib)]
        comp=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        if comp.returncode:
            raise AssertionError('Production adapter host build failed: '+
                                 comp.stderr)
        cls.lib=ctypes.CDLL(str(lib))
        cls.lib.dino_switch_sound_open.restype=ctypes.c_bool
        cls.lib.dino_switch_sound_step.argtypes=[ctypes.c_uint32]
        cls.lib.dino_switch_sound_diagnostics.argtypes=[
            ctypes.POINTER(Diagnostics)]
        cls.lib.dino_switch_sound_pcm_witness.restype=ctypes.c_uint64
        cls.lib.dino_switch_sound_pcm_ticks.restype=ctypes.c_uint32
        for symbol in ('dino_switch_sound_guest_mid_batch_enabled',
                       'dino_switch_sound_guest_mid_batch_calls',
                       'dino_switch_sound_guest_mid_batch_releases'):
            getattr(cls.lib,symbol).restype=ctypes.c_uint32
        cls.lib.dino_switch_sound_guest_mid_batch_poll.restype=None
        cls.lib.mock_audout_grant_releases.argtypes=[ctypes.c_uint32]
        cls.lib.mock_audout_inject_bad_release.argtypes=[ctypes.c_uint32]
        cls.lib.mock_audout_reverse_release_order.argtypes=[
            ctypes.c_uint32]
        for name in (
                'mock_audout_pending','mock_audout_appended',
                'mock_audout_released','mock_audout_integrity_errors',
                'mock_audout_flushes','mock_audout_stops',
                'mock_audout_page_layout_ok',
                'mock_audout_poll_calls','mock_audout_empty_polls'):
            getattr(cls.lib,name).restype=ctypes.c_uint32

    @classmethod
    def tearDownClass(cls):
        cls.lib.dino_switch_sound_close()
        cls.tmp.cleanup()

    def setUp(self):
        self.lib.dino_switch_sound_close()
        self.lib.mock_audout_reset()
        self.assertTrue(self.lib.dino_switch_sound_open())
        self.baseline=self.state()
        self.pcm_baseline=self.lib.dino_switch_sound_pcm_ticks()

    def tearDown(self):
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)
        self.lib.dino_switch_sound_close()

    def state(self):
        out=Diagnostics()
        self.lib.dino_switch_sound_diagnostics(ctypes.byref(out))
        return out

    def delta(self,name):
        return getattr(self.state(),name)-getattr(self.baseline,name)

    def step(self,event=0,releases=0):
        self.lib.mock_audout_grant_releases(releases)
        self.lib.dino_switch_sound_step(event)
        q=self.state()
        self.assertLessEqual(q.pending,2)
        self.assertEqual(self.lib.mock_audout_pending(),q.pending)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)
        return q

    def test_two_page_cap_and_full_queue_drops_but_pcm_clock_runs(self):
        self.step()
        self.step(1<<3)
        self.step(1<<4)
        self.assertEqual(self.delta('submitted'),2)
        self.assertEqual(self.delta('released'),0)
        self.assertEqual(self.delta('skipped'),1)
        self.assertEqual(self.delta('full_queue_skips'),1)
        self.assertEqual(self.delta('simulated_ticks'),3)
        self.assertEqual(self.lib.dino_switch_sound_pcm_ticks()-
                         self.pcm_baseline,3)
        self.assertEqual(self.state().pending,2)
        self.assertEqual(self.lib.mock_audout_flushes(),2)
        self.assertEqual(self.lib.mock_audout_page_layout_ok(),1)

    def test_first_release_admitted_second_without_release_is_dropped(self):
        self.step()
        self.step()
        self.step(releases=1)   # First step of a synthetic two-step frame
        self.step()             # Second step, no external release credit
        self.assertEqual(self.delta('submitted'),3)
        self.assertEqual(self.delta('released'),1)
        self.assertEqual(self.delta('skipped'),1)
        self.assertEqual(self.delta('full_queue_skips'),1)
        self.assertEqual(self.delta('pre_poll_full_steps'),2)
        self.assertEqual(self.delta('pre_poll_recovered_steps'),1)
        self.assertEqual(self.state().pending,2)

    def test_second_ack_allows_both_without_changing_two_page_cap(self):
        self.step()
        self.step()
        self.step(releases=1)
        self.step(releases=1)
        self.assertEqual(self.delta('submitted'),4)
        self.assertEqual(self.delta('released'),2)
        self.assertEqual(self.delta('skipped'),0)
        self.assertEqual(self.delta('pre_poll_recovered_steps'),2)
        self.assertEqual(self.lib.mock_audout_page_layout_ok(),1)

    def test_later_ack_reopens_queue_after_skip_without_backlog(self):
        self.step()
        self.step()
        self.step()
        self.step(releases=1)
        self.assertEqual(self.delta('simulated_ticks'),4)
        self.assertEqual(self.delta('submitted'),3)
        self.assertEqual(self.delta('skipped'),1)
        self.assertEqual(self.delta('released'),1)
        self.assertEqual(self.state().pending,2)

    def test_no_release_across_many_ticks_never_overwrites_inflight_pcm(self):
        for tick in range(40):
            self.step((1<<3) if tick%7==0 else 0)
        self.assertEqual(self.delta('simulated_ticks'),40)
        self.assertEqual(self.delta('submitted'),2)
        self.assertEqual(self.delta('skipped'),38)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)
        self.assertEqual(self.lib.mock_audout_appended(),2)
        self.assertEqual(self.lib.mock_audout_flushes(),2)

    def test_discarded_pcm_still_hashes_identically_to_admitted_audio(self):
        events=[1<<3,0,1<<4,1<<1,1<<2,0,1<<5]
        for i,event in enumerate(events):
            self.step(event,releases=1 if i>=2 else 0)
        fully_admitted_hash=self.lib.dino_switch_sound_pcm_witness()
        self.lib.dino_switch_sound_close()
        self.lib.mock_audout_reset()
        self.assertTrue(self.lib.dino_switch_sound_open())
        for event in events:
            self.step(event)
        dropped_hash=self.lib.dino_switch_sound_pcm_witness()
        self.assertEqual(dropped_hash,fully_admitted_hash)
        self.assertEqual(self.state().skipped,5)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)

    def test_unknown_release_is_rejected_without_reusing_page(self):
        self.step()
        self.step()
        self.lib.mock_audout_inject_bad_release(1)
        error_before=self.state().audio_errors
        self.lib.dino_switch_sound_step(1<<3)
        q=self.state()
        self.assertEqual(q.active,0)
        self.assertEqual(q.audio_errors,error_before+1)
        self.assertEqual(q.pending,0)
        self.assertEqual(self.lib.mock_audout_appended(),2)
        self.assertGreaterEqual(self.lib.mock_audout_stops(),1)

    def test_multi_release_count_is_fail_closed(self):
        self.step()
        self.lib.mock_audout_inject_bad_release(2)
        start=self.state().audio_errors
        self.lib.dino_switch_sound_step(0)
        self.assertEqual(self.state().audio_errors,start+1)
        self.assertEqual(self.state().active,0)
        self.assertEqual(self.lib.mock_audout_appended(),1)

    def test_audout_release_service_failure_is_fail_closed(self):
        self.step()
        self.lib.mock_audout_inject_bad_release(3)
        start=self.state().audio_errors
        self.lib.dino_switch_sound_step(0)
        self.assertEqual(self.state().audio_errors,start+1)
        self.assertEqual(self.state().active,0)
        self.assertEqual(self.lib.mock_audout_appended(),1)


    def test_reverse_order_release_uses_actual_page_identity(self):
        self.step(1<<3)
        self.step(1<<4)
        self.lib.mock_audout_reverse_release_order(1)
        self.step(1<<6,releases=1)  # The most recently submitted page
        self.assertEqual(self.delta('released'),1)
        self.assertEqual(self.state().pending,2)
        self.step(1<<2,releases=1)
        self.assertEqual(self.delta('released'),2)
        self.assertEqual(self.delta('submitted'),4)
        self.assertEqual(self.delta('skipped'),0)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)
        self.assertEqual(self.lib.mock_audout_page_layout_ok(),1)

    def test_reverse_order_mixed_with_fifo_and_stalls_keeps_pages_owned(self):
        for tick in range(120):
            self.lib.mock_audout_reverse_release_order(tick % 2)
            releases=2 if tick % 11 == 0 else (1 if tick % 3 == 0 else 0)
            self.step(1<<(tick%10),releases=releases)
        q=self.state()
        self.assertEqual(self.delta('simulated_ticks'),120)
        self.assertEqual(self.delta('submitted')+
                         self.delta('skipped'),120)
        self.assertEqual(self.delta('submitted')-
                         self.delta('released'),q.pending)
        self.assertEqual(q.audio_errors,self.baseline.audio_errors)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)

    def test_two_distinct_release_acks_drained_before_next_submit(self):
        self.step()
        self.step()
        before_calls=self.lib.mock_audout_poll_calls()
        before_empty=self.lib.mock_audout_empty_polls()
        self.step(releases=2)
        self.assertEqual(self.delta('released'),2)
        self.assertEqual(self.delta('submitted'),3)
        self.assertEqual(self.state().pending,1)
        self.assertEqual(self.lib.mock_audout_poll_calls()-before_calls,3)
        self.assertEqual(self.lib.mock_audout_empty_polls()-before_empty,1)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)

    def test_credit_after_empty_poll_is_consumed_only_next_tick(self):
        self.step()
        self.step()
        self.lib.mock_audout_credit_after_next_empty_poll()
        before=self.lib.mock_audout_poll_calls()
        self.step(1<<3)
        self.assertEqual(self.delta('skipped'),1)
        self.assertEqual(self.delta('released'),0)
        self.assertEqual(self.lib.mock_audout_poll_calls()-before,1)
        self.assertEqual(self.state().pending,2)
        self.step(1<<4)
        self.assertEqual(self.delta('released'),1)
        self.assertEqual(self.delta('submitted'),3)
        self.assertEqual(self.delta('skipped'),1)
        self.assertEqual(self.delta('pre_poll_recovered_steps'),1)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)

    def test_empty_poll_without_release_credit_does_not_create_pcm_slot(self):
        self.step()
        self.step()
        before=self.lib.mock_audout_empty_polls()
        for _ in range(8):
            self.step(1<<3)
        self.assertEqual(self.lib.mock_audout_empty_polls()-before,8)
        self.assertEqual(self.delta('submitted'),2)
        self.assertEqual(self.delta('skipped'),8)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)

    def test_reverse_ack_and_delayed_credit_do_not_change_synth_witness(self):
        events=[1<<3,0,1<<4,1<<1,1<<5,0,1<<9]
        for i,event in enumerate(events):
            self.lib.mock_audout_reverse_release_order(i%2)
            if i==2:
                self.lib.mock_audout_credit_after_next_empty_poll()
            self.step(event,releases=1 if i>3 and i%2==0 else 0)
        hash_with_delays=self.lib.dino_switch_sound_pcm_witness()
        self.lib.dino_switch_sound_close()
        self.lib.mock_audout_reset()
        self.assertTrue(self.lib.dino_switch_sound_open())
        for event in events:
            self.step(event,releases=1)
        self.assertEqual(self.lib.dino_switch_sound_pcm_witness(),
                         hash_with_delays)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)


    def check_fixed_release_schedule(self, schedule):
        """Independent integer queue oracle versus the actual production C."""
        pending=submitted=released=skipped=0
        sound_before=self.lib.dino_switch_sound_pcm_ticks()
        for tick,grant in enumerate(schedule):
            if type(grant) is not int or not 0 <= grant <= 2:
                raise ValueError('bad synthetic release grant')
            returned=min(pending,grant)
            pending-=returned
            released+=returned
            if pending<2:
                pending+=1
                submitted+=1
            else:
                skipped+=1
            out=self.step(1<<(tick%10),releases=grant)
            self.assertEqual(out.pending,pending,'tick '+str(tick))
            self.assertEqual(self.delta('submitted'),submitted)
            self.assertEqual(self.delta('released'),released)
            self.assertEqual(self.delta('skipped'),skipped)
            self.assertEqual(self.delta('simulated_ticks'),tick+1)
            self.assertEqual(self.lib.dino_switch_sound_pcm_ticks()-
                             sound_before,tick+1)
            self.assertEqual(self.lib.mock_audout_flushes(),submitted)
        self.assertEqual(self.lib.mock_audout_page_layout_ok(),1)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)
        return submitted,released,skipped

    def test_900_ticks_uninterrupted_full_queue_preserves_pcm_ownership(self):
        stats=self.check_fixed_release_schedule([0]*900)
        self.assertEqual(stats,(2,0,898))

    def test_900_ticks_first_only_release_every_two_step_frame(self):
        # One external release before first tick, none before second.
        # After startup, loss stays concentrated on second ticks.
        schedule=[0,0]+[1,0]*449
        stats=self.check_fixed_release_schedule(schedule)
        self.assertEqual(stats[0]+stats[2],900)
        self.assertGreater(stats[2],0)
        self.assertEqual(self.state().pending,2)

    def test_900_ticks_triple_step_frames_first_ack_only(self):
        # Render frames of three game ticks are an artificial schedule;
        # no extra time or polling between consecutive simulation steps.
        schedule=[0,0]+[1,0,0]*299+[1]
        self.assertEqual(len(schedule),900)
        submitted,released,skipped=self.check_fixed_release_schedule(schedule)
        self.assertEqual(submitted+skipped,900)
        self.assertGreater(skipped,submitted//2)
        self.assertEqual(submitted-released,2)

    def test_900_ticks_burst_release_credits_are_not_carried_forever(self):
        schedule=[2 if tick%11==0 else 0 for tick in range(900)]
        submitted,released,skipped=self.check_fixed_release_schedule(schedule)
        self.assertEqual(submitted+skipped,900)
        self.assertGreater(skipped,700)
        self.assertLessEqual(self.state().pending,2)

    def test_900_ticks_each_tick_one_external_ack_needs_no_queue_growth(self):
        submitted,released,skipped=self.check_fixed_release_schedule(
            [1]*900)
        self.assertEqual((submitted,released,skipped),(900,899,0))
        self.assertEqual(self.state().pending,1)

    def test_900_ticks_seeded_deterministic_release_mix_matches_oracle(self):
        import random
        generator=random.Random(0xCAD1D150)
        schedule=[generator.choice((0,0,0,1,1,2))
                  for _ in range(900)]
        submitted,released,skipped=self.check_fixed_release_schedule(schedule)
        self.assertEqual(submitted+skipped,900)
        self.assertGreater(released,0)
        self.assertGreater(skipped,0)
        self.assertEqual(self.state().pending,submitted-released)

    def test_pcm_witness_unchanged_across_900_tick_release_schedules(self):
        events=[1<<((i*7)%10) for i in range(900)]
        for i,event in enumerate(events):
            self.step(event,releases=1 if i else 0)
        all_admitted_hash=self.lib.dino_switch_sound_pcm_witness()
        self.assertEqual(self.delta('skipped'),0)
        self.lib.dino_switch_sound_close()
        self.lib.mock_audout_reset()
        self.assertTrue(self.lib.dino_switch_sound_open())
        for event in events:
            self.step(event,releases=0)
        self.assertEqual(self.delta('skipped'),898)
        self.assertEqual(self.lib.dino_switch_sound_pcm_witness(),
                         all_admitted_hash)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)


    def test_guest_boundary_poll_with_no_release_cannot_create_space(self):
        self.step()
        self.step()
        before=self.lib.mock_audout_poll_calls()
        self.lib.dino_switch_sound_guest_mid_batch_poll()
        self.assertEqual(self.lib.mock_audout_poll_calls()-before,1)
        self.assertEqual(self.lib.mock_audout_pending(),2)
        self.assertEqual(self.delta('released'),0)
        self.assertEqual(self.delta('simulated_ticks'),2)
        self.step()
        self.assertEqual((self.delta('submitted'),self.delta('skipped')),
                         (2,1))
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)

    def test_extra_guest_poll_consumes_only_real_external_ack(self):
        self.step()
        self.step()
        self.lib.mock_audout_grant_releases(1)
        self.lib.dino_switch_sound_guest_mid_batch_poll()
        self.assertEqual(self.delta('released'),1)
        self.assertEqual(self.state().pending,1)
        self.assertEqual(self.delta('simulated_ticks'),2)
        self.step(releases=0)
        self.assertEqual(self.delta('submitted'),3)
        self.assertEqual(self.delta('skipped'),0)
        self.assertEqual(self.lib.mock_audout_page_layout_ok(),1)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)

    def test_guest_poll_preserves_pcm_clock_and_generated_hash(self):
        events=[1<<3,1<<4,1<<2,1<<5,1<<9,1<<1]
        for event in events:
            self.lib.dino_switch_sound_guest_mid_batch_poll()
            self.step(event)
        with_extra=self.lib.dino_switch_sound_pcm_witness()
        self.assertEqual(self.lib.dino_switch_sound_pcm_ticks()-
                         self.pcm_baseline,len(events))
        self.lib.dino_switch_sound_close()
        self.lib.mock_audout_reset()
        self.assertTrue(self.lib.dino_switch_sound_open())
        for event in events:
            self.step(event)
        self.assertEqual(self.lib.dino_switch_sound_pcm_witness(),with_extra)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)

    def test_invalid_mid_batch_release_refuses_reuse_fail_closed(self):
        self.step()
        self.step()
        self.lib.mock_audout_inject_bad_release(1)
        before=self.state().audio_errors
        self.lib.dino_switch_sound_guest_mid_batch_poll()
        q=self.state()
        self.assertFalse(q.active)
        self.assertEqual(q.audio_errors,before+1)
        self.assertEqual(q.pending,0)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)
        self.lib.dino_switch_sound_step(1<<3)
        self.assertEqual(self.delta('simulated_ticks'),3)

    def test_guest_poll_drains_two_pages_without_pcm_admission(self):
        self.step()
        self.step()
        before=self.lib.mock_audout_poll_calls()
        self.lib.mock_audout_grant_releases(2)
        self.lib.dino_switch_sound_guest_mid_batch_poll()
        self.assertEqual(self.lib.mock_audout_poll_calls()-before,3)
        self.assertEqual(self.state().pending,0)
        self.assertEqual(self.delta('released'),2)
        self.assertEqual(self.delta('submitted'),2)
        self.assertEqual(self.delta('simulated_ticks'),2)
        self.step(releases=0)
        self.assertEqual(self.state().pending,1)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)


    def test_experimental_poll_counts_only_actual_optional_sweeps(self):
        self.assertEqual(self.lib.dino_switch_sound_guest_mid_batch_enabled(),1)
        self.step()
        self.step()
        self.lib.dino_switch_sound_guest_mid_batch_poll()
        self.assertEqual(self.lib.dino_switch_sound_guest_mid_batch_calls(),1)
        self.assertEqual(self.lib.dino_switch_sound_guest_mid_batch_releases(),0)
        self.lib.mock_audout_grant_releases(1)
        self.lib.dino_switch_sound_guest_mid_batch_poll()
        self.assertEqual(self.lib.dino_switch_sound_guest_mid_batch_calls(),2)
        self.assertEqual(self.lib.dino_switch_sound_guest_mid_batch_releases(),1)
        self.assertEqual(self.delta('released'),1)
        self.assertEqual(self.delta('simulated_ticks'),2)
        self.step()
        self.assertEqual(self.lib.dino_switch_sound_guest_mid_batch_calls(),2)
        self.assertEqual(self.lib.dino_switch_sound_guest_mid_batch_releases(),1)
        self.assertEqual(self.lib.mock_audout_integrity_errors(),0)

    def test_experiment_counters_reset_when_sound_backend_reopens(self):
        self.step()
        self.lib.dino_switch_sound_guest_mid_batch_poll()
        self.assertEqual(self.lib.dino_switch_sound_guest_mid_batch_calls(),1)
        self.lib.dino_switch_sound_close()
        self.lib.mock_audout_reset()
        self.assertTrue(self.lib.dino_switch_sound_open())
        self.assertEqual(self.lib.dino_switch_sound_guest_mid_batch_calls(),0)
        self.assertEqual(self.lib.dino_switch_sound_guest_mid_batch_releases(),0)
        self.assertEqual(self.lib.mock_audout_pending(),0)

    def test_default_guest_has_zero_extra_poll_functions_and_state(self):
        # Compile without the experimental flag: this is a distinct
        # native C binary, not a fake zero injected into a report.
        with tempfile.TemporaryDirectory(prefix='dino-default-audout-') as tmp:
            lib=Path(tmp)/'baseline.so'
            sources=[
                'source/dino_switch_sound.c','source/dino_audio_queue.c',
                'source/dino_sfx.c','source/dino_pcm_witness.c',
                'tests/mocks/mock_audout.c',
            ]
            cmd=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                 '-DDINO_EMULATOR_SELFTEST','-fPIC','-shared',
                 '-Itests/mocks','-Isource',*sources,'-o',str(lib)]
            r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stderr)
            baseline=ctypes.CDLL(str(lib))
            for name in ('dino_switch_sound_guest_mid_batch_enabled',
                         'dino_switch_sound_guest_mid_batch_calls',
                         'dino_switch_sound_guest_mid_batch_releases'):
                getattr(baseline,name).restype=ctypes.c_uint32
                self.assertEqual(getattr(baseline,name)(),0)
            with self.assertRaises(AttributeError):
                baseline.dino_switch_sound_guest_mid_batch_poll

    def check_release_mode_matches_baseline_pcm(self, defines):
        """Real adapter binaries; no guessed guest counters or fake audio."""
        with tempfile.TemporaryDirectory(prefix='dino-release-parity-') as tmp:
            lib=Path(tmp)/'release_audio.so'
            sources=[
                'source/dino_switch_sound.c','source/dino_audio_queue.c',
                'source/dino_sfx.c','source/dino_pcm_witness.c',
                'tests/mocks/mock_audout.c',
            ]
            command=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                     *defines,'-fPIC','-shared',
                     '-Itests/mocks','-Isource',*sources,'-o',str(lib)]
            result=subprocess.run(command,cwd=ROOT,
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            normal=ctypes.CDLL(str(lib))
            # Neither ordinary release code nor an accidentally supplied
            # experiment macro alone may link guest-only interfaces.
            for forbidden in (
                    'dino_switch_sound_guest_mid_batch_poll',
                    'dino_switch_sound_guest_mid_batch_enabled',
                    'dino_switch_sound_guest_mid_batch_calls',
                    'dino_switch_sound_guest_mid_batch_releases'):
                with self.assertRaises(AttributeError,msg=forbidden):
                    getattr(normal,forbidden)
            normal.dino_switch_sound_open.restype=ctypes.c_bool
            normal.dino_switch_sound_step.argtypes=[ctypes.c_uint32]
            normal.dino_switch_sound_diagnostics.argtypes=[
                ctypes.POINTER(Diagnostics)]
            normal.dino_switch_sound_pcm_witness.restype=ctypes.c_uint64
            normal.dino_switch_sound_pcm_ticks.restype=ctypes.c_uint32
            normal.mock_audout_grant_releases.argtypes=[ctypes.c_uint32]
            normal.mock_audout_pending.restype=ctypes.c_uint32
            normal.mock_audout_integrity_errors.restype=ctypes.c_uint32
            normal.mock_audout_page_layout_ok.restype=ctypes.c_uint32
            normal.mock_audout_reset()
            self.assertTrue(normal.dino_switch_sound_open())
            try:
                for tick in range(900):
                    event=1<<((tick*7)%10) if tick%3==0 else 0
                    external_ack=(2 if tick%37==0
                                  else (1 if tick%5==0 else 0))
                    self.step(event,releases=external_ack)
                    normal.mock_audout_grant_releases(external_ack)
                    normal.dino_switch_sound_step(event)
                    actual=Diagnostics()
                    normal.dino_switch_sound_diagnostics(
                        ctypes.byref(actual))
                    expected=self.state()
                    self.assertEqual(
                        tuple(getattr(actual,key) for key,_ in
                              Diagnostics._fields_),
                        tuple(getattr(expected,key) for key,_ in
                              Diagnostics._fields_))
                    self.assertEqual(
                        normal.dino_switch_sound_pcm_ticks(),
                        self.lib.dino_switch_sound_pcm_ticks())
                    if tick%75==0 or tick==899:
                        self.assertEqual(
                            normal.dino_switch_sound_pcm_witness(),
                            self.lib.dino_switch_sound_pcm_witness())
                    self.assertEqual(actual.pending,
                                     normal.mock_audout_pending())
                    self.assertLessEqual(actual.pending,2)
                    self.assertEqual(
                        normal.mock_audout_integrity_errors(),0)
                self.assertEqual(normal.mock_audout_page_layout_ok(),1)
            finally:
                normal.dino_switch_sound_close()

    def test_ordinary_release_binary_matches_guest_pcm_for_900_ticks(self):
        self.check_release_mode_matches_baseline_pcm([])

    def test_unguarded_experiment_macro_cannot_affect_release_binary(self):
        # Both defines must be present: stray opt-in alone must not
        # activate or even link the experimental guest-only probe.
        self.check_release_mode_matches_baseline_pcm(
            ['-DDINO_AUDIO_EXPERIMENT_MID_BATCH_POLL'])

    def test_active_sound_adapter_open_is_idempotent(self):
        self.step(1<<3)
        start=self.lib.dino_switch_sound_pcm_ticks()
        self.assertTrue(self.lib.dino_switch_sound_open())
        self.assertEqual(self.lib.dino_switch_sound_pcm_ticks(),start)
        self.step()
        self.assertEqual(self.lib.dino_switch_sound_pcm_ticks(),start+1)
        self.assertEqual(self.lib.mock_audout_appended(),2)


if __name__=='__main__':
    unittest.main()
