"""Ensure the native Switch C decoder and Python reference return identical pixels.

This test compiles the portable C function on the host (when a C compiler
is available). All graphics data are synthetic; no MAME ROMs are included.
"""
import ctypes
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools.cps1_tiles import decode_tile

ROOT = Path(__file__).resolve().parents[1]
ROM_SIZE = 0x400000
CHAR_BYTES = 128
SAMPLE_CODES = (0, 1, 127, 128, 255, 256, 1023, 2047, 2048,
                4095, 4096, 8191, 8192, 16383, 16384, 32767)


@unittest.skipUnless(os.name == "posix" and shutil.which("cc"),
                     "A POSIX host C compiler is required for parity checks")
class NativePythonParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        library = Path(cls.temp.name) / "cps1_native.so"
        subprocess.run([
            "cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
            "-fPIC", "-shared", str(ROOT / "source" / "cps1_tile.c"),
            "-o", str(library)],
            check=True, capture_output=True, text=True)
        cls.decoder = ctypes.CDLL(str(library)).cps1_decode_tile16
        cls.decoder.argtypes = (ctypes.POINTER(ctypes.c_uint8),
                                ctypes.c_size_t, ctypes.c_size_t,
                                ctypes.POINTER(ctypes.c_uint8))
        cls.decoder.restype = ctypes.c_bool
        cls.gfx = bytearray(ROM_SIZE)
        rng = random.Random(930201)
        for code in SAMPLE_CODES:
            start = code * CHAR_BYTES
            cls.gfx[start:start + CHAR_BYTES] = rng.randbytes(CHAR_BYTES)
        cls.input = (ctypes.c_uint8 * ROM_SIZE).from_buffer(cls.gfx)

    def test_native_matches_python_for_all_sample_codes(self):
        out = (ctypes.c_uint8 * 256)()
        region = bytes(self.gfx)
        for code in SAMPLE_CODES:
            with self.subTest(code=code):
                self.assertTrue(self.decoder(self.input, ROM_SIZE, code, out))
                self.assertEqual(bytes(out), decode_tile(region, "16x16", code))

    def test_native_rejects_out_of_range_code(self):
        out = (ctypes.c_uint8 * 256)()
        self.assertFalse(self.decoder(self.input, ROM_SIZE, 32768, out))


if __name__ == "__main__":
    unittest.main()
