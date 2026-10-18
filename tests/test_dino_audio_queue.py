"""ROM-free, host-compiled tests of the Switch sound buffer admission gate.

This C policy never touches the Switch operating system. It enforces
bounded queued audio and a fail-closed buffer release contract.
"""
import ctypes
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class Queue(ctypes.Structure):
    _fields_=[
        ('busy',ctypes.c_uint8*4),
        ('pending',ctypes.c_uint8),
        ('submitted',ctypes.c_uint32),
        ('skipped',ctypes.c_uint32),
        ('released',ctypes.c_uint32),
    ]

@unittest.skipUnless(shutil.which('gcc'), 'Host GCC needed for portable sound queue tests')
class SoundQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dino-rom-free-audio-queue-')
        lib=Path(cls.tmp.name)/'soundqueue.so'
        compile=subprocess.run(
            ['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
             '-fPIC','-shared','-Isource','source/dino_audio_queue.c',
             '-o',str(lib)],
            cwd=ROOT,check=False,capture_output=True,text=True)
        if compile.returncode:
            raise AssertionError('Portable queue C failed to compile: '+compile.stderr)
        cls.dll=ctypes.CDLL(str(lib))
        cls.dll.dino_audio_queue_reset.argtypes=[ctypes.POINTER(Queue)]
        cls.dll.dino_audio_queue_pick.argtypes=[ctypes.POINTER(Queue)]
        cls.dll.dino_audio_queue_pick.restype=ctypes.c_int
        cls.dll.dino_audio_queue_submit.argtypes=[
            ctypes.POINTER(Queue),ctypes.c_uint]
        cls.dll.dino_audio_queue_submit.restype=ctypes.c_bool
        cls.dll.dino_audio_queue_release.argtypes=[
            ctypes.POINTER(Queue),ctypes.c_uint]
        cls.dll.dino_audio_queue_release.restype=ctypes.c_bool
        cls.dll.dino_audio_queue_skip.argtypes=[ctypes.POINTER(Queue)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def fresh(self):
        q=Queue()
        self.dll.dino_audio_queue_reset(ctypes.byref(q))
        return q

    def pick(self,q):
        return self.dll.dino_audio_queue_pick(ctypes.byref(q))

    def submit(self,q,index):
        return self.dll.dino_audio_queue_submit(ctypes.byref(q),index)

    def release(self,q,index):
        return self.dll.dino_audio_queue_release(ctypes.byref(q),index)

    def test_empty_queue_has_free_first_page(self):
        q=self.fresh()
        self.assertEqual(self.pick(q),0)
        self.assertEqual((q.pending,q.submitted,q.skipped,q.released),(0,0,0,0))
        self.assertEqual(tuple(q.busy),(0,0,0,0))

    def test_only_two_inflight_pages_are_accepted(self):
        q=self.fresh()
        self.assertTrue(self.submit(q,0))
        self.assertTrue(self.submit(q,1))
        self.assertEqual((q.pending,q.submitted),(2,2))
        self.assertEqual(self.pick(q),-1)
        self.assertFalse(self.submit(q,2))
        self.assertEqual(tuple(q.busy),(1,1,0,0))

    def test_released_page_is_safe_for_reuse_only_after_ack(self):
        q=self.fresh()
        self.assertTrue(self.submit(q,0))
        self.assertTrue(self.submit(q,1))
        self.assertEqual(self.pick(q),-1)
        self.assertTrue(self.release(q,0))
        self.assertEqual((q.pending,q.released),(1,1))
        self.assertEqual(self.pick(q),0)
        self.assertTrue(self.submit(q,0))
        self.assertEqual((q.pending,q.submitted),(2,3))

    def test_invalid_and_duplicate_release_do_not_change_state(self):
        q=self.fresh()
        self.assertTrue(self.submit(q,0))
        before=bytes(q)
        for index in (1,2,3,4,100):
            self.assertFalse(self.release(q,index))
            self.assertEqual(bytes(q),before)
        self.assertTrue(self.release(q,0))
        after=bytes(q)
        self.assertFalse(self.release(q,0))
        self.assertEqual(bytes(q),after)

    def test_double_submit_and_out_of_range_are_rejected(self):
        q=self.fresh()
        self.assertTrue(self.submit(q,1))
        before=bytes(q)
        for index in (1,4,123):
            self.assertFalse(self.submit(q,index))
            self.assertEqual(bytes(q),before)

    def test_audio_stall_drops_subsequent_ticks_without_unbounded_queue(self):
        q=self.fresh()
        for tick in range(200):
            index=self.pick(q)
            if index<0:
                self.dll.dino_audio_queue_skip(ctypes.byref(q))
            else:
                self.assertTrue(self.submit(q,index))
            self.assertLessEqual(q.pending,2)
        self.assertEqual((q.submitted,q.skipped,q.pending),(2,198,2))
        self.assertEqual(self.pick(q),-1)
        self.assertTrue(self.release(q,0))
        self.assertTrue(self.release(q,1))
        self.assertEqual(q.pending,0)
        self.assertEqual(self.pick(q),0)

    def test_fourth_physical_page_can_be_used_within_two_page_cap(self):
        q=self.fresh()
        self.assertTrue(self.submit(q,3))
        self.assertEqual(self.pick(q),0)
        self.assertTrue(self.submit(q,2))
        self.assertEqual(self.pick(q),-1)
        self.assertTrue(self.release(q,3))
        self.assertEqual(self.pick(q),0)
        self.assertTrue(self.submit(q,0))
        self.assertEqual(tuple(q.busy),(1,0,1,0))
        self.assertEqual(q.pending,2)

    def test_skip_counter_only_changes_explicitly_and_reset_clears_all(self):
        q=self.fresh()
        self.submit(q,0)
        self.dll.dino_audio_queue_skip(ctypes.byref(q))
        self.dll.dino_audio_queue_skip(ctypes.byref(q))
        self.assertEqual((q.pending,q.skipped),(1,2))
        self.dll.dino_audio_queue_reset(ctypes.byref(q))
        self.assertEqual((q.pending,q.submitted,q.skipped,q.released),(0,0,0,0))
        self.assertEqual(self.pick(q),0)

    def test_two_independent_queues_follow_identical_events(self):
        a,b=self.fresh(),self.fresh()
        for tick in range(800):
            for q in (a,b):
                if tick%7==0:
                    for i in range(4):
                        if q.busy[i]:
                            self.release(q,i)
                            break
                free=self.pick(q)
                if free<0:
                    self.dll.dino_audio_queue_skip(ctypes.byref(q))
                else:
                    self.submit(q,free)
                self.assertLessEqual(q.pending,2)
        self.assertEqual(bytes(a),bytes(b))
        self.assertGreater(a.skipped,0)

    def test_null_pointer_handling_is_fail_closed(self):
        self.dll.dino_audio_queue_reset(None)
        self.assertEqual(self.dll.dino_audio_queue_pick(None),-1)
        self.assertFalse(self.dll.dino_audio_queue_submit(None,0))
        self.assertFalse(self.dll.dino_audio_queue_release(None,0))
        self.dll.dino_audio_queue_skip(None)

if __name__=='__main__':
    unittest.main()
