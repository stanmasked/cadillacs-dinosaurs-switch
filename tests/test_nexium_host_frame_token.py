"""Stage 253: synthetic-only X11 watermark and native frame identity tests."""
import csv
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from tools import nexium_host_live_counter_pixel as host
from tools import verify_nexium_host_frame_token as verifier

def write_csv(path,headers,rows):
    with path.open('w',encoding='ascii',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


class FrameTokenTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.token=3141
        self.host_path=self.root/'host-token.json'
        self.window=self.root/'host-window.json'
        self.trace=self.root/'trace.csv'
        self.frame=self.root/'frame.csv'
        self.metadata=self.root/'metadata.txt'
        self.nro=self.root/'guest.nro'
        original=bytearray(256)
        original[16:20]=b'NRO0'
        struct.pack_into('<I',original,0x18,256)
        self.nro.write_bytes(original)
        digest=hashlib.sha256(original).hexdigest()
        self.metadata.write_text('scope=REAL_NE_XIUM_GUEST_CI_NO_NINTENDO_ROM\n'
                                 'nro_sha256='+digest+'\n')
        self.host_path.write_text(json.dumps({
            'schema':verifier.HOST_SCHEMA,'status':verifier.STATUS,
            'token_u16':self.token,
            'token_same_x11_image_as_counter_pixels':True,
            'guest_submitted_frame_identity_verified':False,
            'exact_host_guest_frame_latency_verified':False,
            'physical_display_verified':False,
        }))
        self.window.write_text(json.dumps({
            'status':'HOST_WINDOW_COUNTER_PIXELS_OBSERVED_UNBOUND',
            'host_x11_window_counter_pixels_observed':True,
            'counter_transition_baseline_observed':True,
            'same_x11_image_four_pixel_match':True,
        }))
        self.native=[
            dict(event='TOKEN_SUBMITTED',render_iteration='3141',
                 arena_tick='148',feedback_ttl='6',impact_ttl='6',
                 token_u16=str(self.token)),
            dict(event='TOKEN_SUBMITTED',render_iteration='3142',
                 arena_tick='148',feedback_ttl='6',impact_ttl='6',
                 token_u16='3142'),
        ]
        write_csv(self.trace,verifier.CSV_FIELDS,self.native)
        self.sample=dict(zip(verifier.GUEST_FIELDS,
                ('SUBMITTED_COUNTER_FRAME','3141','148','6','6',
                 *verifier.PIXELS)))
        write_csv(self.frame,verifier.GUEST_FIELDS,[self.sample])

    def verify(self):
        return verifier.verify(self.host_path,self.window,self.trace,
                               self.frame,self.metadata,self.nro)

    def mutate_host(self,**kwargs):
        record=json.loads(self.host_path.read_text())
        record.update(kwargs)
        self.host_path.write_text(json.dumps(record))

    def test_decode_all_16_bits_in_one_x11_image(self):
        for token in (0,1,3141,0xA55A,65535):
            colors=[host.TOKEN_SYNC_START]
            colors.extend(host.TOKEN_ONE if token&(1<<i) else host.TOKEN_ZERO
                          for i in range(16))
            colors.append(host.TOKEN_SYNC_END)
            self.assertEqual(host.decode_frame_token(colors),token)
        self.assertIsNone(host.decode_frame_token([host.TOKEN_ZERO]*18))

    def test_cropped_x11_coordinates_monotonic_and_bounded(self):
        xs=[x for x,_ in host.TOKEN_BITS]
        self.assertEqual(len(xs),16)
        self.assertEqual(xs,sorted(set(xs)))
        self.assertEqual(xs[0],935)
        self.assertEqual(xs[-1],1108)
        self.assertLess(host.MIN_X,host.TOKEN_START[0])
        self.assertGreaterEqual(host.MAX_Y,665)

    def test_matching_real_submitted_render_id(self):
        result=self.verify()
        self.assertEqual(result['status'],verifier.SUCCESS)
        self.assertEqual(result['matched_native_render_iteration'],3141)
        self.assertTrue(result['host_x11_guest_submitted_frame_identity_verified'])
        self.assertFalse(result['precise_input_to_display_latency_verified'])
        self.assertFalse(result['physical_switch_display_verified'])

    def test_missing_marker_is_inconclusive(self):
        self.host_path.unlink()
        with self.assertRaises(ValueError):self.verify()

    def test_forged_host_token_rejected(self):
        self.mutate_host(token_u16=9999)
        with self.assertRaises(ValueError):self.verify()

    def test_host_token_without_same_image_counter_rejected(self):
        self.mutate_host(token_same_x11_image_as_counter_pixels=False)
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_render_id_rejected(self):
        write_csv(self.trace,verifier.CSV_FIELDS,[self.native[0],self.native[0]])
        with self.assertRaises(ValueError):self.verify()

    def test_counter_native_frame_absent_rejected(self):
        self.sample['render_iteration']='999'
        write_csv(self.frame,verifier.GUEST_FIELDS,[self.sample])
        with self.assertRaises(ValueError):self.verify()

    def test_forged_native_token_for_iteration_rejected(self):
        self.native[0]['token_u16']='3140'
        write_csv(self.trace,verifier.CSV_FIELDS,self.native)
        with self.assertRaises(ValueError):self.verify()

    def test_missing_exact_nro_binding_rejected(self):
        self.nro.write_bytes(self.nro.read_bytes()+b'forged')
        with self.assertRaises(ValueError):self.verify()

    def test_duplicate_json_evidence_field_rejected(self):
        s=self.host_path.read_text()
        self.host_path.write_text(s.replace('"status":',
                            '"status": "FAKE", "status":'))
        with self.assertRaises(ValueError):self.verify()

    def test_cli_missing_trace_writes_inconclusive(self):
        self.trace.unlink()
        report=self.root/'report.json'
        rc=verifier.main([
            '--host-token',str(self.host_path),
            '--host-window',str(self.window),
            '--guest-trace',str(self.trace),
            '--guest-framebuffer',str(self.frame),
            '--metadata',str(self.metadata),
            '--nro',str(self.nro),
            '--out',str(report)])
        self.assertEqual(rc,0)
        saved=json.loads(report.read_text())
        self.assertEqual(saved['status'],verifier.INCONCLUSIVE)
        self.assertFalse(saved['host_x11_guest_submitted_frame_identity_verified'])


if __name__=='__main__':
    unittest.main()
