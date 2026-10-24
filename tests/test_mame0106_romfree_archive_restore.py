"""No original ROM, gameplay capture, or private data in these tests."""
import hashlib
from pathlib import Path
import stat
import struct
import tempfile
import unittest
import zipfile

from tools import mame0106_romfree_archive_restore as p


class ArchiveRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        exe = bytearray(0x90)
        exe[:2] = b"MZ"
        struct.pack_into("<I", exe, 0x3C, 0x80)
        exe[0x80:0x86] = b"PE\x00\x00\x4c\x01"
        self.files = {name: name.encode() for name in p.CONTENTS}
        self.files["mame0106.exe"] = bytes(exe)
        self.files["source-pin.txt"] = (p.SOURCE_PIN + "\n").encode()
        self.files["SHA256SUMS.txt"] = b"".join(
            hashlib.sha256(self.files[name]).hexdigest().encode() + b" *" + name.encode() + b"\n"
            for name in sorted(p.FILES))
        self.zip = self.root / "bundle.zip"
        self.build_zip()

    def build_zip(self, names=None, symlink=None):
        with zipfile.ZipFile(self.zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name in (sorted(self.files) if names is None else names):
                if name == symlink:
                    info = zipfile.ZipInfo(name)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, self.files[name])
                else:
                    archive.writestr(name, self.files.get(name, b"synthetic"))
        self.zip_sha = hashlib.sha256(self.zip.read_bytes()).hexdigest()
        self.exe_sha = hashlib.sha256(self.files["mame0106.exe"]).hexdigest()

    def audit(self, **kwargs):
        return p.audit(self.zip, archive_sha=self.zip_sha, exe_sha=self.exe_sha, **kwargs)

    def test_complete_zip_passes_offline(self):
        self.assertEqual(self.audit()["members_verified"], 12)

    def test_pinned_archive_sha_is_mandatory(self):
        with self.assertRaisesRegex(p.ArchiveError, "archive_digest_mismatch"):
            p.audit(self.zip)

    def test_extra_entry_rejected(self):
        self.build_zip(names=sorted(self.files) + ["rom.bin"])
        with self.assertRaisesRegex(p.ArchiveError, "unexpected_inventory"):
            self.audit()

    def test_traversal_rejected(self):
        self.build_zip(names=sorted(self.files)[:-1] + ["../private.rom"])
        with self.assertRaises(p.ArchiveError):
            self.audit()

    def test_symlink_rejected(self):
        self.build_zip(symlink="mame0106.exe")
        with self.assertRaisesRegex(p.ArchiveError, "unsafe_archive_member"):
            self.audit()

    def test_digest_tampering_rejected(self):
        self.files["mame0106-help.txt"] = b"tampered"
        self.build_zip()
        with self.assertRaisesRegex(p.ArchiveError, "member_digest_mismatch"):
            self.audit()

    def test_source_pin_rejected(self):
        self.files["source-pin.txt"] = b"source_commit=wrong\n"
        self.build_zip()
        with self.assertRaisesRegex(p.ArchiveError, "source_pin_mismatch"):
            self.audit()

    def test_unpacked_budget_rejected(self):
        with self.assertRaisesRegex(p.ArchiveError, "oversized_archive_contents"):
            self.audit(max_unpacked=10)

    def test_existing_destination_refused(self):
        destination = self.root / "existing"
        destination.mkdir()
        with self.assertRaisesRegex(p.ArchiveError, "destination_already_exists"):
            p.restore(self.zip, destination)

    def test_correct_bundle_can_be_restored(self):
        destination = self.root / "restored"
        p.restore(self.zip, destination, archive_sha=self.zip_sha, exe_sha=self.exe_sha)
        self.assertEqual(set(f.name for f in destination.iterdir()), p.CONTENTS)
        self.assertEqual((destination / "mame0106.exe").read_bytes(), self.files["mame0106.exe"])

    def test_restoration_defaults_pin_real_zip(self):
        with self.assertRaisesRegex(p.ArchiveError, "archive_digest_mismatch"):
            p.restore(self.zip, self.root / "restored")
        self.assertFalse((self.root / "restored").exists())


if __name__ == "__main__":
    unittest.main()
