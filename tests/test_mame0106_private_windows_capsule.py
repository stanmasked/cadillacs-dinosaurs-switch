"""Pure synthetic regression tests. No actual game files or Windows binaries."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import mame0106_private_windows_capsule as p


class CapsuleTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        root = Path(self.workspace.name)
        self.exe = root/'dummy.exe'
        self.rom = root/'dino.zip'
        self.xml = root/'listxml.xml'
        self.out = root/'capsule.zip'
        self.exe.write_bytes(b'MZ' + b'synthetic binary' * 2048)
        self.rom.write_bytes(b'PK' + b'synthetic zip contents, not ROM' * 64)
        self.xml.write_bytes(b'<mame><game name="dino"/></mame>')
        self.exesha = p.hashfile(self.exe)[0]
        self.romsha = p.hashfile(self.rom)[0]
        self.xmlsha = p.hashfile(self.xml)[0]
        self.calls = []

    def _fakeexe(self, f, digest):
        self.assertEqual(digest,self.exesha)
        self.calls.append('exe_checked')

    def _fakeaudit(self, f, xml, *, rom_sha, xml_sha):
        self.assertEqual((rom_sha,xml_sha),(self.romsha,self.xmlsha))
        self.calls.append('rom_audited')

    def build(self):
        # ONLY synthetic inputs bypass the public runner guard in this fixture.
        with patch.object(p, 'guard_private'):
            return p.build(self.exe,self.rom,self.xml,self.out,
                           exe_sha=self.exesha,rom_sha=self.romsha,
                           xml_sha=self.xmlsha,audit=self._fakeaudit,
                           exe_check=self._fakeexe)

    def validate(self):
        with patch.object(p, 'guard_private'):
            return p.validate_capsule(self.out,archive_sha=p.hashfile(self.out)[0],
                                      exe_sha=self.exesha,rom_sha=self.romsha,
                                      xml_sha=self.xmlsha)

    def test_build_and_revalidate_synthetic(self):
        result=self.build()
        self.assertEqual(result['native_mame_execution'],'not_executed')
        self.assertEqual(self.validate()['status'],'offline_capsule_integrity_pass')
        self.assertEqual(self.calls,['exe_checked','rom_audited'])

    def test_inventory_exact(self):
        self.build()
        with zipfile.ZipFile(self.out) as z:
            self.assertEqual(set(z.namelist()),set(p.MEMBERS))
            obj=json.loads(z.read('capsule.json'))
            self.assertEqual(obj['execution_status'],'not_executed')
            self.assertEqual(obj['files']['roms/dino.zip']['sha256'],self.romsha)

    def test_output_not_overwritten(self):
        self.build()
        digest=p.hashfile(self.out)[0]
        with self.assertRaisesRegex(p.CapsuleError,'unsafe_output_location'):
            self.build()
        self.assertEqual(p.hashfile(self.out)[0],digest)

    def test_pending_copy_is_preserved(self):
        Path(str(self.out)+'.pending').write_bytes(b'previous interrupted copy')
        with self.assertRaisesRegex(p.CapsuleError,'pending_output_exists'):
            self.build()
        self.assertEqual(Path(str(self.out)+'.pending').read_bytes(),b'previous interrupted copy')

    def test_public_actions_fails_before_opening_inputs(self):
        # Unpatched guard: no output, no source files accessed on Actions.
        with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):
            with self.assertRaisesRegex(p.CapsuleError,'public_runner_forbidden'):
                p.build(self.exe,self.rom,self.xml,self.out,
                        exe_sha=self.exesha,rom_sha=self.romsha,xml_sha=self.xmlsha)
        self.assertFalse(self.out.exists())

    def test_symlink_private_input_rejected(self):
        link=self.exe.parent/'shortcut.exe'
        link.symlink_to(self.exe)
        with patch.object(p,'guard_private'):
            with self.assertRaisesRegex(p.CapsuleError,'unsafe_private_input'):
                p.build(link,self.rom,self.xml,self.out,exe_sha=self.exesha,
                        rom_sha=self.romsha,xml_sha=self.xmlsha,
                        audit=self._fakeaudit,exe_check=self._fakeexe)

    def test_modified_private_executable_rejected(self):
        self.exe.write_bytes(self.exe.read_bytes()+b'changed')
        with patch.object(p,'guard_private'):
            with self.assertRaisesRegex(p.CapsuleError,'input_sha_mismatch'):
                p.build(self.exe,self.rom,self.xml,self.out,exe_sha=self.exesha,
                        rom_sha=self.romsha,xml_sha=self.xmlsha,
                        audit=self._fakeaudit,exe_check=self._fakeexe)
        self.assertFalse(self.out.exists())

    def test_manifest_tampering_does_not_pass(self):
        self.build()
        with zipfile.ZipFile(self.out) as z:
            items={name:z.read(name) for name in z.namelist()}
        m=json.loads(items['capsule.json']);m['execution_status']='native_verified'
        items['capsule.json']=json.dumps(m).encode()
        self.out.unlink()
        with zipfile.ZipFile(self.out,'x') as z:
            for k,v in items.items():z.writestr(k,v)
        with self.assertRaisesRegex(p.CapsuleError,'invalid_capsule_manifest'):
            self.validate()

    def test_additional_members_rejected(self):
        self.build()
        with zipfile.ZipFile(self.out,'a') as z:z.writestr('unexpected.bin',b'fake')
        with self.assertRaisesRegex(p.CapsuleError,'capsule_inventory_mismatch'):
            self.validate()

    def test_damaged_member_rejected(self):
        self.build()
        with zipfile.ZipFile(self.out) as z:
            items={name:z.read(name) for name in z.namelist()}
        self.out.unlink()
        items['roms/dino.zip']=b'tampered synthetic fixture'
        with zipfile.ZipFile(self.out,'x') as z:
            for k,v in items.items():z.writestr(k,v)
        with self.assertRaisesRegex(p.CapsuleError,'capsule_member_digest_mismatch'):
            self.validate()

    def test_capsule_hash_guard(self):
        self.build()
        with patch.object(p,'guard_private'):
            with self.assertRaisesRegex(p.CapsuleError,'capsule_archive_digest_mismatch'):
                p.validate_capsule(self.out,archive_sha='0'*64,rom_sha=self.romsha,
                                   exe_sha=self.exesha,xml_sha=self.xmlsha)

    def test_runner_independent_trusted_component_pins(self):
        from tools.mame0106_private_verifyroms import PINNED_ROM_SHA256, PINNED_XML_SHA256, EXE_SHA
        for pin in (EXE_SHA, PINNED_ROM_SHA256, PINNED_XML_SHA256):
            self.assertEqual(p.POWERSHELL.count(pin), 1)
        self.assertIn("throw 'untrusted_component_pin'", p.POWERSHELL)
        self.assertIn("$manifest.files.'mame0106.exe'.sha256", p.POWERSHELL)
        self.assertIn("$manifest.files.'roms/dino.zip'.sha256", p.POWERSHELL)

    def test_windows_script_has_restricted_execution_claim(self):
        self.assertIn('WaitForExit(90000)',p.POWERSHELL)
        self.assertIn('GITHUB_ACTIONS',p.POWERSHELL)
        self.assertIn('status=native_verified',p.POWERSHELL)
        self.assertIn('recording_playback=not_executed',p.POWERSHELL)
        self.assertIn('Get-FileHash',p.POWERSHELL)
        self.assertNotIn('dino.inp',p.POWERSHELL)


if __name__ == '__main__':
    unittest.main()
