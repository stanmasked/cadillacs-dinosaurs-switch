"""Stage295: synthetic-only source-anchored Minivader ROM fixture tests."""
import hashlib
import json
import tempfile
import unittest
import zlib
from pathlib import Path

from tools import mame0106_synthetic_minivadr_fixture_295 as fixture


class SyntheticMinivaderFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dino295-fake-z80-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.driver = self.root / fixture.SOURCE_FILE
        self.driver.parent.mkdir(parents=True)
        self.original = (
            "#include \"driver.h\"\n"
            "ROM_START( minivadr )\n"
            + fixture.ORIGINAL_LINE + "\nROM_END\n"
        )
        self.driver.write_text(self.original)
        self.out = self.root / "temporary-roms"

    def test_generates_only_synthetic_z80_bytecode_in_new_directory(self):
        result = fixture.generate(self.root, self.out)
        rom = (self.out / "minivadr" / fixture.ROM_NAME).read_bytes()
        self.assertEqual(len(rom), 8192)
        self.assertEqual(rom[:11], fixture.SYNTHETIC_Z80_PROGRAM)
        self.assertEqual(rom[11:], bytes(8192 - 11))
        self.assertEqual(result["fixture_crc32"], f"{zlib.crc32(rom):08x}")
        self.assertEqual(result["fixture_sha1"], hashlib.sha1(rom).hexdigest())
        self.assertIn("CRC("+result["fixture_crc32"]+")", self.driver.read_text())
        self.assertFalse(result["actual_original_rom_or_inp_used"])
        self.assertFalse(result["original_dino_gameplay_verified"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_z80_writes_inside_real_visible_minivader_scanlines(self):
        # Upstream 0.106 vidhrdw/minivadr.c maps (address-0xa000)/32 to y.
        # The visible screen is y=16..240; old address 0xa000 drew y=0.
        code = fixture.SYNTHETIC_Z80_PROGRAM
        self.assertEqual(code[:2], bytes.fromhex("f3 21"))
        address = code[2] | (code[3] << 8)
        self.assertGreaterEqual(address, 0xa200)
        self.assertLess(address, 0xa000 + 32 * 240)
        self.assertTrue(16 <= (address - 0xa000) // 32 <= 240)
        self.assertIn(bytes.fromhex("77 3c c3"), code)

    def test_does_not_patch_changed_or_duplicate_source(self):
        self.driver.write_text("ROM_START( minivadr )\nROM_END\n")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            fixture.generate(self.root, self.out)
        self.assertFalse(self.out.exists())
        self.driver.write_text(self.original + self.original)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            fixture.generate(self.root, self.out)
        self.assertFalse(self.out.exists())

    def test_output_existing_directory_blocks_any_source_patch(self):
        self.out.mkdir()
        with self.assertRaisesRegex(ValueError, "not exist"):
            fixture.generate(self.root, self.out)
        self.assertEqual(self.driver.read_text(), self.original)

    def test_symlink_source_and_outdir_rejected(self):
        copy = self.root / "driver-copy"
        copy.write_text(self.original)
        self.driver.unlink()
        self.driver.symlink_to(copy)
        with self.assertRaisesRegex(ValueError, "regular"):
            fixture.generate(self.root, self.out)
        self.assertFalse(self.out.exists())
        self.driver.unlink()
        self.driver.write_text(self.original)
        self.out.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "not exist"):
            fixture.generate(self.root, self.out)
        self.assertEqual(self.driver.read_text(), self.original)

    def test_crlf_source_rejected_before_writing(self):
        self.driver.write_bytes(self.original.encode().replace(b"\n", b"\r\n"))
        with self.assertRaisesRegex(ValueError, "LF-normalized"):
            fixture.generate(self.root, self.out)
        self.assertFalse(self.out.exists())

    def test_second_generation_rejected_no_silent_overwrite(self):
        fixture.generate(self.root, self.out)
        original_bytes = (self.out / "minivadr" / fixture.ROM_NAME).read_bytes()
        with self.assertRaises(ValueError):
            fixture.generate(self.root, self.out)
        self.assertEqual((self.out / "minivadr" / fixture.ROM_NAME).read_bytes(),
                         original_bytes)


if __name__ == "__main__":
    unittest.main()
