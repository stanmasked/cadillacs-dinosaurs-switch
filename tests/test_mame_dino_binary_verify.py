"""ROM-free verification of real MAME driver metadata and CPS-1 ELF objects."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_dino_binary_verify import (
    MAX_XML_BYTES, PROBE_COMPILED_MARKER, SESSION_COMPILED_MARKER,
    SESSION_ENV_COMPILED_MARKER, inspect_binary, main,
    validate_dino_xml, verify_compiled_cps1_video_object,
    verify_linked_probe_markers,
)


def fake_xml(*, build='0.289 (mame0289)', name='dino',
             source='capcom/cps1.cpp', runnable='yes', extra=''):
    return (f'<?xml version="1.0"?>\n<mame build="{build}">'
            f'<machine name="{name}" sourcefile="{source}" runnable="{runnable}">'
            '<description>Cadillacs and Dinosaurs</description></machine>'
            f'{extra}</mame>').encode('utf-8')


class MameDinoBinaryVerificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.build = self.root / 'build' / 'some' / 'mame' / 'capcom'
        self.build.mkdir(parents=True)
        self.obj = self.build / 'cps1_v.o'
        self.obj.write_bytes(b'\x7fELF' + bytes(124) +
                             PROBE_COMPILED_MARKER + SESSION_COMPILED_MARKER +
                             SESSION_ENV_COMPILED_MARKER)

    def test_valid_0289_dino_xml_keeps_game_parity_false(self):
        result = validate_dino_xml(fake_xml())
        self.assertEqual(result['driver'], 'dino')
        self.assertEqual(result['driver_sourcefile'], 'capcom/cps1.cpp')
        self.assertTrue(result['listxml_validated'])
        self.assertFalse(result['real_game_run'])
        self.assertFalse(result['frame_sync_verified'])
        self.assertFalse(result['pixel_parity_eligible'])

    def test_embedded_mame_doctype_is_parsed_not_removed(self):
        xml = (b'<?xml version="1.0"?>\n<!DOCTYPE mame '
               b'[<!ELEMENT mame (machine*)><!ELEMENT machine ANY>]>\n'
               + fake_xml()[len(b'<?xml version="1.0"?>\n'):])
        self.assertEqual(validate_dino_xml(xml)['driver'], 'dino')

    def test_rejects_wrong_build_driver_source_and_nonrunnable(self):
        for xml in (fake_xml(build='0.290'),
                    fake_xml(name='dinou'),
                    fake_xml(source='capcom/cps2.cpp'),
                    fake_xml(runnable='no'),
                    fake_xml(extra='<machine name="dinou"/>')):
            with self.subTest(xml=xml[:70]):
                with self.assertRaises(ValueError):
                    validate_dino_xml(xml)

    def test_rejects_truncated_or_oversized_xml(self):
        for value in (b'', bytes(MAX_XML_BYTES + 1), b'<mame>',
                      '<mame/>'):
            with self.subTest(size=len(value)):
                with self.assertRaises(ValueError):
                    validate_dino_xml(value)

    def test_compiled_elf_object_must_be_real_and_nonempty(self):
        meta = verify_compiled_cps1_video_object(self.root)
        self.assertTrue(meta['compiled_cps1_video_object'])
        self.assertEqual(meta['compiled_cps1_video_object_bytes'],
                         128 + len(PROBE_COMPILED_MARKER) +
                         len(SESSION_COMPILED_MARKER) +
                         len(SESSION_ENV_COMPILED_MARKER))
        self.assertTrue(meta['compiled_instrumented_latch_v2_format'])
        self.assertTrue(meta['compiled_session_label_probe_marker'])
        self.assertTrue(meta['compiled_session_environment_probe_marker'])
        self.assertFalse(meta['instrumentation_runtime_verified'])

    def test_rejects_missing_duplicate_invalid_or_symlinked_objects(self):
        for payload in (b'', b'fake' * 50, b'\x7fELF' + bytes(14)):
            self.obj.write_bytes(payload)
            with self.subTest(case=len(payload)):
                with self.assertRaises(ValueError):
                    verify_compiled_cps1_video_object(self.root)
        self.obj.write_bytes(b'\x7fELF' + bytes(124) +
                             PROBE_COMPILED_MARKER + SESSION_COMPILED_MARKER +
                             SESSION_ENV_COMPILED_MARKER)
        duplicate = self.root / 'cps1_v.o'
        duplicate.write_bytes(self.obj.read_bytes())
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            verify_compiled_cps1_video_object(self.root)
        duplicate.unlink()
        self.obj.unlink()
        duplicate.symlink_to(self.root / 'missing.o')
        with self.assertRaises(ValueError):
            verify_compiled_cps1_video_object(self.root)

    def test_rejects_mock_elf_without_compiled_v2_marker(self):
        self.obj.write_bytes(b'\x7fELF' + bytes(300))
        with self.assertRaisesRegex(ValueError, 'lacks the generated'):
            verify_compiled_cps1_video_object(self.root)

    def test_rejects_pre_session_v2_elf_even_with_latch_marker(self):
        self.obj.write_bytes(b'\x7fELF' + bytes(124) +
                             PROBE_COMPILED_MARKER)
        with self.assertRaisesRegex(ValueError, 'session label sidecar'):
            verify_compiled_cps1_video_object(self.root)

    def test_rejects_session_sidecar_marker_without_environment_lookup(self):
        self.obj.write_bytes(b'\x7fELF' + bytes(124) +
                             PROBE_COMPILED_MARKER + SESSION_COMPILED_MARKER)
        with self.assertRaisesRegex(ValueError, 'session environment lookup'):
            verify_compiled_cps1_video_object(self.root)

    def test_linked_elf_scanner_accepts_all_markers_across_chunk_boundaries(self):
        elf = self.root / 'linked-dino'
        elf.write_bytes(b'\\x7fELF' + bytes(124) +
                        PROBE_COMPILED_MARKER + bytes(3) +
                        SESSION_COMPILED_MARKER + bytes(5) +
                        SESSION_ENV_COMPILED_MARKER)
        with patch('tools.mame_dino_binary_verify.SCAN_CHUNK_BYTES', 11):
            result = verify_linked_probe_markers(elf)
        self.assertTrue(result['linked_dino_executable_probe_markers'])
        self.assertTrue(result['linked_session_label_probe_marker'])
        self.assertTrue(result['linked_session_environment_probe_marker'])
        self.assertFalse(result['linked_probe_runtime_verified'])

    def test_linked_elf_rejects_old_v2_or_missing_environment_marker(self):
        elf = self.root / 'linked-dino'
        for payload in (PROBE_COMPILED_MARKER,
                        PROBE_COMPILED_MARKER + SESSION_COMPILED_MARKER):
            elf.write_bytes(b'\\x7fELF' + bytes(124) + payload)
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, 'session-aware'):
                    verify_linked_probe_markers(elf)

    def test_linked_elf_rejects_non_elf_and_symlink(self):
        elf = self.root / 'linked-dino'
        elf.write_bytes(b'not ELF' + bytes(124) +
                        PROBE_COMPILED_MARKER + SESSION_COMPILED_MARKER +
                        SESSION_ENV_COMPILED_MARKER)
        with self.assertRaisesRegex(ValueError, 'not ELF'):
            verify_linked_probe_markers(elf)
        link = self.root / 'linked-dino-symlink'
        link.symlink_to(elf)
        with self.assertRaisesRegex(ValueError, 'symlinked'):
            verify_linked_probe_markers(link)

    def test_valid_driver_and_object_do_not_certify_unlinked_executable(self):
        binary = self.make_fake_binary(fake_xml())
        with self.assertRaisesRegex(ValueError, 'not ELF'):
            inspect_binary(binary, self.root)

    def test_auxiliary_nonrunnable_mame_devices_are_valid(self):
        devices = ('<machine name="ym2151" sourcefile="devices/sound/ymopm.cpp" '
                   'isdevice="yes" runnable="no"><description>Yamaha</description></machine>'
                   '<machine name="qsound" sourcefile="devices/sound/qsound.cpp" '
                   'isdevice="yes" runnable="no"><description>QSound</description></machine>')
        result = validate_dino_xml(fake_xml(extra=devices))
        self.assertEqual(result['auxiliary_device_entries'], 2)
        self.assertTrue(result['listxml_validated'])

    def test_rejects_runnable_or_malformed_extra_device(self):
        invalid = [
            '<machine name="ym2151" sourcefile="devices/sound/ymopm.cpp" isdevice="yes" runnable="yes"/>',
            '<machine name="ym2151" isdevice="yes" runnable="no"/>',
            '<machine isdevice="yes" runnable="no" sourcefile="devices/sound/ymopm.cpp"/>',
        ]
        for device in invalid:
            with self.subTest(device=device):
                with self.assertRaisesRegex(ValueError, 'device'):
                    validate_dino_xml(fake_xml(extra=device))

    def test_rejects_spoofed_mame_0289_suffix(self):
        with self.assertRaisesRegex(ValueError, 'MAME version'):
            validate_dino_xml(fake_xml(build='0.289-malicious'))

    def test_rejects_missing_build_tree(self):
        with self.assertRaisesRegex(ValueError, 'missing'):
            verify_compiled_cps1_video_object(self.root / 'not-there')

    def make_fake_binary(self, xml, exit_code=0):
        executable = self.root / 'fake-mame'
        # The complete output is manufactured; this tests the checker
        # in isolation and does NOT simulate actual MAME compilation.
        code = ('#!' + sys.executable + '\n'
                'import sys\n'
                f'sys.stdout.buffer.write({xml!r})\n'
                f'raise SystemExit({exit_code})\n')
        executable.write_text(code)
        executable.chmod(0o755)
        return executable

    def test_end_to_end_subprocess_accepts_runnable_dino_metadata(self):
        binary = self.make_fake_binary(fake_xml())
        # Synthetic script exercises XML/CLI handling; it is not an ELF.
        # The real linked-ELF scanner is independently tested above and
        # exercised on official upstream MAME by full-tree GitHub Actions.
        with patch('tools.mame_dino_binary_verify.verify_linked_probe_markers',
                   return_value={'linked_dino_executable_probe_markers': True}):
            result = inspect_binary(binary, self.root)
            self.assertTrue(result['compiled_cps1_video_object'])
            self.assertTrue(result['linked_dino_executable_probe_markers'])
            self.assertTrue(result['listxml_validated'])
            self.assertFalse(result['instrumentation_runtime_verified'])
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main([str(binary), str(self.root)]), 0)

    def test_cli_rejects_bad_exit_xml_and_nonexistent_binary(self):
        for xml, rc in ((fake_xml(), 1), (fake_xml(name='dinou'), 0)):
            binary = self.make_fake_binary(xml, exit_code=rc)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(binary), str(self.root)]), 2)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.root / 'missing'), str(self.root)]), 2)

    def test_oversized_real_subprocess_stdout_fails_before_xml_parsing(self):
        binary = self.root / 'large-output'
        binary.write_text(
            '#!' + sys.executable + '\n'
            'import sys\n'
            f'sys.stdout.buffer.write(b"x" * {MAX_XML_BYTES + 1})\n')
        binary.chmod(0o755)
        with self.assertRaisesRegex(ValueError, 'exceeded the allowed size'):
            inspect_binary(binary, self.root)

    def test_empty_real_subprocess_stdout_is_rejected(self):
        binary = self.make_fake_binary(b'')
        with self.assertRaisesRegex(ValueError, 'exceeded the allowed size'):
            inspect_binary(binary, self.root)

    def test_large_stderr_does_not_prevent_valid_xml_validation(self):
        binary = self.root / 'noisy-stderr'
        binary.write_text(
            '#!' + sys.executable + '\n'
            'import sys\n'
            f'sys.stdout.buffer.write({fake_xml()!r})\n'
            'sys.stderr.buffer.write(b"warning " * 400000)\n')
        binary.chmod(0o755)
        with patch('tools.mame_dino_binary_verify.verify_linked_probe_markers',
                   return_value={'linked_dino_executable_probe_markers': True}):
            meta = inspect_binary(binary, self.root)
        self.assertTrue(meta['listxml_validated'])
        self.assertTrue(meta['compiled_instrumented_latch_v2_format'])
        self.assertFalse(meta['frame_sync_verified'])

    def test_rejects_noninteger_or_zero_metadata_timeout(self):
        binary = self.make_fake_binary(fake_xml())
        for timeout in (0, True, 121, '100'):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    inspect_binary(binary, self.root, timeout_seconds=timeout)


if __name__ == '__main__':
    unittest.main()
