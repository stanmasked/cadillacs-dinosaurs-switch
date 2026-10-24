"""Stage334 synthetic tests; never use original game ROMs."""
import binascii
import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

from tools import wolfmame0106_private_rom_normalize as normalizer


class PrivateRomNormalizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="stage334-rom-normalize-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.zip"
        self.driver = self.root / "dino-driver.xml"
        self.out = self.root / "private" / "dino.zip"
        (self.root / "private").mkdir()
        self.items = [
            ("board-a.bin", "main-a.rom", b"synthetic-rom-A-123"),
            ("board-b.bin", "main-b.rom", b"synthetic-rom-B-456"),
            ("board-c.bin", "gfx-c.rom", b"synthetic-rom-C-789"),
        ]
        with zipfile.ZipFile(self.source, "w", zipfile.ZIP_DEFLATED) as z:
            for source_name, _target_name, data in self.items:
                z.writestr(source_name, data)
        game = ET.Element("game", {"name": "dino"})
        for _source_name, target_name, data in self.items:
            ET.SubElement(game, "rom", {
                "name": target_name,
                "size": str(len(data)),
                "crc": f"{binascii.crc32(data) & 0xffffffff:08x}",
                "sha1": hashlib.sha1(data).hexdigest(),
                "status": "good",
            })
        root = ET.Element("mame")
        root.append(game)
        ET.ElementTree(root).write(self.driver, encoding="utf-8", xml_declaration=True)

    def test_normalizes_names_and_preserves_exact_bytes(self):
        report = normalizer.normalize(self.source, self.driver, self.out)
        self.assertEqual(report["status"], "PRIVATE_ROM_NORMALIZATION_PASS")
        self.assertEqual(report["expected_rom_count"], 3)
        self.assertEqual(report["source_regular_entry_count"], 3)
        self.assertEqual(report["normalized_entry_count"], 3)
        with zipfile.ZipFile(self.out) as z:
            self.assertEqual(z.namelist(), [x[1] for x in self.items])
            for (_src, expected, data) in self.items:
                self.assertEqual(z.read(expected), data)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.root), str(report))

    def test_missing_expected_rom_fails_without_output(self):
        broken = self.root / "broken.xml"
        broken.write_text(self.driver.read_text().replace(
            hashlib.sha1(self.items[0][2]).hexdigest(), "0" * 40))
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            normalizer.normalize(self.source, broken, self.out)
        self.assertFalse(self.out.exists())

    def test_duplicate_content_match_is_ambiguous(self):
        with zipfile.ZipFile(self.source, "a", zipfile.ZIP_DEFLATED) as z:
            z.writestr("duplicate.bin", self.items[0][2])
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            normalizer.normalize(self.source, self.driver, self.out)
        self.assertFalse(self.out.exists())

    def test_rejects_symlink_source(self):
        link = self.root / "source-link.zip"
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            normalizer.normalize(link, self.driver, self.out)

    def test_rejects_repository_output(self):
        forbidden = normalizer.ROOT / ".stage334-forbidden-rom.zip"
        with self.assertRaisesRegex(ValueError, "outside repository"):
            normalizer.normalize(self.source, self.driver, forbidden)
        self.assertFalse(forbidden.exists())

    def test_refuses_overwrite(self):
        self.out.write_bytes(b"existing")
        with self.assertRaisesRegex(ValueError, "new private path"):
            normalizer.normalize(self.source, self.driver, self.out)
        self.assertEqual(self.out.read_bytes(), b"existing")

    def test_rejects_path_traversal_archive_member(self):
        with zipfile.ZipFile(self.source, "a", zipfile.ZIP_DEFLATED) as z:
            z.writestr("../escape.bin", b"unsafe")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            normalizer.normalize(self.source, self.driver, self.out)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
