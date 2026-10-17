"""ROM-free MAME CPS-1 source probe generation checks.

No emulator, original ROM, game state, or copyrighted source file included.
"""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.mame_obj_source_probe import (
    EXPECTED_MAME_BLOB, PROBE_MARKER, git_blob_sha, instrument, main,
)

MINIMAL_SOURCE = '''#include "emu.h"
#include "cps1.h"

void cps_state::cps1_objram_latch(int state)
{
	if (state)
	{
		memcpy(m_buffered_obj.get(), m_obj, m_obj_size);
	}
}
uint32_t cps_state::screen_update_cps1(screen_device &screen,
        bitmap_ind16 &bitmap, const rectangle &cliprect)
{
\tfind_last_sprite();

\tcps1_update_transmasks();
\treturn 0;
}
'''


class MameObjSourceProbeTests(unittest.TestCase):
    def test_inserts_once_after_sprite_marker_before_priority_masks(self):
        patched = instrument(MINIMAL_SOURCE)
        self.assertEqual(patched.count(PROBE_MARKER), 1)
        self.assertLess(patched.index('find_last_sprite();'),
                        patched.index(PROBE_MARKER))
        self.assertLess(patched.index(PROBE_MARKER),
                        patched.index('cps1_update_transmasks();'))
        self.assertIn('#include <cstdio>', patched)
        self.assertIn('#include <cstring>', patched)

    def test_probe_reads_buffered_not_unlatched_obj_words(self):
        patched = instrument(MINIMAL_SOURCE)
        probe = patched[patched.index(PROBE_MARKER):]
        self.assertIn('m_buffered_obj[index]', probe)
        self.assertNotIn('m_obj[index]', probe)
        self.assertIn('m_obj_size == 0x800', probe)
        self.assertIn('std::strcmp(machine().system().name, "dino")', probe)

    def test_latch_counter_uses_actual_mame_latch_after_copy(self):
        source = instrument(MINIMAL_SOURCE)
        self.assertIn('#include <atomic>', source)
        self.assertIn('cps1_dino_obj_latch_events{0};', source)
        self.assertEqual(source.count('cps1_dino_obj_latch_events.fetch_add('), 1)
        self.assertLess(source.index('memcpy(m_buffered_obj.get(), m_obj, m_obj_size)'),
                        source.index('cps1_dino_obj_latch_events.fetch_add('))
        self.assertIn('if (std::strcmp(machine().system().name, "dino") == 0)',
                      source)
        self.assertIn('std::memory_order_relaxed', source)

    def test_video_update_records_counter_before_obj_bytes(self):
        source = instrument(MINIMAL_SOURCE)
        self.assertIn('frame-%08llu.obj-latch-count.txt', source)
        self.assertIn('CPS1_DINO_LATCH_V2 %llu %016llx\\n', source)
        self.assertIn('observed_latch_count', source)
        self.assertLess(source.index('cps1_dino_obj_latch_events.load('),
                        source.index('m_buffered_obj[index]'))
        self.assertIn('existing_latch', source)
        self.assertIn('existing || existing_registers || existing_latch', source)
        self.assertIn('std::fclose(latch_output)', source)

    def test_fingerprint_hashes_same_big_endian_obj_words_before_disk_write(self):
        source = instrument(MINIMAL_SOURCE)
        self.assertIn('14695981039346656037ULL', source)
        self.assertIn('1099511628211ULL', source)
        self.assertIn('observed_obj_fnv1a64 ^= (word >> 8) & 255U;', source)
        self.assertIn('observed_obj_fnv1a64 ^= word & 255U;', source)
        self.assertIn('CPS1_DINO_LATCH_V2', source)
        self.assertLess(source.index('observed_obj_fnv1a64 ^= (word >> 8)'),
                        source.index('std::FILE *output = std::fopen(path, "wb")'))
        self.assertLess(source.index('observed_obj_fnv1a64 ^= (word >> 8)'),
                        source.index('observed_obj_fnv1a64 ^= word & 255U'))
        self.assertLess(source.index('cps1_dino_obj_latch_events.load('),
                        source.index('observed_obj_fnv1a64 ^= (word >> 8)'))
        self.assertNotIn('CPS1_DINO_LATCH_V1 %llu', source)

    def test_latch_copy_anchor_must_be_exactly_unique(self):
        bad = MINIMAL_SOURCE.replace(
            '\t\tmemcpy(m_buffered_obj.get(), m_obj, m_obj_size);',
            '\t\tother_latch_copy();')
        with self.assertRaisesRegex(ValueError, 'anchors'):
            instrument(bad)
        with self.assertRaisesRegex(ValueError, 'anchors'):
            instrument(MINIMAL_SOURCE.replace(
                '\t\tmemcpy(m_buffered_obj.get(), m_obj, m_obj_size);',
                '\t\tmemcpy(m_buffered_obj.get(), m_obj, m_obj_size);\n'
                '\t\tmemcpy(m_buffered_obj.get(), m_obj, m_obj_size);'))

    def test_limits_frames_and_uses_exact_big_endian_words(self):
        probe = instrument(MINIMAL_SOURCE)
        self.assertIn('frame_number >= 900 && frame_number <= 910', probe)
        self.assertIn('((frame_number - 900) % 2) == 0', probe)
        self.assertIn('frame-%08llu.buffered-obj-be.bin', probe)
        self.assertIn('std::fputc((word >> 8) & 255', probe)
        self.assertIn('std::fputc(word & 255', probe)
        self.assertIn('index < 0x400', probe)

    def test_register_sidecar_reads_same_hook_as_latched_obj(self):
        patched = instrument(MINIMAL_SOURCE)
        self.assertIn('frame-%08llu.render-regs-be.bin', patched)
        self.assertIn('m_cps_a_regs[index]', patched)
        self.assertIn('m_cps_b_regs[index - 32]', patched)
        self.assertIn('index < 64', patched)
        self.assertIn('std::FILE *existing_registers', patched)
        self.assertIn('if (existing || existing_registers || existing_latch)', patched)
        self.assertLess(patched.index('m_buffered_obj[index]'),
                        patched.index('m_cps_a_regs[index]'))
        self.assertLess(patched.index('m_cps_b_regs[index - 32]'),
                        patched.index('cps1_update_transmasks();'))

    def test_existing_capture_file_causes_no_overwrite(self):
        probe = instrument(MINIMAL_SOURCE)
        self.assertIn('std::fopen(path, "rb")', probe)
        self.assertIn('if (existing)', probe)
        self.assertIn('std::fopen(path, "wb")', probe)

    def test_duplicate_or_missing_anchors_fail_closed(self):
        for source in (MINIMAL_SOURCE + MINIMAL_SOURCE,
                       MINIMAL_SOURCE.replace('find_last_sprite();', 'noop();'),
                       MINIMAL_SOURCE.replace('#include "cps1.h"', ''),
                       MINIMAL_SOURCE.replace('cps1_objram_latch', 'other')):
            with self.subTest(size=len(source)):
                with self.assertRaises(ValueError):
                    instrument(source)

    def test_already_instrumented_source_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'already instrumented'):
            instrument(instrument(MINIMAL_SOURCE))

    def test_git_blob_hash_matches_git_sha1_definition(self):
        data = b'hello\n'
        raw = b'blob ' + str(len(data)).encode() + b'\0' + data
        self.assertEqual(git_blob_sha(data), hashlib.sha1(raw).hexdigest())
        self.assertEqual(len(EXPECTED_MAME_BLOB), 40)

    def test_cli_refuses_unverified_source_version_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'cps1_v.cpp'
            output = Path(directory)/'instrumented.cpp'
            source.write_text(MINIMAL_SOURCE)
            self.assertEqual(main([str(source), '--out', str(output)]), 2)
            self.assertFalse(output.exists())

    def test_cli_writes_new_copy_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'cps1_v.cpp'
            output = Path(directory)/'instrumented.cpp'
            source.write_text(MINIMAL_SOURCE)
            pristine = source.read_bytes()
            with patch('tools.mame_obj_source_probe.EXPECTED_MAME_BLOB',
                       git_blob_sha(pristine)):
                self.assertEqual(main([str(source), '--out', str(output)]), 0)
                self.assertEqual(source.read_bytes(), pristine)
                self.assertEqual(output.read_text(), instrument(MINIMAL_SOURCE))
                self.assertEqual(main([str(source), '--out', str(output)]), 2)
                self.assertEqual(source.read_bytes(), pristine)

    def test_cli_rejects_source_equal_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'cps1_v.cpp'
            source.write_text(MINIMAL_SOURCE)
            pristine = source.read_bytes()
            with patch('tools.mame_obj_source_probe.EXPECTED_MAME_BLOB',
                       git_blob_sha(pristine)):
                self.assertEqual(main([str(source), '--out', str(source)]), 2)
                self.assertEqual(source.read_bytes(), pristine)


if __name__ == '__main__':
    unittest.main()
