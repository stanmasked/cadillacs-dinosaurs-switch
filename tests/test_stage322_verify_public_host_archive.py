"""Stage322: toy public archive tests only, no private game ROM."""
import contextlib
import hashlib
import io
from pathlib import Path
import random
import tarfile
import tempfile
import unittest

from tools import stage322_verify_public_host_archive as provision


def fixture_tar(path, entries):
    """Compress invented pseudo-executable bytes, not an actual game."""
    with tarfile.open(path,"w:gz") as tar:
        for name,payload in entries:
            info=tarfile.TarInfo(name)
            info.size=len(payload)
            info.mode=0o755
            tar.addfile(info,io.BytesIO(payload))


class Stage322PinnedPublicHostArchiveTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix="stage322-rom-free-")
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.archive=self.root/"nexium-public-test.tar.gz"
        # Incompressible, purely fabricated bytes exceed 1KiB gate.
        generator=random.Random(322)
        self.mock_exe=generator.randbytes(4096)
        fixture_tar(self.archive,[("nexium/release/nexium-gui",self.mock_exe)])
        self.dest=self.root/"verified-executable"
    def checked(self):
        return provision.verify_and_extract(
            self.archive,self.dest,
            size=self.archive.stat().st_size,
            digest=hashlib.sha256(self.archive.read_bytes()).hexdigest())

    def test_mock_archive_is_verified_and_extracted_using_data_filter(self):
        report=self.checked()
        self.assertEqual(report["status"],provision.PASS)
        self.assertFalse(report["original_game_rom_or_graphics_used"])
        exe=self.dest/"nexium/release/nexium-gui"
        self.assertTrue(exe.is_file())
        self.assertEqual(exe.read_bytes(),self.mock_exe)

    def test_modified_archive_size_or_hash_denied_before_extract(self):
        expected_bytes=self.archive.stat().st_size
        sha=hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.archive.write_bytes(self.archive.read_bytes()+b"z")
        with self.assertRaises(ValueError):
            provision.verify_and_extract(self.archive,self.dest,
                                         size=expected_bytes,digest=sha)
        self.assertFalse(self.dest.exists())
        self.archive.write_bytes(self.archive.read_bytes()[:-1])
        with self.assertRaises(ValueError):
            provision.verify_and_extract(self.archive,self.dest,
                                         size=expected_bytes,digest="0"*64)
        self.assertFalse(self.dest.exists())

    def test_preexisting_destination_refused_no_overwrite(self):
        self.dest.mkdir()
        marker=self.dest/"keep.txt"
        marker.write_text("KEEP")
        with self.assertRaises(ValueError):
            self.checked()
        self.assertEqual(marker.read_text(),"KEEP")

    def test_archive_input_symlink_refused(self):
        alias=self.root/"symlink.tar.gz"
        alias.symlink_to(self.archive)
        with self.assertRaises(ValueError):
            provision.verify_and_extract(
                alias,self.dest,size=alias.stat().st_size,
                digest=hashlib.sha256(self.archive.read_bytes()).hexdigest())
        self.assertFalse(self.dest.exists())

    def test_archive_path_traversal_and_absolute_location_rejected(self):
        for filename in ("../../outside-nexium","/tmp/not-nexium"):
            with self.subTest(filename=filename):
                fixture_tar(self.archive,[(filename,self.mock_exe)])
                with self.assertRaises((ValueError,tarfile.TarError)):
                    self.checked()

    def test_ambiguous_executable_rejected(self):
        fixture_tar(self.archive,[("a/nexium-gui",self.mock_exe),
                                  ("b/nexium-gui",self.mock_exe)])
        with self.assertRaises(ValueError):
            self.checked()

    def test_not_an_executable_rejected(self):
        fixture_tar(self.archive,[("anything/README",self.mock_exe)])
        with self.assertRaises(ValueError):
            self.checked()

    def test_extraction_requires_bounded_tar_members(self):
        with tarfile.open(self.archive,"r:gz") as tar:
            from tools import nexium_private_pinned_optical_launch_318 as pin
            self.assertEqual(len(pin._safe_members(tar)),1)

    def test_cli_blocks_unpinned_archive_and_writes_redacted_report(self):
        output=self.root/"host.json"
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture):
            exit_code=provision.main([
                "--archive",str(self.archive),
                "--out",str(output),
                "--install-dir",str(self.dest)])
        self.assertEqual(exit_code,2)
        self.assertEqual(capture.getvalue().strip(),provision.BLOCKED)
        self.assertFalse(self.dest.exists())
        self.assertFalse(__import__("json").loads(output.read_text())
                         ["original_game_rom_or_graphics_used"])


if __name__=="__main__":
    unittest.main()
