"""Compile and execute a ROM-free mock of the MAME 0.289 CPS-1 OBJ probe.

This is a *generated C++ smoke test*, not a full MAME build. The
instrumentation body comes from the actual production source generator.
The fake cps_state emulates only member shapes needed for compilation.
"""
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest

from tools.mame_obj_source_probe import instrument
from tools.mame_obj_latch_evidence import latch_counter_diagnostic, obj_fnv1a64


MOCK_HEADER = r"""
#pragma once
#include <cstdint>
#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <memory>

struct screen_device {
    explicit screen_device(unsigned long long n) : number(n) {}
    unsigned long long frame_number() const { return number; }
    unsigned long long number;
};
struct bitmap_ind16 {};
struct rectangle {};
struct test_system { const char* name; };
struct test_machine {
    const char* system_name;
    test_system system() const { return {system_name}; }
};
inline void osd_printf_warning(const char* fmt, ...) {
    va_list args;
    va_start(args, fmt);
    std::vfprintf(stderr, fmt, args);
    va_end(args);
}
class cps_state {
public:
    unsigned m_obj_size = 0x800;
    const char* game_name = "dino";
    std::uint16_t m_obj[1024]{};
    std::unique_ptr<std::uint16_t[]> m_buffered_obj{
        new std::uint16_t[1024]{}
    };
    std::uint16_t m_cps_a_regs[32]{};
    std::uint16_t m_cps_b_regs[32]{};

    test_machine machine() const { return {game_name}; }
    void find_last_sprite() {}
    void cps1_update_transmasks() {}
    void cps1_objram_latch(int state);
    std::uint32_t screen_update_cps1(
        screen_device &screen, bitmap_ind16 &bitmap, const rectangle &cliprect);
};
"""


MOCK_CPP = """#include "emu.h"
#include "cps1.h"

void cps_state::cps1_objram_latch(int state)
{
    if (state)
    {
        // CPS1 sprites have to be delayed one frame
\t\tmemcpy(m_buffered_obj.get(), m_obj, m_obj_size);
    }
}

uint32_t cps_state::screen_update_cps1(screen_device &screen,
        bitmap_ind16 &bitmap, const rectangle &cliprect)
{
    (void)bitmap;
    (void)cliprect;
\tfind_last_sprite();

\tcps1_update_transmasks();
    return 0;
}

int main()
{
    std::filesystem::create_directory("cps1-captures");
    cps_state c;
    bitmap_ind16 bitmap;
    rectangle clip;
    for (unsigned i = 0; i < 1024; ++i)
        c.m_obj[i] = static_cast<uint16_t>(i * 19U + 3U);
    c.cps1_objram_latch(1);
    for (unsigned n : {900U, 902U}) {
        screen_device screen(n);
        c.screen_update_cps1(screen, bitmap, clip);
    }
    // Changes in unlatched m_obj do not change rendered m_buffered_obj.
    c.m_obj[0] = 0xbeef;
    c.cps1_objram_latch(0);
    c.cps1_objram_latch(1);
    for (unsigned n : {904U, 906U}) {
        screen_device screen(n);
        c.screen_update_cps1(screen, bitmap, clip);
    }
    // A pre-existing register file must block all 3 frame outputs.
    std::FILE* guard = std::fopen(
        "cps1-captures/frame-00000908.render-regs-be.bin", "wb");
    if (!guard) return 31;
    std::fputs("owned", guard);
    std::fclose(guard);
    screen_device guarded(908);
    c.screen_update_cps1(guarded, bitmap, clip);

    // Captures outside the dino driver must be absent.
    c.game_name = "other";
    screen_device other(910);
    c.screen_update_cps1(other, bitmap, clip);

    // Repeating an already-captured frame must not overwrite any file.
    c.game_name = "dino";
    c.m_buffered_obj[0] = 0xffff;
    screen_device old(900);
    c.screen_update_cps1(old, bitmap, clip);
    return 0;
}
"""


class GeneratedMameProbeCppSmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = instrument(MOCK_CPP)
        (cls.root / "emu.h").write_text("#pragma once\n", encoding="utf-8")
        (cls.root / "cps1.h").write_text(MOCK_HEADER, encoding="utf-8")
        (cls.root / "instrumented.cpp").write_text(cls.source, encoding="utf-8")
        compiler = shutil.which("g++")
        if compiler is None:
            cls.tmp.cleanup()
            raise unittest.SkipTest("g++ unavailable; hosted CI must compile smoke harness")
        result = subprocess.run([
            compiler, "-std=c++17", "-O2", "-pthread", "-Wall",
            "-Wextra", "-Werror", "-pedantic",
            "instrumented.cpp", "-o", "probe-smoke",
        ], cwd=cls.root, capture_output=True, text=True, check=False)
        if result.returncode:
            cls.tmp.cleanup()
            raise AssertionError(
                "Generated MAME probe C++ failed strict compilation:\n" +
                result.stdout + result.stderr)
        result = subprocess.run(
            [str(cls.root / "probe-smoke")], cwd=cls.root,
            capture_output=True, text=True, check=False)
        if result.returncode:
            cls.tmp.cleanup()
            raise AssertionError(
                "Compiled C++ probe fixture did not run:\n" +
                result.stdout + result.stderr)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "tmp", None) is not None:
            cls.tmp.cleanup()

    def probe_path(self, frame, suffix):
        return self.root / "cps1-captures" / f"frame-{frame:08d}.{suffix}"

    def test_actual_generated_cpp_compiles_and_emits_four_complete_frames(self):
        for frame in (900, 902, 904, 906):
            with self.subTest(frame=frame):
                self.assertEqual(
                    self.probe_path(frame, "buffered-obj-be.bin").stat().st_size,
                    2048)
                self.assertEqual(
                    self.probe_path(frame, "render-regs-be.bin").stat().st_size,
                    128)
                self.assertTrue(
                    self.probe_path(frame, "obj-latch-count.txt").is_file())

    def test_cpp_v2_digests_match_exact_emitted_buffer_bytes(self):
        objs = [self.probe_path(n, "buffered-obj-be.bin").read_bytes()
                for n in (900, 902, 904, 906)]
        self.assertEqual(objs[0], objs[1])
        self.assertEqual(objs[2], objs[3])
        self.assertNotEqual(objs[1], objs[2])
        self.assertEqual(struct.unpack_from(">H", objs[0], 0), (3,))
        self.assertEqual(struct.unpack_from(">H", objs[2], 0), (0xbeef,))
        for frame, raw in zip((900, 902, 904, 906), objs):
            line = self.probe_path(frame, "obj-latch-count.txt").read_text()
            self.assertTrue(
                line.startswith("CPS1_DINO_LATCH_V2 "), frame)
            self.assertIn(obj_fnv1a64(raw), line)
        evidence = latch_counter_diagnostic(
            self.root / "cps1-captures", 900, 4, 2,
            changed_obj_slots=[0, 1, 0], obj_frames=objs)
        self.assertEqual(evidence["observed_latch_callback_counts"],
                         [1, 1, 2, 2])
        self.assertEqual(evidence["inter_sample_callback_deltas"],
                         [0, 1, 0])
        self.assertEqual(evidence["obj_byte_fingerprint_verified_count"], 4)
        self.assertFalse(evidence["obj_latch_age_verified"])
        self.assertFalse(evidence["pixel_parity_eligible"])

    def test_existing_sidecar_blocks_entire_three_file_capture(self):
        guard = self.probe_path(908, "render-regs-be.bin")
        self.assertEqual(guard.read_bytes(), b"owned")
        self.assertFalse(self.probe_path(908, "buffered-obj-be.bin").exists())
        self.assertFalse(self.probe_path(908, "obj-latch-count.txt").exists())

    def test_nondino_driver_never_writes_obj_or_latch(self):
        for name in ("buffered-obj-be.bin", "render-regs-be.bin",
                     "obj-latch-count.txt"):
            self.assertFalse(self.probe_path(910, name).exists())

    def test_only_one_raw_buffer_read_is_used_by_digest_and_serialization(self):
        # A hash made from one read and a file made from another could
        # disagree if m_buffered_obj changes between those reads.
        self.assertEqual(
            self.source.count("m_buffered_obj[index]"), 1)
        self.assertIn("observed_obj_words[index] = word;", self.source)
        self.assertIn("const unsigned word = observed_obj_words[index];",
                      self.source)
        self.assertLess(
            self.source.index("observed_obj_words[index] = word;"),
            self.source.index("std::FILE *output = std::fopen(path, \"wb\")"))


if __name__ == "__main__":
    unittest.main()
