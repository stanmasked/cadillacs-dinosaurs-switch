"""Stage 229: native C counter guest probe and strict CSV parser tests.

Host test fixtures do NOT prove execution inside the NeXium emulator;
the GitHub guest job is responsible for collecting the actual NRO file.
"""
import csv
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import verify_nexium_guest_counter as counter

ROOT=Path(__file__).resolve().parents[1]
DRIVER=r"""
#include "dino_guest_counter_probe.h"
#include <stdio.h>
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    FILE *out=fopen(argv[1],"wb");
    if (!out) return 3;
    int ok=dino_guest_counter_probe(out);
    if (fclose(out)) return 4;
    return ok ? 0 : 5;
}
"""


@unittest.skipUnless(shutil.which('gcc'),'GCC needed for actual guest C probe')
class GuestCounterNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dino-counter-guest-')
        d=Path(cls.tmp.name)
        driver=d/'driver.c'
        driver.write_text(DRIVER,encoding='utf-8')
        cls.exe=d/'guest-counter-host'
        result=subprocess.run([
            'gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
            '-Isource','source/dino_guest_counter_probe.c',
            'source/dino_arena.c','source/dino_sfx.c',
            'source/dino_pcm_witness.c',
            str(driver),'-o',str(cls.exe)],cwd=ROOT,
            capture_output=True,text=True)
        if result.returncode:
            raise AssertionError(result.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_probe(self,name):
        path=Path(self.tmp.name)/name
        subprocess.run([str(self.exe),str(path)],check=True)
        return path

    def test_actual_guest_c_probe_produces_exact_scripted_counter_states(self):
        path=self.run_probe('first.csv')
        result=counter.verify(path)
        self.assertEqual(result['status'],'ROM_FREE_COUNTER_TRACE_VALIDATED')
        self.assertTrue(result['counter_pcm_nonzero'])
        self.assertEqual(result['counter_pcm_fnv64'],'1169E164EDF5FD7D')
        self.assertTrue(result['wrong_facing_counter_rejected'])
        self.assertFalse(result['guest_hid_zr_verified'])
        self.assertEqual(path.read_text(encoding='ascii').count('\n'),11)
        self.assertEqual(result['invalid_impact_tick_counters_rejected'],5)

    def test_two_native_executions_are_byte_identical(self):
        a=self.run_probe('repeat1.csv')
        b=self.run_probe('repeat2.csv')
        self.assertEqual(a.read_bytes(),b.read_bytes())

    def test_verifier_rejects_counter_that_lacks_synthesized_pcm(self):
        path=self.run_probe('bad-audio.csv')
        data=path.read_text(encoding='ascii').replace(
            'COUNTER,2,5,3,0,9,48,2048,1',
            'COUNTER,2,5,3,0,9,48,2048,0')
        path.write_text(data,encoding='ascii')
        with self.assertRaises(ValueError):
            counter.verify(path)

    def test_verifier_rejects_nonzero_but_wrong_pcm_hash(self):
        path=self.run_probe('bad-pcm-hash.csv')
        raw=path.read_text(encoding='ascii')
        self.assertIn('1169E164EDF5FD7D',raw)
        for tampered in ('1169E164EDF5FD7C', 'ffffffffffffffff',
                         '1169e164edf5fd7d', 'CBF29CE484222325'):
            with self.subTest(tampered=tampered):
                path.write_text(raw.replace('1169E164EDF5FD7D',
                                            tampered),encoding='ascii')
                with self.assertRaises(ValueError):
                    counter.verify(path)

    def test_verifier_rejects_wrong_facing_that_grants_defense(self):
        path=self.run_probe('bad-defense.csv')
        data=path.read_text(encoding='ascii').replace(
            'WRONG_FACING,2,4,3,0,0,48,384,0',
            'WRONG_FACING,2,5,3,0,9,48,2048,1')
        path.write_text(data,encoding='ascii')
        with self.assertRaises(ValueError):
            counter.verify(path)

    def test_verifier_rejects_missing_duplicate_and_uncanonical_rows(self):
        path=self.run_probe('tampered.csv')
        data=path.read_text(encoding='ascii')
        for contents in (
            data.replace('ARMED,1,','ARMED,01,'),
            data.replace('RECOVERY,3,5,3,0,8,47,0,0,CBF29CE484222325\n',''),
            data.replace('RESET,0,','RESET,0,')+data.splitlines()[-1]+'\n',
            data.replace('COUNTER,2,','COUNTER,3,'),
        ):
            path.write_text(contents,encoding='ascii')
            with self.assertRaises(ValueError):
                counter.verify(path)

    def test_exact_impact_boundary_cases_reject_counter_and_apply_damage(self):
        path=self.run_probe('boundary-live.csv')
        with path.open(encoding='ascii',newline='') as src:
            records=list(csv.DictReader(src))
        self.assertEqual(len(records),10)
        expect={
            'LAST_HITSTUN':384,
            'LAST_ATTACK':384,
            'LANDING':388,   # includes a legitimate landing event
            'ATTACK_CHORD':384,
            'JUMP_CHORD':386, # includes legitimate jump-start event
        }
        for record in records:
            name=record['phase']
            if name not in expect:
                continue
            with self.subTest(phase=name):
                self.assertEqual(int(record['event_mask']),expect[name])
                self.assertEqual(int(record['event_mask']) & 2048,0)
                self.assertEqual(int(record['player_hp']),4)
                self.assertEqual(int(record['enemy_hp']),3)
                self.assertEqual(int(record['windup']),0)
                self.assertEqual(int(record['stun']),0)
                self.assertEqual(int(record['cooldown']),48)
                self.assertEqual(record['pcm_nonzero'],'0')
        self.assertEqual(counter.verify(path)['status'],
                         'ROM_FREE_COUNTER_TRACE_VALIDATED')

    def test_corrupted_last_tick_counter_proof_is_refused(self):
        path=self.run_probe('bad-boundary.csv')
        original=path.read_text(encoding='ascii')
        mutations=(
            ('LAST_HITSTUN,2,4,3,0,0,48,384,0,',
             'LAST_HITSTUN,2,5,3,0,9,48,2048,0,'),
            ('LANDING,2,4,3,0,0,48,388,0,',
             'LANDING,2,4,3,0,0,48,384,0,'),
            ('ATTACK_CHORD,2,4,3,0,0,48,384,0,',
             'ATTACK_CHORD,2,4,3,0,0,48,2048,0,'),
            ('JUMP_CHORD,2,4,3,0,0,48,386,0,',
             'JUMP_CHORD,2,4,3,0,0,48,388,0,'),
        )
        for old,new in mutations:
            self.assertIn(old,original)
            with self.subTest(field=old.split(',')[0]):
                path.write_text(original.replace(old,new),encoding='ascii')
                with self.assertRaises(ValueError):
                    counter.verify(path)

    def test_missing_and_symlinked_csv_never_pass(self):
        with self.assertRaises(ValueError):
            counter.verify(Path(self.tmp.name)/'absent.csv')
        target=self.run_probe('real.csv')
        link=Path(self.tmp.name)/'link.csv'
        link.symlink_to(target)
        with self.assertRaises(ValueError):
            counter.verify(link)


if __name__=='__main__':
    unittest.main()
