"""Synthetic negative tests only; do not claim NeXium guest execution."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_nexium_guest_natural_counter_hid_paired as paired
from tools import verify_nexium_guest_natural_counter_hid as natural
from tools import verify_nexium_guest_counter_hid_paired as staged


HEADER=','.join(natural.COLUMNS)+'\n'


def natural_row(tick):
    return ('NATURAL_HID_COUNTER,'+str(tick)+',90,134,'+
            str(129-tick)+',5,3,0,9,48,2048,1,1,1169E164EDF5FD7D\n')


class PairedNaturalCounterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.paths={}
        for mode,tick in (('baseline',119),('extra',117)):
            home=self.root/mode
            home.mkdir()
            files={label:home/label for label in (
                'natural.csv','natural.json','staged.csv','staged.json',
                'stress.json','binding.json','game.nro')}
            files['natural.csv'].write_text(
                HEADER+natural_row(tick),encoding='ascii')
            files['natural.json'].write_text(
                json.dumps(natural.verify(files['natural.csv']),
                           sort_keys=True)+'\n',encoding='ascii')
            self.paths[mode]=files
        self.out=self.root/'paired.json'

    def tearDown(self):
        self.tmp.cleanup()

    def argv(self):
        flags=[]
        for mode in ('baseline','extra'):
            for field,label in (
                ('natural-csv','natural.csv'),
                ('natural-json','natural.json'),
                ('staged-csv','staged.csv'),
                ('staged-json','staged.json'),
                ('report','stress.json'),
                ('binding','binding.json'),
                ('nro','game.nro')):
                flags+=['--'+mode+'-'+field,
                        str(self.paths[mode][label])]
        flags+=['--out',str(self.out)]
        return flags

    @staticmethod
    def prior():
        return {
            'status':staged.STATUS,
            'baseline':{
                'nro_sha256':'A'*64,
                'guest_audio_stress_sha256':'B'*64,
                'synthetic_counter_pcm_fnv64':'1169E164EDF5FD7D'},
            'extra_poll':{
                'nro_sha256':'C'*64,
                'guest_audio_stress_sha256':'D'*64,
                'synthetic_counter_pcm_fnv64':'1169E164EDF5FD7D'},
        }

    def test_realistic_two_guest_modes_differ_in_valid_impact_tick(self):
        with patch.object(paired.staged,'compare',
                          return_value=self.prior()) as mock:
            self.assertEqual(paired.main(self.argv()),0)
        self.assertEqual(mock.call_count,1)
        obj=json.loads(self.out.read_text(encoding='ascii'))
        self.assertEqual(obj['status'],paired.STATUS)
        self.assertEqual(obj['baseline']['counter_impact_tick'],119)
        self.assertEqual(obj['extra_poll']['counter_impact_tick'],117)
        self.assertTrue(obj['both_guest_modes_match_staged_pcm_fingerprint'])
        for key in ('physical_joycon_verified',
                    'live_player_arena_input_verified',
                    'actual_speaker_audio_verified',
                    'causal_audio_improvement_verified'):
            self.assertFalse(obj[key])
        # Never overwrite an existing attestation.
        with patch.object(paired.staged,'compare',return_value=self.prior()):
            self.assertEqual(paired.main(self.argv()),1)

    def test_missing_natural_csv_from_either_mode_fails_closed(self):
        for mode in ('baseline','extra'):
            with self.subTest(mode=mode):
                p=self.paths[mode]['natural.csv']
                data=p.read_bytes()
                p.unlink()
                try:
                    with patch.object(paired.staged,'compare',
                                      return_value=self.prior()):
                        self.assertEqual(paired.main(self.argv()),1)
                    self.assertFalse(self.out.exists())
                finally:
                    p.write_bytes(data)

    def test_duplicate_or_mutated_recorded_natural_json_refused(self):
        p=self.paths['extra']['natural.json']
        original=p.read_text(encoding='ascii')
        cases=(
            '{}',
            original.replace('1169E164EDF5FD7D','1169E164EDF5FD7C'),
            original.replace('"schema":','"schema":"duplicate","schema":',1),
            original+'{}',
        )
        for broken in cases:
            with self.subTest(broken=broken[:40]):
                p.write_text(broken,encoding='ascii')
                with patch.object(paired.staged,'compare',
                                  return_value=self.prior()):
                    self.assertEqual(paired.main(self.argv()),1)
                self.assertFalse(self.out.exists())
        p.write_text(original,encoding='ascii')

    def test_wrong_tick_enemy_state_or_pcm_refused(self):
        p=self.paths['baseline']['natural.csv']
        original=p.read_text(encoding='ascii')
        for broken in (
            original.replace('NATURAL_HID_COUNTER,119,',
                             'NATURAL_HID_COUNTER,129,'),
            original.replace(',90,134,',',90,135,'),
            original.replace(',10,5,3,',',9,5,3,'),
            original.replace(',2048,1,1,',',0,1,1,'),
            original.replace('1169E164EDF5FD7D','1169E164EDF5FD7C'),
        ):
            with self.subTest(broken=broken[-40:]):
                p.write_text(broken,encoding='ascii')
                with patch.object(paired.staged,'compare',
                                  return_value=self.prior()):
                    self.assertEqual(paired.main(self.argv()),1)
                self.assertFalse(self.out.exists())
        p.write_text(original,encoding='ascii')

    def test_missing_staged_proof_or_identical_mode_nro_refused(self):
        with patch.object(paired.staged,'compare',
                          side_effect=ValueError('staged guest not bound')):
            self.assertEqual(paired.main(self.argv()),1)
        self.assertFalse(self.out.exists())
        for kind in ('badstatus','samenro','badpcm'):
            with self.subTest(kind=kind):
                prior=self.prior()
                if kind=='badstatus':
                    prior['status']='INCONCLUSIVE'
                if kind=='samenro':
                    prior['extra_poll']['nro_sha256']='A'*64
                if kind=='badpcm':
                    prior['extra_poll']['synthetic_counter_pcm_fnv64']='0'*16
                with patch.object(paired.staged,'compare',
                                  return_value=prior):
                    self.assertEqual(paired.main(self.argv()),1)
                self.assertFalse(self.out.exists())

    def test_symlinked_guest_evidence_refused(self):
        p=self.paths['extra']['natural.json']
        data=p.read_bytes()
        p.unlink()
        target=self.root/'outside.json'
        target.write_bytes(data)
        p.symlink_to(target)
        with patch.object(paired.staged,'compare',return_value=self.prior()):
            self.assertEqual(paired.main(self.argv()),1)
        self.assertFalse(self.out.exists())

    def test_workflow_requires_both_guest_csv_json_and_nro_modes(self):
        y=Path('.github/workflows/nexium-guest-replay.yml').read_text(
            encoding='utf-8')
        fragment=y.split(
            'python3 tools/verify_nexium_guest_natural_counter_hid_paired.py',
            1)[1].split(
            '--out paired-natural-zr-counter-pcm-attestation.json',1)[0]
        for mode,flag in (('baseline','baseline'),('extra-poll','extra')):
            self.assertIn('--'+flag+'-natural-csv paired/'+mode+
                          '/guest-natural-counter-hid.csv',fragment)
            self.assertIn('--'+flag+'-natural-json paired/'+mode+
                          '/guest-natural-counter-hid-evidence.json',fragment)
            self.assertIn('--'+flag+'-report paired/'+mode+
                          '/guest-audio-stress-evidence.json',fragment)
            self.assertIn('--'+flag+'-nro paired/build-'+mode+
                          '/cadillacs-dinosaurs-switch.nro',fragment)
        self.assertIn(
            'paired-natural-zr-counter-pcm-attestation.json',y)


if __name__=='__main__':
    unittest.main()
