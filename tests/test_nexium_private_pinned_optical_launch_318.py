"""Stage318 public tests: invented local files only, NEVER original ROM data."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from tools import nexium_private_pinned_optical_launch_318 as stage


def tiny_archive(target, *, filename="folder/nexium-gui", payload=b"MOCK EXE"):
    with tarfile.open(target,"w:gz") as tar:
        info=tarfile.TarInfo(filename)
        info.size=len(payload)
        info.mode=0o700
        tar.addfile(info,io.BytesIO(payload))


def approved_receipt():
    return {
        "status":stage.STAGE316_PASS,
        "guest_submitted_original_graphics_synthetic_frames":14,
        "host_x11_optical_original_graphics_synthetic_frames":14,
        "original_graphics_uploaded_to_public_github":False,
        "actual_original_game_executed":False,
        "physical_nintendo_switch_display_verified":False,
    }


class Stage318PinnedPrivateNeXiumSafety(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory(prefix="stage318-artificial-only-")
        self.addCleanup(d.cleanup)
        self.root=Path(d.name)
        self.nro=self.root/"private-optin.nro"
        self.nro.write_bytes(b"FAKE, NOT A REAL SWITCH EXECUTABLE")
        self.archive=self.root/"pinned-nexium.tar.gz"
        tiny_archive(self.archive)
        self.rom=self.root/"dino.zip"
        self.rom.write_bytes(b"NOT A ROM")
        self.receipt=self.root/"private-report.json"

    def pinned(self):
        return patch.multiple(stage,
            NRO_BYTES=self.nro.stat().st_size,
            NRO_SHA256=hashlib.sha256(self.nro.read_bytes()).hexdigest(),
            NEXIUM_BYTES=self.archive.stat().st_size,
            NEXIUM_SHA256=hashlib.sha256(self.archive.read_bytes()).hexdigest())

    def test_exact_pinned_file_inputs_only(self):
        with self.pinned():
            self.assertTrue(stage.preflight(self.nro,self.archive))

    def test_modified_nro_and_archive_are_rejected(self):
        with self.pinned():
            self.nro.write_bytes(self.nro.read_bytes()+b"X")
            with self.assertRaises(ValueError):
                stage.preflight(self.nro,self.archive)
        self.nro.write_bytes(b"FAKE, NOT A REAL SWITCH EXECUTABLE")
        with self.pinned():
            self.archive.write_bytes(self.archive.read_bytes()+b"X")
            with self.assertRaises(ValueError):
                stage.preflight(self.nro,self.archive)

    def test_symlink_archive_or_nro_rejected(self):
        target=self.root/"other-archive"
        target.symlink_to(self.archive)
        with self.pinned(),self.assertRaises(ValueError):
            stage._secure_regular(target,stage.NEXIUM_BYTES,stage.NEXIUM_SHA256)
        target.unlink()
        target.symlink_to(self.nro)
        with self.pinned(),self.assertRaises(ValueError):
            stage._secure_regular(target,stage.NRO_BYTES,stage.NRO_SHA256)

    def test_archive_extraction_has_one_native_host_executable(self):
        with tempfile.TemporaryDirectory(prefix="stage318-extract-") as dst:
            path=stage._extract_verified_executable(self.archive,dst)
            self.assertEqual(path.name,"nexium-gui")
            self.assertEqual(path.read_bytes(),b"MOCK EXE")

    def test_archive_path_traversal_and_special_node_refused(self):
        bad=self.root/"bad.tar.gz"
        for name in ("../../escaping", "/absolute/escaping"):
            tiny_archive(bad,filename=name)
            with tarfile.open(bad,"r:gz") as tar:
                with self.assertRaises(ValueError):
                    stage._safe_members(tar)
        with tarfile.open(bad,"w:gz") as tar:
            info=tarfile.TarInfo("unsafe-pipe")
            info.type=tarfile.FIFOTYPE
            tar.addfile(info)
        with tarfile.open(bad,"r:gz") as tar:
            with self.assertRaises(ValueError):
                stage._safe_members(tar)

    def test_absolute_symlink_target_rejected_by_safe_tar_filter(self):
        target=self.root/"bad-link.tar.gz"
        with tarfile.open(target,"w:gz") as tar:
            info=tarfile.TarInfo("folder/nexium-gui")
            info.type=tarfile.SYMTYPE
            info.linkname="/etc/passwd"
            tar.addfile(info)
        with tempfile.TemporaryDirectory() as dst:
            with self.assertRaises((tarfile.TarError,ValueError,OSError)):
                stage._extract_verified_executable(target,dst)

    def test_duplicate_host_executables_refused(self):
        target=self.root/"duplicate.tar.gz"
        with tarfile.open(target,"w:gz") as tar:
            for filename in ("a/nexium-gui","b/nexium-gui"):
                info=tarfile.TarInfo(filename)
                info.size=1
                tar.addfile(info,io.BytesIO(b"X"))
        with tempfile.TemporaryDirectory() as dst:
            with self.assertRaises(ValueError):
                stage._extract_verified_executable(target,dst)

    def test_run_mocked_private_receipt_checks_success_not_only_process_exit(self):
        def fake_execute(cmd,**kwargs):
            self.assertEqual(cmd[0],"bash")
            self.assertEqual(Path(cmd[4]),self.receipt)
            self.receipt.write_text(json.dumps(approved_receipt()))
            self.receipt.chmod(0o600)
            return SimpleNamespace(returncode=0)
        with self.pinned():
            self.assertTrue(stage.run(self.rom,self.nro,self.archive,
                                      self.receipt,execute=fake_execute))

    def test_overclaimed_host_or_gameplay_receipts_refused(self):
        for key,value in (
            ("host_x11_optical_original_graphics_synthetic_frames",13),
            ("original_graphics_uploaded_to_public_github",True),
            ("actual_original_game_executed",True),
            ("physical_nintendo_switch_display_verified",True),
        ):
            with self.subTest(field=key):
                def fake(cmd,**kwargs):
                    record=approved_receipt()
                    record[key]=value
                    self.receipt.write_text(json.dumps(record))
                    self.receipt.chmod(0o600)
                    return SimpleNamespace(returncode=0)
                with self.pinned(),self.assertRaises(ValueError):
                    stage.run(self.rom,self.nro,self.archive,
                              self.receipt,execute=fake)
                self.receipt.unlink()

    def test_bad_private_receipt_permissions_refused(self):
        def fake(cmd,**kwargs):
            self.receipt.write_text(json.dumps(approved_receipt()))
            self.receipt.chmod(0o644)
            return SimpleNamespace(returncode=0)
        with self.pinned(),self.assertRaises(ValueError):
            stage.run(self.rom,self.nro,self.archive,
                      self.receipt,execute=fake)

    def test_cli_does_not_print_sensitive_source_paths_or_hashes(self):
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            rc=stage.main([
                "--rom",str(self.rom),"--nro",str(self.nro),
                "--nexium-archive",str(self.archive),
                "--receipt",str(self.receipt)])
        self.assertEqual(rc,2)
        self.assertEqual(out.getvalue().strip(),stage.BLOCKED)
        self.assertNotIn(str(self.root),out.getvalue())
        self.assertFalse(self.receipt.exists())

    def test_existing_receipt_prevents_any_emulator_execution(self):
        self.receipt.write_text("KEEP MY PRIVATE FILE")
        calls=[]
        with self.pinned(),self.assertRaises(ValueError):
            stage.run(self.rom,self.nro,self.archive,self.receipt,
                      execute=lambda *x,**kw:calls.append(x))
        self.assertEqual(calls,[])
        self.assertEqual(self.receipt.read_text(),"KEEP MY PRIVATE FILE")


if __name__=="__main__":
    unittest.main()
