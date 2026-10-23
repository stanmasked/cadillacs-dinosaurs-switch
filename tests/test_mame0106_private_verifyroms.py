"""Synthetic data only. No original game content or recordings."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import zipfile

from tools import mame0106_private_verifyroms as p


class PrivateVerifyRomsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.xml = self.dir / 'driver.xml'
        self.archive = self.dir / 'dino.zip'
        self.payloads = {'synthetic_a.bin': b'Never a game ROM',
                         'synthetic_b.bin': b'Synthetic test material' * 10}
        root = ET.Element('mame')
        game = ET.SubElement(root, 'game', {'name':'dino','runnable':'yes'})
        for name,data in self.payloads.items():
            ET.SubElement(game,'rom',{'name':name,'size':str(len(data)),
                                      'crc':f'{zipfile.crc32(data) & 0xffffffff:08x}',
                                      'sha1':hashlib.sha1(data).hexdigest()})
        self.xml.write_bytes(ET.tostring(root))
        self.make_archive()

    def make_archive(self, payloads=None):
        with zipfile.ZipFile(self.archive,'w') as z:
            for name,content in (payloads or self.payloads).items():
                z.writestr(name,content)
        self.sha = p.digest(self.archive)
        self.xml_sha = p.digest(self.xml)

    def audit(self, **kw):
        return p.offline_audit(self.archive,self.xml,rom_sha=self.sha,
                               xml_sha=self.xml_sha,**kw)

    def test_valid_synthetic_rom_set(self):
        result = self.audit()
        self.assertEqual((result['verified_roms'],result['offline_audit']), (2,'pass'))

    def test_default_production_pins_reject_synthetic(self):
        with self.assertRaises(p.PrivateProbeError):
            p.offline_audit(self.archive,self.xml)

    def test_tampered_payload_fails_even_with_outer_repin(self):
        self.make_archive({'synthetic_a.bin':b'corrupt', 'synthetic_b.bin':self.payloads['synthetic_b.bin']})
        with self.assertRaises(p.PrivateProbeError):self.audit()

    def test_missing_one_member_rejected(self):
        self.make_archive({'synthetic_a.bin':self.payloads['synthetic_a.bin']})
        with self.assertRaisesRegex(p.PrivateProbeError,'rom_inventory_mismatch'):self.audit()

    def test_unexpected_extra_member_rejected(self):
        extra=dict(self.payloads)
        extra['private.raw']=b'synthetic extra'
        self.make_archive(extra)
        with self.assertRaisesRegex(p.PrivateProbeError,'rom_inventory_mismatch'):self.audit()

    def test_renamed_entry_rejected(self):
        self.make_archive({'other.bin':self.payloads['synthetic_a.bin'],
                           'synthetic_b.bin':self.payloads['synthetic_b.bin']})
        with self.assertRaises(p.PrivateProbeError):self.audit()

    def test_public_actions_rejected_before_disk_access(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            with self.assertRaisesRegex(p.PrivateProbeError,'public_runner_forbidden'):
                self.audit()

    def test_native_output_requires_two_markers(self):
        ok = b'romset dino is good\n1 romsets found, 1 were OK.\n'
        self.assertEqual(p.classify_native_output(ok,b'',0),'native_verified')
        self.assertEqual(p.classify_native_output(ok,b'',2),'native_exit_nonzero')
        self.assertEqual(p.classify_native_output(b'1 romsets found, 1 were OK.\n',b'',0),
                         'native_positive_evidence_missing')

    def test_report_fake_positive_rejected(self):
        self.assertEqual(p.classify_native_output(b'romset dino is bad\n',b'',0),
                         'native_positive_evidence_missing')
        self.assertEqual(p.classify_native_output(
            b'romset dino is good\nromset other is bad\n1 romsets found, 1 were OK.\n',b'',0),
                         'native_negative_evidence_present')

    def test_no_native_windows_runtime_not_reported_as_pass(self):
        if os.name=='nt':self.skipTest('native platform test only on Linux')
        self.assertEqual(p.native_verify(self.archive,self.dir/'nonexistent.exe'),
                         'not_run_no_native_windows_runtime')

    def test_missing_binary_cannot_impersonate_original(self):
        with self.assertRaisesRegex(p.PrivateProbeError,'executable_digest_mismatch'):
            p.verify_executable(self.dir/'missing.exe')

    def test_runner_sanitization_precedes_native_logic(self):
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            with self.assertRaisesRegex(p.PrivateProbeError,'public_runner_forbidden'):
                p.native_verify(self.archive,self.dir/'bad.exe')


if __name__ == '__main__':
    unittest.main()