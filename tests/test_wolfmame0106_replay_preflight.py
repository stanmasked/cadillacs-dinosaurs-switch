"""Synthetic, ROM-free Stage272 bootstrap and PNG receipt tests."""
import json
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from tools import wolfmame0106_replay_preflight as pre

def plan():
    return {
        'schema':pre.PLAN_SCHEMA,
        'status':'PRIVATE_PLAYBACK_CAPTURE_REQUEST_NOT_EXECUTED',
        'total_original_recorded_frames':314951,
        'actual_emulator_frames_captured':False,
        'input_binding_and_exact_video_frame_alignment_verified':False,
        'public_GitHub_raw_capture_export_permitted':False,
        'overview':{'requested_frames':[0,60]},
        'detail':{'requested_frames':[180,181]},
        'overview_frame_count':2,'detail_frame_count':2,
    }

def chunk(name,data):
    return (struct.pack('>I',len(data))+name+data+
            struct.pack('>I',zlib.crc32(name+data)&0xffffffff))

def png(w=2,h=2):
    ihdr=struct.pack('>IIBBBBB',w,h,8,2,0,0,0)
    raw=b''.join(b'\0'+b'\xff\0\0'*w for _ in range(h))
    return (pre.PNG_SIG+chunk(b'IHDR',ihdr)+
            chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b''))

class WolfmameBootstrapTests(unittest.TestCase):
    def test_first_start_anchor_and_early_frames(self):
        q=pre.make_request(plan(),102)
        self.assertEqual(q['frame_indices'][0],0)
        for frame in (99,102,103,110,118,120,3600):
            self.assertIn(frame,q['frame_indices'])
        self.assertEqual(len(q['frame_indices']),len(set(q['frame_indices'])))
        self.assertFalse(q['input_to_image_sync_verified'])

    def test_reject_anchor_outside_record(self):
        for anchor in (-1,314951,True,'102',1.5):
            with self.subTest(anchor=anchor),self.assertRaises(ValueError):
                pre.make_request(plan(),anchor)

    def test_reject_false_capture_claim_in_plan(self):
        src=plan()
        src['actual_emulator_frames_captured']=True
        with self.assertRaises(ValueError):
            pre.make_request(src,102)

    def test_png_chunk_crc_and_dimensions(self):
        self.assertEqual(pre.png_integrity(png())['width'],2)

    def test_corrupted_png_crc_is_rejected(self):
        damaged=bytearray(png())
        damaged[22]^=1
        with self.assertRaisesRegex(ValueError,'CRC'):
            pre.png_integrity(bytes(damaged))

    def test_invalid_png_compressed_payload_rejected(self):
        raw=png()
        idx=raw.find(b'IDAT')
        n=struct.unpack('>I',raw[idx-4:idx])[0]
        fake=raw[:idx-4]+chunk(b'IDAT',b'invalidstream')+raw[idx+n+8:]
        with self.assertRaisesRegex(ValueError,'IDAT'):
            pre.png_integrity(fake)

    def test_exact_receipt_hashes_without_content_claim(self):
        q=pre.make_request(plan(),102)
        with tempfile.TemporaryDirectory() as folder:
            for name in q['image_names']:
                (Path(folder)/name).write_bytes(png())
            result=pre.audit_captures(q,folder,2,2)
            self.assertEqual(result['frames_received'],q['expected_capture_count'])
            self.assertTrue(all(len(e['sha256'])==64 for e in result['image_files']))
            self.assertFalse(result['pixel_parity_verified'])

    def test_reject_missing_and_extra_pngs(self):
        q=pre.make_request(plan())
        with tempfile.TemporaryDirectory() as folder:
            for name in q['image_names'][:-1]:
                (Path(folder)/name).write_bytes(png())
            with self.assertRaisesRegex(ValueError,'missing'):
                pre.audit_captures(q,folder)
            (Path(folder)/q['image_names'][-1]).write_bytes(png())
            (Path(folder)/'extra.png').write_bytes(png())
            with self.assertRaisesRegex(ValueError,'unexpected'):
                pre.audit_captures(q,folder)

    def test_reject_symlink_png(self):
        q=pre.make_request(plan())
        with tempfile.TemporaryDirectory() as folder:
            for name in q['image_names']:
                (Path(folder)/name).write_bytes(png())
            original=Path(folder)/q['image_names'][0]
            original.unlink()
            original.symlink_to(Path(folder)/q['image_names'][1])
            with self.assertRaisesRegex(ValueError,'ordinary'):
                pre.audit_captures(q,folder)

    def test_reject_wrong_resolution(self):
        q=pre.make_request(plan())
        with tempfile.TemporaryDirectory() as folder:
            for name in q['image_names']:
                (Path(folder)/name).write_bytes(png())
            with self.assertRaisesRegex(ValueError,'resolution'):
                pre.audit_captures(q,folder,384,224)

    def test_duplicate_json_keys_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'fake.json'
            path.write_text('{"frame":1,"frame":2}')
            with self.assertRaisesRegex(ValueError,'duplicate'):
                pre.read_json(path,1000)

if __name__=='__main__':
    unittest.main()
