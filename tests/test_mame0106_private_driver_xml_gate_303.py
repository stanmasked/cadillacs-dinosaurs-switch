"""Stage303 entirely artificial compiled MAME XML to ROM hash tests."""
import hashlib
import json
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from tools import mame0106_private_driver_xml_gate_303 as gate303


class CompiledDinoXmlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dino303-artificial-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.xml = self.root / "invented-listxml.xml"
        self.rom = self.root / "invented-dino.zip"
        self.payloads = {
            "alpha.rom": b"synthetic Alpha original NOT A GAME",
            "beta.rom": b"synthetic Beta original NOT A GAME",
            "gamma.rom": b"synthetic Gamma original NOT A GAME",
            "delta.rom": b"synthetic Delta original NOT A GAME",
        }
        self.manifest = tuple(
            (name, len(raw), f"{zlib.crc32(raw) & 0xffffffff:08x}",
             hashlib.sha1(raw).hexdigest())
            for name, raw in self.payloads.items())
        self.layout = {
            "alpha.rom": ("cpu1", "0"),
            "beta.rom": ("gfx1", "2"),
            "gamma.rom": ("gfx1", "4"),
            "delta.rom": ("sound1", "80000"),
        }
        self.make_xml()
        self.make_zip()

    def make_xml(self, mutate=None):
        rows = []
        for name, size, crc, sha in self.manifest:
            region, offset = self.layout[name]
            rows.append(dict(name=name, size=str(size), crc=crc, sha1=sha,
                             region=region, offset=offset, status="good"))
        if mutate:
            mutate(rows)
        def entry(item):
            return "<rom " + " ".join(
                f'{key}="{value}"' for key, value in item.items()) + "/>"
        doc = ('<?xml version="1.0"?>\n<mame><game name="other">'
               '<rom name="irrelevant"/></game>'
               '<game name="dino" sourcefile="cps1.c" runnable="yes">'
               + "".join(entry(r) for r in rows) +
               '</game><game name="another"/></mame>')
        self.xml.write_text(doc)

    def make_zip(self, mutate=None):
        with zipfile.ZipFile(self.rom, "w") as archive:
            for name, raw in self.payloads.items():
                archive.writestr(name, raw if name != mutate else raw+b"!")

    def check(self):
        return gate303.audit(self.xml, self.rom, manifest=self.manifest,
                             layout=self.layout)

    def test_compiled_driver_exact_rom_identity_region_and_hash(self):
        report = self.check()
        self.assertEqual(report["status"], gate303.PASS)
        self.assertEqual(report["private_rom_members_confirmed"], 4)
        self.assertEqual(report["compiled_region_entry_counts"],
                         {"cpu1": 1, "gfx1": 2, "sound1": 1})
        self.assertFalse(report["mame_original_rom_loader_executed"])
        self.assertFalse(report["original_inp_wlf_replay_verified"])
        self.assertFalse(report["private_game_bytes_hashes_paths_exported"])
        self.assertNotIn(str(self.root), json.dumps(report))
        self.assertNotIn("synthetic Alpha", json.dumps(report))

    def test_mismatched_compiled_crc_or_sha_rejected(self):
        for key,value in (("crc","deadbeef"),("sha1","0"*40)):
            with self.subTest(key):
                self.make_xml(mutate=lambda rows: rows[0].__setitem__(key,value))
                with self.assertRaisesRegex(ValueError,"hash, placement"):
                    self.check()

    def test_wrong_region_and_offset_rejected(self):
        for key,value in (("region","cpu2"),("offset","100000")):
            with self.subTest(key):
                self.make_xml(mutate=lambda rows: rows[1].__setitem__(key,value))
                with self.assertRaisesRegex(ValueError,"hash, placement"):
                    self.check()

    def test_wrong_compiled_rom_size_rejected(self):
        self.make_xml(mutate=lambda rows: rows[0].__setitem__("size","999"))
        with self.assertRaisesRegex(ValueError,"hash, placement"):
            self.check()

    def test_compiled_rom_status_bad_rejected(self):
        self.make_xml(mutate=lambda rows: rows[0].__setitem__("status","baddump"))
        with self.assertRaisesRegex(ValueError,"hash, placement"):
            self.check()

    def test_missing_rom_in_compiled_catalog_rejected(self):
        self.make_xml(mutate=lambda rows: rows.pop())
        with self.assertRaisesRegex(ValueError,"count"):
            self.check()

    def test_duplicate_compiled_rom_member_rejected(self):
        self.make_xml(mutate=lambda rows: rows.__setitem__(1,rows[0].copy()))
        with self.assertRaisesRegex(ValueError,"duplicate"):
            self.check()

    def test_duplicate_dino_game_rejected(self):
        original = self.xml.read_text()
        original = original.replace(
            "</mame>", '<game name="dino" sourcefile="cps1.c"/></mame>')
        self.xml.write_text(original)
        with self.assertRaisesRegex(ValueError,"duplicate compiled"):
            self.check()

    def test_unexpected_clone_or_sourcefile_rejected(self):
        original = self.xml.read_text()
        self.xml.write_text(original.replace('sourcefile="cps1.c"',
                                             'sourcefile="other.c"'))
        with self.assertRaisesRegex(ValueError,"driver identity"):
            self.check()
        self.xml.write_text(original.replace('runnable="yes"',
                                             'runnable="no"'))
        with self.assertRaisesRegex(ValueError,"driver identity"):
            self.check()

    def test_entity_declaration_rejected_before_xml_parse(self):
        self.xml.write_text('<?xml version="1.0"?>'
                            '<!DOCTYPE mame [<!ENTITY x "bad">]>'
                            + self.xml.read_text().split('?>', 1)[-1])
        with self.assertRaisesRegex(ValueError,"entities forbidden"):
            self.check()

    def test_original_payload_byte_mutation_rejected_even_if_compiled_xml_same(self):
        self.make_zip(mutate="gamma.rom")
        with self.assertRaises(ValueError):
            self.check()

    def test_extra_source_zip_member_rejected(self):
        with zipfile.ZipFile(self.rom, "a") as z:
            z.writestr("other.dat", b"extra")
        with self.assertRaisesRegex(ValueError,"extra/missing"):
            self.check()

    def test_symlinked_private_evidence_files_rejected(self):
        a = self.root / "alias.xml"
        a.symlink_to(self.xml)
        with self.assertRaisesRegex(ValueError,"unsafe"):
            gate303.audit(a, self.rom, manifest=self.manifest,
                          layout=self.layout)
        b = self.root / "alias.zip"
        b.symlink_to(self.rom)
        with self.assertRaisesRegex(ValueError,"unsafe"):
            gate303.audit(self.xml, b, manifest=self.manifest,
                          layout=self.layout)

    def test_oversized_xml_refused(self):
        original = gate303.MAX_XML_BYTES
        try:
            gate303.MAX_XML_BYTES = 50
            with self.assertRaisesRegex(ValueError,"oversized"):
                self.check()
        finally:
            gate303.MAX_XML_BYTES = original

    def test_malformed_xml_not_a_positive_result(self):
        self.xml.write_text("<mame><game name='dino'>")
        with self.assertRaises(Exception):
            self.check()


if __name__ == "__main__":
    unittest.main()
