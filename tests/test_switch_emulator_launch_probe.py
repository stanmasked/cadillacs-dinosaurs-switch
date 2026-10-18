"""ROM-free host tests for conservative Switch emulator startup probing.

Use only a temporary synthetic NRO header and the system Python process;
never download emulators, keys, firmware or original game data. These tests
exercise the probe itself, NOT actual Ryujinx/Nintendo Switch emulation.
"""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

from tools import switch_emulator_launch_probe as probe


class SwitchEmulatorProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='dino-fake-nro-')
        self.nro=Path(self.temp.name)/'self-authored-fixture.nro'
        # Synthetic but structurally consistent NRO image with
        # three 4096-byte sections, no copyrighted ROM or firmware.
        contents=bytearray(0x3000)
        contents[0x10:0x14]=b'NRO0'
        struct.pack_into('<I',contents,0x18,len(contents))
        for position,offset in enumerate((0x20,0x28,0x30)):
            struct.pack_into('<II',contents,offset,position*0x1000,0x1000)
        self.nro.write_bytes(contents)

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_original_test_header(self):
        self.assertTrue(probe.check_nro(self.nro))

    def test_bad_magic_is_rejected(self):
        data=bytearray(self.nro.read_bytes())
        data[0x10:0x14]=b'BAD!'
        self.nro.write_bytes(data)
        self.assertFalse(probe.check_nro(self.nro))

    def test_truncated_and_bad_declared_sizes_are_rejected(self):
        for declared in (0,0x40,999999):
            with self.subTest(declared=declared):
                data=bytearray(256)
                data[0x10:0x14]=b'NRO0'
                struct.pack_into('<I',data,0x18,declared)
                self.nro.write_bytes(data)
                self.assertFalse(probe.check_nro(self.nro))
        self.nro.write_bytes(b'NRO0')
        self.assertFalse(probe.check_nro(self.nro))

    def test_unknown_emulator_refuses_to_run_with_safe_result(self):
        result=probe.probe('no-such-dino-emulator-executable-test',self.nro)
        self.assertEqual(result['status'],'EMULATOR_UNAVAILABLE')
        self.assertFalse(result['process_launched'])
        self.assertFalse(result['rendering_verified'])
        self.assertNotIn(str(self.nro),str(result))

    def test_invalid_nro_prevents_even_an_available_executable_launch(self):
        self.nro.write_bytes(b'untrusted')
        result=probe.probe(sys.executable,self.nro)
        self.assertEqual(result['status'],'INVALID_NRO')
        self.assertFalse(result['process_launched'])

    def test_observation_window_rejects_bad_runtime_before_start(self):
        for value in (0,-1,121):
            with self.subTest(runtime=value):
                result=probe.probe(sys.executable,self.nro,runtime=value)
                self.assertEqual(result['status'],'INVALID_RUNTIME')
                self.assertFalse(result['process_launched'])

    def test_process_that_exits_early_is_not_emulator_pass(self):
        # Python stands in for the external executable. This tests only
        # the probe's refusal logic, NOT Switch application compatibility.
        result=probe.probe(sys.executable,self.nro,runtime=.3,
                           extra_args=('-c','pass'))
        self.assertEqual(result['status'],'EMULATOR_EARLY_EXIT')
        self.assertTrue(result['process_launched'])
        self.assertFalse(result['process_survived_window'])

    def test_long_lived_mock_does_not_prove_rendering_or_audio(self):
        result=probe.probe(sys.executable,self.nro,runtime=.25,
                           extra_args=('-c','import time; time.sleep(5)'))
        self.assertEqual(result['status'],'PROCESS_ALIVE_RENDER_UNVERIFIED')
        self.assertTrue(result['process_launched'])
        self.assertTrue(result['process_survived_window'])
        for field in ('rendering_verified','audio_verified',
                      'controller_verified'):
            self.assertFalse(result[field])
        self.assertNotIn(str(self.nro),json.dumps(result))

    def test_all_executable_segments_are_checked_not_only_magic(self):
        original=self.nro.read_bytes()
        for offset,start,length in (
                (0x20,0,0),
                (0x20,0x1000,0x1000),
                (0x28,0x0000,0x1000),
                (0x28,0x1001,0x1000),
                (0x28,0x1000,0),
                (0x30,0x2000,0x2000),
                (0x30,0x1000,0x1000)):
            with self.subTest(offset=offset,start=start,length=length):
                changed=bytearray(original)
                struct.pack_into('<II',changed,offset,start,length)
                self.nro.write_bytes(changed)
                self.assertFalse(probe.check_nro(self.nro))
        self.nro.write_bytes(original)
        self.assertTrue(probe.check_nro(self.nro))

    def test_invalid_nro_alignment_is_refused(self):
        b=bytearray(self.nro.read_bytes())
        struct.pack_into('<I',b,0x18,0x3001)
        self.nro.write_bytes(b)
        self.assertFalse(probe.check_nro(self.nro))

    def test_nro_symlink_is_refused_without_following(self):
        link=Path(self.temp.name)/'shortcut.nro'
        try:
            link.symlink_to(self.nro)
        except (OSError,NotImplementedError):
            self.skipTest('Symlinks not supported by this host')
        self.assertFalse(probe.check_nro(link))

    def test_correct_optional_sha256_is_required_before_process_launch(self):
        digest=hashlib.sha256(self.nro.read_bytes()).hexdigest()
        result=probe.probe('no-such-dino-emulator-executable-test',
                           self.nro,sha256=digest.upper())
        self.assertTrue(result['nro_sha256_matches'])
        self.assertEqual(result['status'],'EMULATOR_UNAVAILABLE')
        self.assertNotIn(digest,result.__str__())

    def test_mismatched_sha256_refuses_before_emulator_execution(self):
        wrong='0'*64
        result=probe.probe(sys.executable,self.nro,sha256=wrong)
        self.assertFalse(result['nro_sha256_matches'])
        self.assertFalse(result['process_launched'])
        self.assertEqual(result['status'],'NRO_CHECKSUM_MISMATCH')
        self.assertFalse(result['rendering_verified'])

    def test_malformed_checksum_argument_fails_closed(self):
        for invalid in ('0','g'*64,' ','-1'):
            with self.subTest(invalid=invalid):
                result=probe.probe(sys.executable,self.nro,sha256=invalid)
                self.assertEqual(result['status'],'INVALID_CHECKSUM_ARGUMENT')
                self.assertFalse(result['process_launched'])

    def test_cli_checksum_mismatch_has_only_safe_boolean_evidence(self):
        buf=io.StringIO()
        digest='0'*64
        with contextlib.redirect_stdout(buf):
            code=probe.main(['--emulator',sys.executable,
                             '--nro',str(self.nro),'--sha256',digest])
        self.assertEqual(code,2)
        report=json.loads(buf.getvalue())
        self.assertFalse(report['nro_sha256_matches'])
        self.assertEqual(report['status'],'NRO_CHECKSUM_MISMATCH')
        self.assertNotIn(str(self.nro),buf.getvalue())

    def test_cli_output_contains_only_safe_machine_readable_fields(self):
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf):
            code=probe.main(['--emulator',
                             'no-such-dino-emulator-executable-test',
                             '--nro',str(self.nro)])
        self.assertEqual(code,2)
        result=json.loads(buf.getvalue())
        self.assertEqual(result['schema'],'dino-emulator-launch-v2')
        self.assertEqual(result['status'],'EMULATOR_UNAVAILABLE')
        self.assertNotIn(str(self.nro),buf.getvalue())


if __name__=='__main__':
    unittest.main()
