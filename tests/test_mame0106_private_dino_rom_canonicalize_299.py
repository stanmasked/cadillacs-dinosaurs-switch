"""Stage299 ROM-free synthetic tests for private historical MAME ZIP binding.

These make tiny invented byte payloads and inject a temporary checksum
manifest. No real dino ROM bits, firmware, INP, WLF, or screenshots used.
"""
import hashlib
import json
import stat
import tempfile
import unittest
import zipfile
import zlib
from pathlib import Path

from tools import mame0106_private_dino_rom_canonicalize_299 as norm


class PrivateRomCanonicalize299Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="dino299-synthetic-")
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.source = self.folder / "invented-source.zip"
        self.dest = self.folder / "dino.zip"
        self.values = {
            "canonical-a.rom": b"synthetic byte pattern AAAA",
            "canonical-b.rom": b"synthetic byte pattern BBBB",
            "canonical-c.rom": b"synthetic byte pattern CCCC",
        }
        self.aliases = ["a.11d", "some-other.rom", "cd-hypothetical.bin"]
        self.manifest = tuple((
            name, len(data), f"{zlib.crc32(data) & 0xffffffff:08x}",
            hashlib.sha1(data).hexdigest()
        ) for name, data in self.values.items())
        self.build()

    def build(self, *, omit=None, mutate=None, extra=True, duplicate=False,
              unsafe_name=False):
        with zipfile.ZipFile(self.source, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for (name, payload), alias in zip(self.values.items(), self.aliases):
                if name == omit:
                    continue
                if name == mutate:
                    payload += b"corrupted"
                z.writestr(alias if not unsafe_name else "../" + alias, payload)
            if extra:
                z.writestr("unmatched-extra.dat", b"not an original ROM")
            if duplicate:
                z.writestr("duplicate-correct.rom", self.values["canonical-a.rom"])

    def test_expected_private_hashes_are_public_reference_only(self):
        self.assertEqual(len(norm.MANIFEST), 16)
        self.assertEqual({name for name, *_ in norm.MANIFEST}.__len__(), 16)
        self.assertTrue(all(len(h) == 40 and len(crc) == 8 for
                            name, size, crc, h in norm.MANIFEST))
        self.assertEqual(norm.MANIFEST[0][0], "cde_23a.rom")

    def test_exact_hash_match_even_when_filenames_differ(self):
        res = norm.verify_archive(self.source, manifest=self.manifest)
        self.assertEqual(res["status"], norm.MATCH)
        self.assertEqual(res["required_rom_members_matched_by_crc32_sha1"], 3)
        self.assertEqual(res["extra_source_archive_members_ignored"], 1)
        self.assertFalse(res["canonical_mame_zip_written"])
        self.assertFalse(res["actual_historical_mame_rom_loader_verified"])
        self.assertFalse(res["original_dino_gameplay_verified"])
        self.assertNotIn(str(self.folder), json.dumps(res))

    def test_new_private_canonical_archive_has_only_correct_names_and_bytes(self):
        res = norm.canonicalize(self.source, self.dest, manifest=self.manifest)
        self.assertEqual(res["status"], norm.WRITTEN)
        self.assertTrue(res["canonical_mame_zip_written"])
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o600)
        with zipfile.ZipFile(self.dest) as z:
            self.assertEqual(set(z.namelist()), set(self.values))
            for name, data in self.values.items():
                self.assertEqual(z.read(name), data)
            self.assertIsNone(z.testzip())
        self.assertNotIn(str(self.folder), json.dumps(res))

    def test_missing_rom_rejected_before_creating_any_output(self):
        self.build(omit="canonical-b.rom")
        with self.assertRaisesRegex(ValueError, "missing expected"):
            norm.canonicalize(self.source, self.dest, manifest=self.manifest)
        self.assertFalse(self.dest.exists())

    def test_changed_bytes_rejected_even_if_some_checksums_still_match(self):
        self.build(mutate="canonical-c.rom")
        with self.assertRaises(ValueError):
            norm.canonicalize(self.source, self.dest, manifest=self.manifest)
        self.assertFalse(self.dest.exists())

    def test_sha1_mismatch_rejected_when_crc_size_match(self):
        manifest = list(self.manifest)
        name, size, crc, _hash = manifest[1]
        manifest[1] = name, size, crc, "0" * 40
        with self.assertRaisesRegex(ValueError, "SHA1"):
            norm.verify_archive(self.source, manifest=tuple(manifest))

    def test_duplicate_payload_is_ambiguous_not_selected_arbitrarily(self):
        self.build(duplicate=True)
        with self.assertRaisesRegex(ValueError, "duplicate source payload"):
            norm.verify_archive(self.source, manifest=self.manifest)
        self.assertFalse(self.dest.exists())

    def test_rejects_zip_slip_member_even_if_unmatched_extra(self):
        self.build(unsafe_name=True)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            norm.verify_archive(self.source, manifest=self.manifest)

    def test_existing_destination_cannot_be_replaced(self):
        self.dest.write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "fresh"):
            norm.canonicalize(self.source, self.dest, manifest=self.manifest)
        self.assertEqual(self.dest.read_bytes(), b"preserve")

    def test_input_and_output_symlinks_refused(self):
        link = self.folder / "source-link.zip"
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "unsafe"):
            norm.verify_archive(link, manifest=self.manifest)
        self.dest.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, "fresh"):
            norm.canonicalize(self.source, self.dest, manifest=self.manifest)

    def test_expanded_size_and_member_count_budgets(self):
        original = norm.MAX_EXPANDED_BYTES
        original_count = norm.MAX_MEMBERS
        try:
            norm.MAX_EXPANDED_BYTES = 12
            with self.assertRaisesRegex(ValueError, "budget"):
                norm.verify_archive(self.source, manifest=self.manifest)
            norm.MAX_EXPANDED_BYTES = original
            norm.MAX_MEMBERS = 3
            with self.assertRaisesRegex(ValueError, "member count"):
                norm.verify_archive(self.source, manifest=self.manifest)
        finally:
            norm.MAX_EXPANDED_BYTES = original
            norm.MAX_MEMBERS = original_count

    def test_cli_failure_is_sanitized_and_no_private_content_exported(self):
        receipt = self.folder / "private-result.json"
        rc = norm.main(["--source", str(self.source), "--report", str(receipt)])
        self.assertEqual(rc, 2)  # synthetic fixture is not the real manifest
        data = json.loads(receipt.read_text())
        self.assertEqual(data["status"], norm.BLOCKED)
        self.assertNotIn(str(self.folder), receipt.read_text())
        self.assertNotIn("canonical-a.rom", receipt.read_text())
        self.assertFalse(data["original_dino_gameplay_verified"])
        self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
