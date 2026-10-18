"""ROM-free host tests for conservative Switch emulator startup probing.

Use only a temporary synthetic NRO header and the system Python process;
never download emulators, keys, firmware or original game data. These tests
exercise the probe itself, NOT actual Ryujinx/Nintendo Switch emulation.
"""
import contextlib
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
        contents=bytearray(256)
        contents[0x10:0x14]=b'NRO0'
        struct.pack_into('<I',contents,0x18,len(contents))
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

    def test_cli_output_contains_only_safe_machine_readable_fields(self):
        buf=io.StringIO()
        with contextlib.redirect_stdout(buf):
            code=probe.main(['--emulator',
                             'no-such-dino-emulator-executable-test',
                             '--nro',str(self.nro)])
        self.assertEqual(code,2)
        result=json.loads(buf.getvalue())
        self.assertEqual(result['schema'],'dino-emulator-launch-v1')
        self.assertEqual(result['status'],'EMULATOR_UNAVAILABLE')
        self.assertNotIn(str(self.nro),buf.getvalue())


if __name__=='__main__':
    unittest.main()
