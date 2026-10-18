"""Synthetic, ROM-free checks for paired actual guest audio evidence."""
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import json
import struct
from pathlib import Path
import tempfile
import unittest

from tools import verify_nexium_audio_mode_binding as binding
from tools import verify_nexium_audio_paired_artifacts as paired
from test_nexium_audio_mid_batch_ab import complete


def synthetic_nro(label):
    """Synthetic ROM-free NRO header plus mode-distinguishing test text."""
    data=bytearray(256)
    data[0x10:0x14]=b'NRO0'
    struct.pack_into('<I',data,0x18,len(data))
    payload=label.encode('ascii')
    data[0x80:0x80+len(payload)]=payload
    return bytes(data)


class PairedGuestAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='dino-paired-audio-')
        root=Path(self.temp.name)
        self.a=root/'baseline.json'
        self.b=root/'experimental.json'
        self.aa=root/'baseline-mode.json'
        self.bb=root/'experimental-mode.json'
        self.base_nro=root/'baseline.nro'
        self.extra_nro=root/'extra-poll.nro'
        self.base_nro.write_bytes(synthetic_nro('BASELINE'))
        self.extra_nro.write_bytes(synthetic_nro('EXTRA_POLL'))
        self.write()

    def tearDown(self):
        self.temp.cleanup()

    def write(self):
        for file,mode_file,nro,enabled,variation,selected in (
                (self.a,self.aa,self.base_nro,False,0,'baseline'),
                (self.b,self.bb,self.extra_nro,True,1,'extra-poll')):
            file.write_text(json.dumps(complete(enabled,variation),sort_keys=True)+'\n')
            mode_file.write_text(
                json.dumps(binding.attest(selected,file,nro),sort_keys=True)+'\n')

    def analyze(self):
        return paired.compare(self.a,self.aa,self.b,self.bb,
                              self.base_nro,self.extra_nro)

    def test_valid_pair_matches_sha256_without_causality_claim(self):
        result=self.analyze()
        self.assertEqual(result['status'],
                         'UNCONTROLLED_BOUND_GUEST_AUDIO_COMPARISON_DESCRIPTIVE_ONLY')
        self.assertEqual(result['baseline_report_sha256'],
                         hashlib.sha256(self.a.read_bytes()).hexdigest())
        self.assertEqual(result['experimental_report_sha256'],
                         hashlib.sha256(self.b.read_bytes()).hexdigest())
        self.assertEqual(result['baseline_guest_poll_calls'],0)
        self.assertEqual(result['experimental_guest_poll_calls'],150)
        self.assertFalse(result['causal_audio_improvement_verified'])
        self.assertFalse(result['physical_switch_audio_verified'])

    def test_swap_bound_mode_evidence_fails_closed(self):
        with self.assertRaises(ValueError):
            paired.compare(self.a,self.bb,self.b,self.aa,
                           self.base_nro,self.extra_nro)

    def test_forged_sha256_or_selected_mode_is_rejected(self):
        for field,bad in (('guest_report_sha256','0'*64),
                          ('selected_mode','baseline')):
            with self.subTest(field=field):
                forged=json.loads(self.bb.read_text())
                forged[field]=bad
                self.bb.write_text(json.dumps(forged)+'\n')
                with self.assertRaises(ValueError):
                    self.analyze()
                self.write()

    def test_raw_guest_record_changes_after_binding_are_detected(self):
        self.b.write_bytes(self.b.read_bytes()+b' ')
        with self.assertRaises(ValueError):
            self.analyze()

    def test_duplicate_json_fields_are_rejected(self):
        self.bb.write_text(
            self.bb.read_text().replace('{','{"selected_mode":"baseline",',1))
        with self.assertRaises(ValueError):
            self.analyze()

    def test_missing_or_symlink_mode_binding_fails_closed(self):
        self.bb.unlink()
        with self.assertRaises(ValueError):
            self.analyze()
        self.bb.symlink_to(self.aa)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_changed_guest_nro_detected_after_attestation(self):
        self.base_nro.write_bytes(self.base_nro.read_bytes()+b'X')
        with self.assertRaises(ValueError):
            self.analyze()

    def test_identical_guest_nro_modes_rejected_even_if_report_modes_differ(self):
        self.extra_nro.write_bytes(self.base_nro.read_bytes())
        self.write()
        with self.assertRaisesRegex(ValueError,'binaries are identical'):
            self.analyze()

    def test_paired_binary_declared_size_forgery_is_rejected(self):
        data=bytearray(self.extra_nro.read_bytes())
        struct.pack_into('<I',data,0x18,0xffffffff)
        self.extra_nro.write_bytes(data)
        self.write()
        with self.assertRaisesRegex(ValueError,'declared program size'):
            self.analyze()

    def test_guest_nro_symlink_refused(self):
        self.extra_nro.unlink()
        self.extra_nro.symlink_to(self.base_nro)
        with self.assertRaises(ValueError):
            self.analyze()

    def test_cli_writes_new_file_without_touching_inputs(self):
        output=Path(self.temp.name)/'result.json'
        originals=[p.read_bytes() for p in (self.a,self.aa,self.b,self.bb)]
        captured=StringIO()
        with redirect_stdout(captured):
            rc=paired.main([
                '--baseline-report',str(self.a),'--baseline-binding',str(self.aa),
                '--experimental-report',str(self.b),'--experimental-binding',str(self.bb),
                '--baseline-nro',str(self.base_nro),
                '--experimental-nro',str(self.extra_nro),
                '--out',str(output)])
        self.assertEqual(rc,0)
        self.assertEqual(output.read_text(),captured.getvalue())
        self.assertEqual([p.read_bytes() for p in (self.a,self.aa,self.b,self.bb)],originals)

    def test_cli_inconclusive_writes_fail_closed_artifact(self):
        self.bb.unlink()
        output=Path(self.temp.name)/'result.json'
        captured=StringIO()
        with redirect_stdout(captured):
            rc=paired.main([
                '--baseline-report',str(self.a),'--baseline-binding',str(self.aa),
                '--experimental-report',str(self.b),'--experimental-binding',str(self.bb),
                '--baseline-nro',str(self.base_nro),
                '--experimental-nro',str(self.extra_nro),
                '--out',str(output)])
        self.assertEqual(rc,1)
        result=json.loads(output.read_text())
        self.assertEqual(result['status'],
                         'INCONCLUSIVE_UNVERIFIED_BOUND_GUEST_AUDIO_COMPARISON')
        self.assertFalse(result['causal_audio_improvement_verified'])

    def test_cli_refuses_to_overwrite_guest_json(self):
        original=self.a.read_bytes()
        captured=StringIO()
        with redirect_stdout(captured):
            rc=paired.main([
                '--baseline-report',str(self.a),'--baseline-binding',str(self.aa),
                '--experimental-report',str(self.b),'--experimental-binding',str(self.bb),
                '--baseline-nro',str(self.base_nro),
                '--experimental-nro',str(self.extra_nro),
                '--out',str(self.a)])
        self.assertEqual(rc,1)
        self.assertEqual(self.a.read_bytes(),original)


if __name__=='__main__':
    unittest.main()
