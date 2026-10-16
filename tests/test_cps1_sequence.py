"""Portable C/Python timeline tests. Only synthetic scene data; no game ROMs."""
import ctypes
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib

from tools.cps1_scene_export import pack_scene, FILE_BYTES
from tools.cps1_sequence_export import pack_sequence, demo_snapshots, HEADER_BYTES, MAX_FRAMES

ROOT=Path(__file__).resolve().parents[1]

class SeqInfo(ctypes.Structure):
    _fields_=[('blob',ctypes.c_void_p),('frame_count',ctypes.c_uint16),
              ('fps',ctypes.c_uint16)]

class Playback(ctypes.Structure):
    _fields_=[('index',ctypes.c_uint32),('remainder',ctypes.c_uint32),
              ('speed_num',ctypes.c_uint),('paused',ctypes.c_bool)]

def fixture(n=3, fps=12):
    frames=[pack_scene(item) for item in demo_snapshots(n)]
    return pack_sequence(frames,fps)

@unittest.skipUnless(shutil.which('gcc'), 'Host gcc needed to validate portable native C')
class Cps1SequenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='cps1-sequence-')
        cls.lib=Path(cls.tmp.name)/'libseq.so'
        proc=subprocess.run(
            ['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fPIC','-shared',
             '-Isource','source/cps1_tile.c','source/cps1_scene.c',
             'source/cps1_sequence.c','-o',str(cls.lib)],
            cwd=ROOT,text=True,capture_output=True)
        if proc.returncode:
            raise AssertionError('gcc failed:\n'+proc.stderr)
        cls.dll=ctypes.CDLL(str(cls.lib))
        cls.dll.cps1_sequence_decode.argtypes=[ctypes.c_void_p,ctypes.c_size_t,
                                               ctypes.POINTER(SeqInfo)]
        cls.dll.cps1_sequence_decode.restype=ctypes.c_bool
        cls.dll.cps1_sequence_frame.argtypes=[ctypes.POINTER(SeqInfo),ctypes.c_uint,
                                              ctypes.c_void_p]
        cls.dll.cps1_sequence_frame.restype=ctypes.c_bool
        cls.dll.cps1_playback_init.argtypes=[ctypes.POINTER(Playback)]
        cls.dll.cps1_playback_advance.argtypes=[ctypes.POINTER(Playback),
                                                ctypes.POINTER(SeqInfo),ctypes.c_uint32]
        cls.dll.cps1_playback_advance.restype=ctypes.c_bool
        cls.dll.cps1_playback_step.argtypes=[ctypes.POINTER(Playback),
                                             ctypes.POINTER(SeqInfo),ctypes.c_int]
        cls.dll.cps1_playback_step.restype=ctypes.c_bool
        cls.dll.cps1_playback_speed.argtypes=[ctypes.POINTER(Playback),ctypes.c_int]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def opened(self,data):
        storage=ctypes.create_string_buffer(data)
        info=SeqInfo()
        ok=self.dll.cps1_sequence_decode(storage,len(data),ctypes.byref(info))
        return ok,storage,info

    def playback(self):
        pb=Playback()
        self.dll.cps1_playback_init(ctypes.byref(pb))
        return pb

    def test_three_synthetic_frames_and_crc(self):
        data=fixture()
        self.assertEqual(data[:8],b'CPS1SEQ1')
        self.assertEqual(len(data),HEADER_BYTES+3*FILE_BYTES)
        self.assertEqual(struct.unpack_from('<I',data,12)[0],zlib.crc32(data[20:]))
        ok,storage,info=self.opened(data)
        self.assertTrue(ok)
        self.assertEqual((info.frame_count,info.fps),(3,12))
        self.assertEqual(info.blob,ctypes.addressof(storage))

    def test_can_decode_each_embedded_scene(self):
        ok,storage,seq=self.opened(fixture())
        self.assertTrue(ok)
        for index in range(3):
            with self.subTest(index=index):
                scene=ctypes.create_string_buffer(70000)
                self.assertTrue(self.dll.cps1_sequence_frame(
                    ctypes.byref(seq),index,scene))
                self.assertEqual(struct.unpack_from('<H',scene.raw,4)[0],
                                 demo_snapshots(3)[index]['scroll1']['scrollx'])

    def test_reject_out_of_range_frame(self):
        ok,storage,seq=self.opened(fixture())
        self.assertTrue(ok)
        self.assertFalse(self.dll.cps1_sequence_frame(
            ctypes.byref(seq),3,ctypes.create_string_buffer(70000)))

    def test_crc_rejects_mutated_data(self):
        data=bytearray(fixture())
        data[75]^=1
        self.assertFalse(self.opened(data)[0])

    def test_reject_invalid_header_and_truncation(self):
        data=fixture()
        self.assertFalse(self.opened(data[:-1])[0])
        self.assertFalse(self.opened(b'BADMAGIC'+data[8:])[0])
        broken=bytearray(data)
        broken[16]=1
        self.assertFalse(self.opened(broken)[0])

    def test_reject_per_frame_checksum_even_when_outer_crc_is_valid(self):
        data=bytearray(fixture())
        data[80]^=0x20
        struct.pack_into('<I',data,12,zlib.crc32(data[20:]))
        self.assertFalse(self.opened(data)[0])

    def test_python_reject_invalid_rate_or_count(self):
        scene=pack_scene(demo_snapshots(1)[0])
        with self.assertRaises(ValueError): pack_sequence([scene],0)
        with self.assertRaises(ValueError): pack_sequence([scene],61)
        with self.assertRaises(ValueError): pack_sequence([],12)
        with self.assertRaises(ValueError): pack_sequence([scene]*(MAX_FRAMES+1),12)

    def test_tick_accumulator_exact_12fps(self):
        ok,data,seq=self.opened(fixture())
        pb=self.playback()
        self.assertTrue(ok)
        for _ in range(4):
            self.assertFalse(self.dll.cps1_playback_advance(
                ctypes.byref(pb),ctypes.byref(seq),1))
        self.assertEqual((pb.index,pb.remainder),(0,96))
        self.assertTrue(self.dll.cps1_playback_advance(
            ctypes.byref(pb),ctypes.byref(seq),1))
        self.assertEqual((pb.index,pb.remainder),(1,0))

    def test_tick_wrap_across_three_frames(self):
        ok,data,seq=self.opened(fixture())
        pb=self.playback()
        self.assertTrue(ok)
        self.assertTrue(self.dll.cps1_playback_advance(
            ctypes.byref(pb),ctypes.byref(seq),20))
        self.assertEqual(pb.index,1)  # four frames modulo three

    def test_pause_freezes_and_manual_step_pauses(self):
        ok,data,seq=self.opened(fixture())
        pb=self.playback()
        pb.paused=True
        self.assertFalse(self.dll.cps1_playback_advance(
            ctypes.byref(pb),ctypes.byref(seq),60))
        self.assertEqual(pb.index,0)
        self.assertTrue(self.dll.cps1_playback_step(
            ctypes.byref(pb),ctypes.byref(seq),-1))
        self.assertEqual(pb.index,2)
        self.assertTrue(pb.paused)
        self.assertTrue(self.dll.cps1_playback_step(
            ctypes.byref(pb),ctypes.byref(seq),1))
        self.assertEqual(pb.index,0)

    def test_three_playback_speeds(self):
        ok,data,seq=self.opened(fixture())
        pb=self.playback()
        self.dll.cps1_playback_speed(ctypes.byref(pb),-1)
        self.assertEqual(pb.speed_num,1)
        self.assertFalse(self.dll.cps1_playback_advance(
            ctypes.byref(pb),ctypes.byref(seq),5))
        self.assertTrue(self.dll.cps1_playback_advance(
            ctypes.byref(pb),ctypes.byref(seq),5))
        self.dll.cps1_playback_speed(ctypes.byref(pb),1)
        self.dll.cps1_playback_speed(ctypes.byref(pb),1)
        self.assertEqual(pb.speed_num,4)
        self.assertTrue(self.dll.cps1_playback_advance(
            ctypes.byref(pb),ctypes.byref(seq),5))

    def test_missing_pointer_rejected(self):
        ok,data,seq=self.opened(fixture())
        self.assertFalse(self.dll.cps1_playback_advance(None,ctypes.byref(seq),1))
        self.assertFalse(self.dll.cps1_sequence_frame(ctypes.byref(seq),0,None))

    def test_source_is_not_modified_by_playback(self):
        before=fixture()
        ok,data,seq=self.opened(before)
        pb=self.playback()
        self.assertTrue(ok)
        self.dll.cps1_playback_advance(ctypes.byref(pb),ctypes.byref(seq),9999)
        self.assertEqual(data.raw[:len(before)],before)

if __name__=='__main__':
    unittest.main()
