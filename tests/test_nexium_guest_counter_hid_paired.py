"""Synthetic-only negative checks for paired real-NeXium ZR/PCM attestation.

A fake NRO mode-binding response is used ONLY in these parser tests.
It does not establish real guest execution, physical controllers or audio.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_nexium_guest_counter_hid_paired as check
from tools import verify_nexium_guest_counter_hid as guest

HEADER='phase,tick,player_hp,enemy_hp,windup,stun,cooldown,event_mask,hid_edge,pcm_nonzero,pcm_fnv64\n'
READY='READY,1,5,3,12,0,0,1,0,0,CBF29CE484222325\n'
COUNTER='HID_COUNTER,2,5,3,0,9,48,2048,1,1,1169E164EDF5FD7D\n'


class PairedGuestZRTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.paths={}
        for mode in ('baseline','extra'):
            directory=self.root/mode
            directory.mkdir()
            files={key:directory/key for key in (
                'counter.csv','counter.json','stress.json','binding.json',
                'game.nro')}
            files['counter.csv'].write_text(HEADER+READY+COUNTER,
                                            encoding='ascii')
            files['counter.json'].write_text(
                json.dumps(guest.verify(files['counter.csv']),sort_keys=True)+'\n',
                encoding='ascii')
            self.paths[mode]=files
        self.out=self.root/'paired.json'

    def tearDown(self):
        self.temp.cleanup()

    def args(self):
        a=self.paths['baseline']
        b=self.paths['extra']
        return (a['counter.csv'],a['counter.json'],a['stress.json'],
                a['binding.json'],a['game.nro'],
                b['counter.csv'],b['counter.json'],b['stress.json'],
                b['binding.json'],b['game.nro'])

    @staticmethod
    def simulated_binding(report,binding,mode,nro):
        # The real CI uses the unmocked audio-report validator, and
        # checks that each bound NRO hash actually matches its bytes.
        return {'guest_nro_sha256':'A'*64 if mode=='baseline' else 'B'*64,
                'guest_report_sha256':'C'*64 if mode=='baseline' else 'D'*64}

    def test_workflow_binds_to_guest_audio_evidence_json_not_raw_csv(self):
        # The mode attestation hashes the *verified JSON*, not the
        # guest's raw stress CSV. Exact filenames are essential.
        workflow=Path('.github/workflows/nexium-guest-replay.yml').read_text(
            encoding='utf-8')
        fragment=workflow.split(
            'python3 tools/verify_nexium_guest_counter_hid_paired.py',1)[1]
        fragment=fragment.split(
            '--out paired-real-zr-counter-pcm-attestation.json',1)[0]
        for mode,flag in (('baseline','baseline'),
                          ('extra-poll','extra')):
            self.assertIn(
                '--'+flag+'-report paired/'+mode+
                '/guest-audio-stress-evidence.json',fragment)
            self.assertNotIn(
                '--'+flag+'-report paired/'+mode+
                '/guest-audio-stress.csv',fragment)
            self.assertIn(
                '--'+flag+'-binding paired/'+mode+
                '/guest-audio-mode-binding.json',fragment)

    def test_two_independent_valid_csvs_and_recorded_jsons(self):
        with patch.object(check.paired_audio,'validate_binding',
                          side_effect=self.simulated_binding) as mock:
            result=check.compare(*self.args())
        self.assertEqual(mock.call_count,2)
        self.assertEqual(result['status'],check.STATUS)
        self.assertEqual(result['baseline']['audio_mode'],'baseline')
        self.assertEqual(result['extra_poll']['audio_mode'],'extra-poll')
        self.assertEqual(result['baseline']['synthetic_counter_pcm_fnv64'],
                         result['extra_poll']['synthetic_counter_pcm_fnv64'])
        self.assertTrue(result['guest_counter_proof_reverified_in_both_modes'])
        for claim in ('physical_controller_verified',
                      'natural_combat_counter_window_verified',
                      'speaker_audio_verified',
                      'audio_mode_causal_improvement_verified'):
            self.assertFalse(result[claim])

    def test_missing_altered_or_duplicate_recorded_json_fails_closed(self):
        f=self.paths['extra']['counter.json']
        original=f.read_text(encoding='ascii')
        for broken in (
            '{}',
            original.replace('1169E164EDF5FD7D','1169E164EDF5FD7C'),
            original.replace(
                '"schema":','"schema": "duplicate", "schema":',1),
            original+'{}',
            '',
        ):
            with self.subTest(broken=broken[:50]):
                f.write_text(broken,encoding='ascii')
                with patch.object(check.paired_audio,'validate_binding',
                                  side_effect=self.simulated_binding):
                    with self.assertRaises(ValueError):
                        check.compare(*self.args())
        f.unlink()
        with patch.object(check.paired_audio,'validate_binding',
                          side_effect=self.simulated_binding):
            with self.assertRaises(ValueError):
                check.compare(*self.args())

    def test_invalid_guest_counter_event_or_pcm_never_passes(self):
        path=self.paths['baseline']['counter.csv']
        original=path.read_text(encoding='ascii')
        for bad in (
            original.replace(',2048,1,1,',',0,1,1,'),
            original.replace('1169E164EDF5FD7D','1169E164EDF5FD7C'),
            original.replace('HID_COUNTER','READY'),
            HEADER+COUNTER,
        ):
            with self.subTest(bad=bad[-75:]):
                path.write_text(bad,encoding='ascii')
                with patch.object(check.paired_audio,'validate_binding',
                                  side_effect=self.simulated_binding):
                    with self.assertRaises(ValueError):
                        check.compare(*self.args())
        path.write_text(original,encoding='ascii')

    def test_bad_mode_binding_or_matching_nros_fail_closed(self):
        with patch.object(check.paired_audio,'validate_binding',
                          side_effect=ValueError('bad bound audio file')):
            with self.assertRaises(ValueError):
                check.compare(*self.args())
        def same_hash(*args):
            return {'guest_nro_sha256':'A'*64,
                    'guest_report_sha256':'C'*64}
        with patch.object(check.paired_audio,'validate_binding',
                          side_effect=same_hash):
            with self.assertRaisesRegex(ValueError,'identical'):
                check.compare(*self.args())

    def test_symlink_and_replaced_evidence_refused(self):
        f=self.paths['extra']['counter.csv']
        external=self.root/'external.csv'
        external.write_bytes(f.read_bytes())
        f.unlink()
        f.symlink_to(external)
        with patch.object(check.paired_audio,'validate_binding',
                          side_effect=self.simulated_binding):
            with self.assertRaises(ValueError):
                check.compare(*self.args())

    def test_cli_fails_on_missing_bound_guest_without_success_artifact(self):
        a=self.paths['baseline'];b=self.paths['extra']
        argv=[
            '--baseline-csv',str(a['counter.csv']),
            '--baseline-json',str(a['counter.json']),
            '--baseline-report',str(a['stress.json']),
            '--baseline-binding',str(a['binding.json']),
            '--baseline-nro',str(a['game.nro']),
            '--extra-csv',str(b['counter.csv']),
            '--extra-json',str(b['counter.json']),
            '--extra-report',str(b['stress.json']),
            '--extra-binding',str(b['binding.json']),
            '--extra-nro',str(b['game.nro']),
            '--out',str(self.out),
        ]
        self.assertEqual(check.main(argv),1)
        self.assertFalse(self.out.exists())
        with patch.object(check.paired_audio,'validate_binding',
                          side_effect=self.simulated_binding):
            self.assertEqual(check.main(argv),0)
        report=json.loads(self.out.read_text(encoding='ascii'))
        self.assertEqual(report['status'],check.STATUS)
        self.assertFalse(report['physical_controller_verified'])
        # Exclusive creation: never overwrite an already emitted attestation.
        with patch.object(check.paired_audio,'validate_binding',
                          side_effect=self.simulated_binding):
            self.assertEqual(check.main(argv),1)


if __name__=='__main__':
    unittest.main()
