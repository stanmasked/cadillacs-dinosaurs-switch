"""Stage282 tests use *only synthetic bytes*, never Capcom ROMs."""
import hashlib
import json
import stat
import tempfile
import unittest
import zlib
import zipfile
from pathlib import Path

from tools import wolfmame0106_private_rom_alias as alias


def sample_manifest():
    raw = {
        "first.rom": b"synthetic CPU test data A" * 13,
        "second.rom": b"synthetic graphics test data B" * 5,
        "third.rom": b"synthetic sound test data C" * 17,
    }
    expected = {
        name: (len(payload), f"{zlib.crc32(payload) & 0xffffffff:08x}",
               hashlib.sha1(payload).hexdigest())
        for name, payload in raw.items()
    }
    return raw, expected


def source_zip(path, contents):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, payload in contents:
            z.writestr(name, payload)


class PrivateHistoricalRomAliasTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="dino282-synthetic-")
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.src = self.root / "user-archive.zip"
        self.dest = self.root / "dino.zip"
        self.raw, self.expected = sample_manifest()
        source_zip(self.src, [(f"unrelated-{i}.bin", value)
                              for i, value in enumerate(self.raw.values())])

    def test_relabel_matches_exact_bytes_without_any_rom_distribution(self):
        result = alias.build(self.src, self.dest, expected=self.expected)
        self.assertEqual(result["verified_roms"], 3)
        self.assertTrue(result["source_bytes_preserved_for_matched_roms"])
        self.assertFalse(result["historical_mame0106_manifest_matched"])
        self.assertFalse(result["wolfmame_0106_executable_tested"])
        self.assertFalse(result["original_gameplay_replayed"])
        self.assertFalse(result["private_ROM_bytes_exported_to_GitHub"])
        with zipfile.ZipFile(self.dest) as out:
            self.assertEqual(set(out.namelist()), set(self.raw))
            self.assertEqual(out.testzip(), None)
            for name, value in self.raw.items():
                self.assertEqual(out.read(name), value)
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_reject_missing_required_member_without_creating_output(self):
        values = list(self.raw.values())[:-1]
        source_zip(self.src, [(f"custom-{i}.bin", value)
                              for i, value in enumerate(values)])
        with self.assertRaisesRegex(ValueError, "missing or ambiguous"):
            alias.build(self.src, self.dest, expected=self.expected)
        self.assertFalse(self.dest.exists())

    def test_reject_sha1_mismatch_even_when_crc_and_size_match(self):
        wrong = dict(self.expected)
        old = wrong["first.rom"]
        wrong["first.rom"] = (old[0], old[1], "0" * 40)
        with self.assertRaisesRegex(ValueError, "SHA-1 mismatch"):
            alias.build(self.src, self.dest, expected=wrong)
        self.assertFalse(self.dest.exists())

    def test_reject_ambiguous_duplicate_crc_and_length(self):
        a = next(iter(self.raw.values()))
        source_zip(self.src, [("a.bin", a), ("b.bin", a)] +
                   [(f"x{i}.bin", v) for i, v in
                    enumerate(list(self.raw.values())[1:])])
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            alias.build(self.src, self.dest, expected=self.expected)
        self.assertFalse(self.dest.exists())

    def test_reject_unsafe_zip_names_before_writing_output(self):
        for name in ("../outside.bin", "nested/path.bin", "bad\\path.bin"):
            with self.subTest(name=name):
                source_zip(self.src, [(name, b"foo")] +
                           [(f"ok{i}.bin", val) for i, val in
                            enumerate(self.raw.values())])
                with self.assertRaisesRegex(ValueError, "invalid"):
                    alias.build(self.src, self.dest, expected=self.expected)
                self.assertFalse(self.dest.exists())

    def test_truncated_zip_is_rejected_without_output(self):
        # Remove the end-of-central-directory marker; no original game data used.
        self.src.write_bytes(self.src.read_bytes()[:-22])
        with self.assertRaises(zipfile.BadZipFile):
            alias.build(self.src, self.dest, expected=self.expected)
        self.assertFalse(self.dest.exists())

    def test_never_overwrite_previous_private_archive(self):
        self.dest.write_bytes(b"original private archive")
        with self.assertRaises(FileExistsError):
            alias.build(self.src, self.dest, expected=self.expected)
        self.assertEqual(self.dest.read_bytes(), b"original private archive")

    def test_symlink_source_and_output_parent_rejected(self):
        source_link = self.root / "source-link.zip"
        source_link.symlink_to(self.src)
        with self.assertRaisesRegex(ValueError, "symlinks"):
            alias.build(source_link, self.dest, expected=self.expected)
        subdir = self.root / "work"
        subdir.mkdir()
        parent_link = self.root / "linked"
        parent_link.symlink_to(subdir, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            alias.build(self.src, parent_link / "dino.zip", expected=self.expected)

    def test_refuse_public_repo_destination_and_wrong_filename(self):
        with self.assertRaisesRegex(ValueError, "public repository"):
            alias.build(self.src, alias.gate.ROOT / "dino.zip",
                        expected=self.expected)
        with self.assertRaisesRegex(ValueError, "dino.zip"):
            alias.build(self.src, self.root / "not-dino.zip",
                        expected=self.expected)

    def test_duplicate_source_entry_names_are_rejected(self):
        first, second, third = self.raw.values()
        source_zip(self.src, [("same.bin", first), ("same.bin", second),
                              ("other.bin", third)])
        with self.assertRaisesRegex(ValueError, "invalid"):
            alias.build(self.src, self.dest, expected=self.expected)
        self.assertFalse(self.dest.exists())

    def test_main_fails_without_public_data_or_traceback(self):
        code = alias.main(["--source", str(self.src), "--out", str(self.dest)])
        self.assertEqual(code, 2)
        self.assertFalse(self.dest.exists())

    def test_default_historical_metadata_is_complete(self):
        self.assertEqual(len(alias.REQUIRED), 16)
        self.assertEqual(len({x[1] for x in alias.REQUIRED.values()}), 16)
        for name, (size, crc, sha1) in alias.REQUIRED.items():
            self.assertTrue(name.endswith(".rom"))
            self.assertIn(size, (131072, 524288))
            self.assertEqual(len(crc), 8)
            self.assertEqual(len(sha1), 40)


if __name__ == "__main__":
    unittest.main()
