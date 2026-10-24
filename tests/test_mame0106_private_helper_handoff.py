"""Stage380 handoff ZIP tests use synthetic files and safe public sources only."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest
import zipfile

from tools import mame0106_private_helper_handoff as p


class SyntheticRomfreeHandoffTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "public-source"
        self.source.mkdir()
        for name in p.MODULES:
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# only synthetic Python\nVALUE = True\n",
                              encoding="utf-8")
        self.archive = self.root / "handoff.zip"
        self.revision = "a"*40

    def _build(self):
        return p.build(self.source, self.archive, self.revision)

    def _rewrite(self, change):
        with zipfile.ZipFile(self.archive) as z:
            contents = {i.filename: z.read(i) for i in z.infolist()}
        change(contents)
        self.archive.unlink()
        with zipfile.ZipFile(self.archive, "x") as z:
            for name, data in sorted(contents.items()):
                z.writestr(p._entry(name), data)

    def test_complete_romfree_bundle_hash_and_inventory(self):
        result = self._build()
        self.assertEqual(result["status"], "romfree_helper_source_only")
        self.assertEqual(result["members"], len(p.MODULES) + 2)
        self.assertEqual(result["source_revision"], self.revision)
        self.assertEqual(result["private_game_execution"], "not_executed")
        self.assertEqual(result["sha256"], hashlib.sha256(self.archive.read_bytes()).hexdigest())
        with zipfile.ZipFile(self.archive) as z:
            manifest = json.loads(z.read(p.MANIFEST))
            self.assertFalse(manifest["game_private_inputs_included"])
            self.assertFalse(manifest["mame_executable_included"])
            self.assertFalse(manifest["historical_inp_playback_executed"])
            self.assertTrue(all(x.endswith(".py") or x.startswith("STAGE380-")
                                for x in z.namelist()))
            self.assertNotIn("roms/dino.zip", z.namelist())
            self.assertNotIn("dino.inp", z.namelist())
            self.assertNotIn("dino.wlf", z.namelist())
            self.assertNotIn("mame0106.exe", z.namelist())

    def test_deterministic_bytes_for_same_revision(self):
        first = self._build()["sha256"]
        second = self.root / "second.zip"
        self.assertEqual(first, p.build(self.source, second, self.revision)["sha256"])

    def test_source_mutation_detected_even_when_zip_crc_is_good(self):
        self._build()
        name = p.MODULES[0]
        self._rewrite(lambda files: files.__setitem__(name, b"# tampered synthetic Python\n"))
        with self.assertRaisesRegex(p.HandoffError, "helper_member_digest_mismatch"):
            p.verify(self.archive)

    def test_extra_or_missing_component_rejected(self):
        for add in (True, False):
            with self.subTest(add=add):
                self.archive.unlink(missing_ok=True)
                self._build()
                if add:
                    self._rewrite(lambda files: files.__setitem__(
                        "roms/dino.zip", b"SYNTHETIC NOT A ROM"))
                else:
                    self._rewrite(lambda files: files.pop(p.MODULES[0]))
                with self.assertRaisesRegex(p.HandoffError, "archive_inventory_mismatch"):
                    p.verify(self.archive)

    def test_wrong_revision_fails_closed(self):
        self._build()
        with self.assertRaisesRegex(p.HandoffError, "invalid_helper_manifest"):
            p.verify(self.archive, expected_revision="b"*40)
        with self.assertRaisesRegex(p.HandoffError, "invalid_source_revision"):
            p.build(self.source, self.root / "bad.zip", "not-hex")

    def test_output_is_exclusive_and_existing_bytes_survive(self):
        self.archive.write_bytes(b"KEEP SYNTHETIC ORIGINAL")
        with self.assertRaisesRegex(p.HandoffError, "output_must_be_new"):
            self._build()
        self.assertEqual(self.archive.read_bytes(), b"KEEP SYNTHETIC ORIGINAL")

    def test_symlink_source_refused(self):
        name = p.MODULES[0]
        link = self.source / name
        target = self.root / "synthetic-source.py"
        target.write_text("# synthetic only\n")
        link.unlink()
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError):
            self.skipTest("Host forbids symlinks")
        with self.assertRaisesRegex(p.HandoffError, "missing_or_linked_source"):
            self._build()
        self.assertFalse(self.archive.exists())

    def test_oversized_source_refused(self):
        (self.source / p.MODULES[0]).write_bytes(b"#"*(p.MAX_SOURCE_BYTES + 1))
        with self.assertRaisesRegex(p.HandoffError, "unsafe_source_metadata"):
            self._build()

    def test_forged_manifest_false_status_rejected(self):
        self._build()
        def alter(files):
            m = json.loads(files[p.MANIFEST])
            m["game_private_inputs_included"] = True
            files[p.MANIFEST] = json.dumps(m, sort_keys=True).encode()
        self._rewrite(alter)
        with self.assertRaisesRegex(p.HandoffError, "invalid_helper_manifest"):
            p.verify(self.archive)

    def test_stage381_bundled_verifier_validates_original_zip(self):
        # Build a genuinely usable ROM-free handoff, extract into an isolated
        # workspace, then invoke only its own included verification code.
        source_root = Path(__file__).resolve().parents[1]
        self.assertEqual(p.build(source_root, self.archive, self.revision)["members"], 11)
        target = self.root / "unpacked-public-only"
        target.mkdir()
        with zipfile.ZipFile(self.archive) as z:
            self.assertEqual(set(z.namelist()), set(p.MODULES) | {
                p.MANIFEST, p.INSTRUCTIONS})
            z.extractall(target)
        proc = subprocess.run(
            [sys.executable, "-m", "tools.mame0106_private_helper_handoff",
             "--verify", str(self.archive), "--expected-revision", self.revision],
            cwd=target, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr.decode("utf-8", "replace"))
        self.assertIn(b"status=romfree_helper_source_only", proc.stdout)
        self.assertIn(b"members=11", proc.stdout)
        wrong = subprocess.run(
            [sys.executable, "-m", "tools.mame0106_private_helper_handoff",
             "--verify", str(self.archive), "--expected-revision", "b"*40],
            cwd=target, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=15)
        self.assertEqual(wrong.returncode, 2)
        self.assertIn(b"status=helper_archive_refused", wrong.stdout)

    def test_stage381_tampered_embedded_verifier_is_rejected(self):
        self._build()
        name = "tools/mame0106_private_helper_handoff.py"
        self._rewrite(lambda files: files.__setitem__(name, b"# fake verifier\n"))
        with self.assertRaisesRegex(p.HandoffError, "helper_member_digest_mismatch"):
            p.verify(self.archive)

    def test_pack_actual_public_sources_only(self):
        # This test intentionally reads only nine named public .py files.
        source_root = Path(__file__).resolve().parents[1]
        result = p.build(source_root, self.archive, self.revision)
        self.assertEqual(result["members"], 11)
        with zipfile.ZipFile(self.archive) as z:
            self.assertTrue(all(i.file_size <= p.MAX_SOURCE_BYTES
                                for i in z.infolist()))
            self.assertEqual(set(z.namelist()), set(p.MODULES) | {
                p.MANIFEST, p.INSTRUCTIONS})


if __name__ == "__main__":
    unittest.main()
