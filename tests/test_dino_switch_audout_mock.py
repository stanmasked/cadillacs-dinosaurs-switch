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
