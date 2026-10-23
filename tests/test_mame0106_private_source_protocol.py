"""Strict synthetic MAME front-end protocol fixtures: NO game files."""
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools import mame0106_private_source_protocol as p


FRONT = r'''
{ "verifyroms", NULL, rc_set_int, &verify, NULL, VERIFY_ROMS, 0, NULL, "report romsets that have problems" },
if (strwildcmp(gamename, drivers[i]->name)) continue;
printf ("romset %s ", drivers[i]->name);
else if (res == CORRECT) { printf ("is good\n"); correct++; }
else if (res == INCORRECT) { printf ("is bad\n"); incorrect++; }
if (correct+incorrect == 0) {
    printf ("romset not found\n");
    return 1;
}
printf("%d %s found, %d were OK.\n", correct+incorrect,
        (verify & VERIFY_ROMS)? "romsets" : "samplesets", correct);
if (incorrect > 0)
    return 2;
else
    return 0;
fprintf(stderr,"%d%%\r", 100);
'''
CONFIG = '{ "readconfig", "rc", rc_bool, &readconfig, "1", 0, 0, NULL, "enable loading" },'
FILEIO = '{ "rompath", "rp", rc_string, &roms, "roms", 0, 0, NULL, "rom path" },'


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.zip = Path(self.tmp.name) / 'source.zip'
        self.members = {
            'mame0106/src/windows/fronthlp.c': FRONT.encode(),
            'mame0106/src/windows/config.c': CONFIG.encode(),
            'mame0106/src/windows/fileio.c': FILEIO.encode(),
        }

    def create(self, *, duplicate=False, exclude=None):
        if self.zip.exists():
            self.zip.unlink()
        with zipfile.ZipFile(self.zip, 'w') as z:
            for name, raw in self.members.items():
                if name != exclude:
                    z.writestr(name, raw)
                    if duplicate and name.endswith('fronthlp.c'):
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter('ignore', UserWarning)
                            z.writestr(name, raw)
        return hashlib.sha256(self.zip.read_bytes()).hexdigest()

    def synthetic_audit(self, sha):
        fixture_pins = {name: hashlib.sha256(raw).hexdigest() for name,raw in self.members.items()}
        with patch.object(p, 'private_guard'), patch.object(p, 'SOURCES', fixture_pins):
            return p.audit_zip(self.zip, expected_zip_sha=sha)

    def test_all_protocol_conditions_are_supported(self):
        res = p.verify_contract(FRONT, CONFIG, FILEIO)
        self.assertEqual(res['status'],'source_contract_pass_no_runtime_execution')
        self.assertEqual(res['checks_passed'],res['checks_total'])
        self.assertFalse(res['historic_mame_verifyroms_executed'])

    def test_zip_synthetic_roundtrip(self):
        res = self.synthetic_audit(self.create())
        self.assertTrue(res['pinned_historic_source_zip_sha256_verified'])
        self.assertEqual(res['pinned_historic_source_member_count'],3)

    def test_missing_summary_rejected(self):
        res = p.verify_contract(FRONT.replace('found, %d were OK.', 'found, %d incorrect.'),CONFIG,FILEIO)
        self.assertIn('summary_output',res['missing_checks'])

    def test_missing_rom_flag_rejected(self):
        res = p.verify_contract(FRONT.replace('"verifyroms"','"verifyroms_DISABLED"'),CONFIG,FILEIO)
        self.assertIn('verifyroms_option',res['missing_checks'])

    def test_missing_exit_guard_rejected(self):
        res = p.verify_contract(FRONT.replace('return 2;','return 0;'), CONFIG,FILEIO)
        self.assertIn('zero_when_no_incorrect',res['missing_checks'])

    def test_wrong_output_rejected(self):
        res = p.verify_contract(FRONT.replace('is good\\n','is complete\\n'),CONFIG,FILEIO)
        self.assertIn('correct_output',res['missing_checks'])

    def test_missing_rompath_rejected(self):
        res = p.verify_contract(FRONT,CONFIG,FILEIO.replace('"rompath"','"rompath_DISABLED"'))
        self.assertIn('rompath_option',res['missing_checks'])

    def test_missing_readconfig_rejected(self):
        res = p.verify_contract(FRONT,CONFIG.replace('"readconfig"','"readconfig_DISABLED"'),FILEIO)
        self.assertIn('readconfig_option',res['missing_checks'])

    def test_unpinned_source_archive_rejected(self):
        self.create()
        with patch.object(p,'private_guard'):
            with self.assertRaisesRegex(p.ProtocolRefused,'source_zip_sha256_mismatch'):
                p.audit_zip(self.zip,expected_zip_sha='0'*64)

    def test_missing_file_rejected(self):
        sha=self.create(exclude='mame0106/src/windows/config.c')
        with self.assertRaisesRegex(p.ProtocolRefused,'source_members_missing_or_duplicated'):
            self.synthetic_audit(sha)

    def test_duplicate_file_rejected(self):
        sha=self.create(duplicate=True)
        with self.assertRaisesRegex(p.ProtocolRefused,'source_members_missing_or_duplicated'):
            self.synthetic_audit(sha)

    def test_modified_content_rejected(self):
        self.create()
        old=self.members['mame0106/src/windows/fronthlp.c']
        self.members['mame0106/src/windows/fronthlp.c']=old+b'altered'
        with patch.object(p,'private_guard'), patch.object(p,'SOURCES', {k:hashlib.sha256(v).hexdigest() for k,v in {**self.members, 'mame0106/src/windows/fronthlp.c':old}.items()}):
            newsha=self.create()
            with self.assertRaisesRegex(p.ProtocolRefused,'historical_source_member_sha256_mismatch'):
                p.audit_zip(self.zip,expected_zip_sha=newsha)

    def test_public_ci_guard_refuses_before_files(self):
        with patch.dict(os.environ, {'GITHUB_ACTIONS':'true'}):
            with self.assertRaisesRegex(p.ProtocolRefused,'public_runner_forbidden'):
                p.audit_zip(self.zip)

    def test_symlink_archive_refused(self):
        self.create()
        alias=self.zip.with_name('alias.zip')
        alias.symlink_to(self.zip)
        with patch.object(p,'private_guard'):
            with self.assertRaisesRegex(p.ProtocolRefused,'unsafe_source_zip'):
                p.audit_zip(alias)

    def test_script_cannot_claim_original_inp_replay(self):
        res=p.verify_contract(FRONT,CONFIG,FILEIO,p.POWERSHELL.replace('recording_playback=not_executed','recording_playback=done'))
        self.assertIn('script_explicit_not_replay',res['missing_checks'])

    def test_script_requires_exit_zero(self):
        res=p.verify_contract(FRONT,CONFIG,FILEIO,p.POWERSHELL.replace('$process.ExitCode -eq 0','$process.ExitCode -ne 0'))
        self.assertIn('script_requires_exit_zero',res['missing_checks'])


if __name__=='__main__':
    unittest.main()
