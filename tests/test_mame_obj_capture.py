"""ROM-free tests for optional MAME CPS-1 VBlank OBJ instrumentation."""
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tools.mame_obj_instrument import instrument, create_patch
from tools.mame_obj_validate import inspect, main

MAME_CPS_SNIPPET = '''// MAME CPS-1 abbreviated compile fixture
#include "emu.h"
void cps_state::cps1_objram_latch(int state)
{
    if (state)
    {
        // CPS1 sprites have to be delayed one frame
        memcpy(m_buffered_obj.get(), m_obj, m_obj_size);
    }
}
'''


class InstrumentationTests(unittest.TestCase):
    def test_exact_latch_injection(self):
        edited = instrument(MAME_CPS_SNIPPET)
        self.assertEqual(edited.count('CPS1_OBJ_DUMP_DIR'), 1)
        self.assertIn('memcpy(m_buffered_obj.get(), m_obj, m_obj_size);', edited)
        self.assertIn('m_buffered_obj[i]', edited)
        self.assertIn('std::fwrite', edited)
        self.assertIn('m_screen->frame_number()', edited)
        self.assertLess(edited.index('memcpy('), edited.index('CPS1_OBJ_DUMP_DIR'))
        for header in ('<cstdio>', '<cstdlib>', '<cstring>'):
            self.assertIn('#include ' + header, edited)

    def test_small_unified_patch(self):
        patch = create_patch(MAME_CPS_SNIPPET)
        self.assertTrue(patch.startswith('--- a/src/mame/capcom/cps1_v.cpp'))
        self.assertIn('+', patch)
        self.assertIn('m_buffered_obj[i]', patch)
        self.assertNotIn('CPS1_OBJ_DUMP_DIR', MAME_CPS_SNIPPET)

    def test_refuse_duplicate_patch(self):
        with self.assertRaisesRegex(ValueError, 'already present'):
            instrument(instrument(MAME_CPS_SNIPPET))

    def test_refuse_missing_method(self):
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            instrument('#include "emu.h"\n')

    def test_refuse_changed_memcpy(self):
        with self.assertRaisesRegex(ValueError, 'buffered-object'):
            instrument(MAME_CPS_SNIPPET.replace(
                'memcpy(m_buffered_obj.get(), m_obj, m_obj_size);', '/* removed */'))


class LatchedObjTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'dino_obj_latch_frame-00000900.be.bin'
        words = [0] * 1024
        words[7] = 0xff00
        self.path.write_bytes(struct.pack('>1024H', *words))

    def test_size_and_terminator(self):
        result = inspect(self.path)
        self.assertEqual(result['bytes'], 2048)
        self.assertEqual(result['latch_frame_number'], 900)
        self.assertEqual(result['first_terminator_slot'], 1)
        self.assertEqual(result['object_slots_before_marker'], 1)
        self.assertFalse(result['framebuffer_synchronized'])
        self.assertFalse(result['pixel_parity_eligible'])

    def test_reject_truncated_capture(self):
        self.path.write_bytes(b'\x00' * 2047)
        with self.assertRaisesRegex(ValueError, 'Expected 2048'):
            inspect(self.path)

    def test_reject_bad_name(self):
        with self.assertRaisesRegex(ValueError, 'Unrecognized'):
            inspect(self.path.with_name('frame-00000900.bin'))

    def test_do_not_overwrite_audit(self):
        output = Path(self.temp.name) / 'audit.json'
        self.assertEqual(main([str(self.path), '--output', str(output)]), 0)
        self.assertEqual(main([str(self.path), '--output', str(output)]), 2)


@unittest.skipUnless(shutil.which('g++'), 'Host C++ compiler unavailable')
class NativeCppSmoke(unittest.TestCase):
    def test_patched_latch_generates_be_buffer(self):
        patched = instrument(MAME_CPS_SNIPPET)
        patched = patched.replace('#include "emu.h"', '''#include <memory>
#include <cstdint>
struct TinyScreen { unsigned frame_number() const {return 900;} };
struct TinyMachine {
    struct Sys {const char* name="dino";};
    Sys system() const {return {};}
};
struct cps_state {
    int m_obj_size=2048;
    uint16_t m_obj[1024]{};
    std::unique_ptr<uint16_t[]> m_buffered_obj = std::make_unique<uint16_t[]>(1024);
    TinyScreen screen;
    TinyScreen *m_screen=&screen;
    TinyMachine machine() const {return {};}
    void cps1_objram_latch(int state);
};''')
        patched += '''
int main() {
    cps_state obj;
    obj.m_obj[0] = 0x1234;
    obj.m_obj[3] = 0xff00;
    obj.cps1_objram_latch(0);
    obj.cps1_objram_latch(1);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'patched.cpp'
            exe = Path(tmp) / 'patched'
            source.write_text(patched)
            built = subprocess.run(
                ['g++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                 str(source), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            env = os.environ.copy()
            env.update(CPS1_OBJ_DUMP_DIR=tmp, CPS1_OBJ_DUMP_START='900',
                       CPS1_OBJ_DUMP_COUNT='1')
            executed = subprocess.run([str(exe)], env=env,
                                      capture_output=True, text=True)
            self.assertEqual(executed.returncode, 0, executed.stderr)
            output = Path(tmp) / 'dino_obj_latch_frame-00000900.be.bin'
            self.assertEqual(output.stat().st_size, 2048)
            data = output.read_bytes()
            self.assertEqual(data[:2], b'\x12\x34')
            self.assertEqual(data[6:8], b'\xff\x00')
            self.assertEqual(inspect(output)['first_terminator_slot'], 0)


if __name__ == '__main__':
    unittest.main()
