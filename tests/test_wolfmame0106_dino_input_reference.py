"""Synthetic ROM-free tests for 0.106 dino INP/WLF input layout."""
import struct
import tempfile
import unittest
from pathlib import Path
from tools import wolfmame0106_dino_input_reference as mod

class WolfMameDinoInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.inp=self.folder/"synthetic.inp"
        self.wlf=self.folder/"synthetic.wlf"
        self.frames=240
        frame=bytearray(mod.FRAME_BYTES)
        for i in (3,18,19,23):
            frame[i]=255
        data=[bytearray(frame) for _ in range(self.frames)]
        for n in range(10,20):
            data[n][19]&=~1   # P1 RIGHT, low IN1 byte
        for n in range(30,40):
            data[n][18]&=~2   # P2 LEFT, high IN1 byte
        for n in range(50,56):
            data[n][19]&=~16  # P1 ATTACK
            data[n][23]&=~4   # P3 DOWN alias
        for n in range(80,83):
            data[n][19]&=~32  # P1 JUMP
            data[n][23]&=~1   # P3 RIGHT alias
        for n in range(2,5):
            data[n][3]&=~16   # START1
        header=bytearray(mod.HEADER_BYTES)
        header[:4]=b"dino"
        header[16:20]=b"ABCD"
        self.inp.write_bytes(header+b"".join(data))
        wlf=bytearray(598)
        wlf[:4]=b"WLF\x00"
        struct.pack_into("<I",wlf,4,9)
        wlf[148:153]=b"dino\x00"
        wlf[157:177]=b"0.106 (May 16 2006)"
        wlf[248:252]=b"ABCD"
        struct.pack_into("<III",wlf,256,1_000_000,1_000_004,self.frames)
        self.wlf.write_bytes(wlf)

    def test_headers_and_exact_stride(self):
        self.assertEqual(mod.metadata(self.inp,self.wlf)[0],240)
        self.assertEqual(self.inp.stat().st_size,32+240*124)

    def test_low_byte_first_player_high_byte_second(self):
        report=mod.analyze(self.inp,self.wlf)
        self.assertEqual(report["port_byte_offsets"]["p1"],19)
        self.assertEqual(report["port_byte_offsets"]["p2"],18)
        counts={(r["port"],r["name"]):r["press_onsets"]
                for r in report["signals"]}
        self.assertEqual(counts[("p1","right")],1)
        self.assertEqual(counts[("p2","left")],1)
        self.assertEqual(counts[("system","start1")],1)
        self.assertNotIn(("p2","right"),counts)
        self.assertEqual(report["total_press_onsets"],7)

    def test_independent_players_not_asserted(self):
        report=mod.analyze(self.inp,self.wlf)
        by_name={(r["signal_a"],r["signal_b"]):r
                 for r in report["cross_player_alias_diagnostics"]}
        self.assertTrue(by_name[("p1.attack_button1","p3.down")]["looks_correlated"])
        self.assertTrue(by_name[("p1.jump_button2","p3.right")]["looks_correlated"])
        self.assertFalse(report["distinct_human_players_confirmed"])
        self.assertFalse(report["original_0_106_serializer_confirmed"])
        self.assertFalse(report["safe_to_publish_original_files"])

    def test_rejects_wrong_game(self):
        data=bytearray(self.inp.read_bytes())
        data[:4]=b"fake"
        self.inp.write_bytes(data)
        with self.assertRaisesRegex(ValueError,"dino"):
            mod.metadata(self.inp,self.wlf)

    def test_rejects_forged_header_binding(self):
        data=bytearray(self.wlf.read_bytes())
        data[248:252]=b"FAKE"
        self.wlf.write_bytes(data)
        with self.assertRaisesRegex(ValueError,"tag"):
            mod.metadata(self.inp,self.wlf)

    def test_rejects_truncated_record(self):
        self.inp.write_bytes(self.inp.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError,"stride"):
            mod.metadata(self.inp,self.wlf)

    def test_rejects_wrong_wlf_version(self):
        data=bytearray(self.wlf.read_bytes())
        struct.pack_into("<I",data,4,8)
        self.wlf.write_bytes(data)
        with self.assertRaisesRegex(ValueError,"revision"):
            mod.metadata(self.inp,self.wlf)

if __name__=="__main__":
    unittest.main()
