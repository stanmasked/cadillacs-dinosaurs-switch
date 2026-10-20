"""Negative/positive Stage 247 paired-live auditor tests (fake fixtures).

Only actual NeXium NRO guest CSVs + full unmocked previous A/B/NRO
binding can prove the requested game-state input. These tests never
constitute physical controller, display, or audio evidence.
"""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import verify_nexium_guest_live_counter_hid_paired as paired
from tools import verify_nexium_guest_live_counter_hid as live
from tools import verify_nexium_guest_natural_counter_hid_paired as natural

HEADER=','.join(live.FIELDS)+'\n'


def counter(tick):
    return ('LIVE_HID_COUNTER,'+str(tick)+',90,134,'+
            str(129-tick)+',5,3,0,9,48,2048,1,1,1169E164EDF5FD7D\n')


class PairedRenderedArenaZRTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.parts={}
        for mode,tick in (('baseline',118),('extra',119)):
            folder=self.root/mode
            folder.mkdir()
            names=('live.csv','live.json','natural.csv','natural.json',
                   'staged.csv','staged.json','report.json','binding.json',
                   'compiled.nro')
            self.parts[mode]={key:folder/key for key in names}
            files=self.parts[mode]
            files['live.csv'].write_text(HEADER+counter(tick),
                                         encoding='ascii')
            files['live.json'].write_text(
                json.dumps(live.verify(files['live.csv']),sort_keys=True)+'\n',
                encoding='ascii')
        self.out=self.root/'paired-live.json'

    def tearDown(self):
        self.temp.cleanup()

    def args(self):
        args=[]
        for mode in ('baseline','extra'):
            for flag,name in (
                ('live-csv','live.csv'),('live-json','live.json'),
                ('natural-csv','natural.csv'),
                ('natural-json','natural.json'),
                ('staged-csv','staged.csv'),
                ('staged-json','staged.json'),
                ('report','report.json'),('binding','binding.json'),
                ('nro','compiled.nro')):
                args.extend(['--'+mode+'-'+flag,
                             str(self.parts[mode][name])])
        return args+['--out',str(self.out)]

    @staticmethod
    def prior():
        return {
            'status':natural.STATUS,
            'baseline':{
                'guest_nro_sha256':'A'*64,
                'audout_report_sha256':'B'*64,
                'counter_software_pcm_fnv64':'1169E164EDF5FD7D'},
            'extra_poll':{
                'guest_nro_sha256':'C'*64,
                'audout_report_sha256':'D'*64,
                'counter_software_pcm_fnv64':'1169E164EDF5FD7D'},
        }

    def run_fake_previous(self):
        with patch.object(paired.prior,'compare',return_value=self.prior()):
            return paired.main(self.args())

    def test_two_realistic_guest_live_ticks_and_no_hardware_claims(self):
        self.assertEqual(self.run_fake_previous(),0)
        obj=json.loads(self.out.read_text(encoding='ascii'))
        self.assertEqual(obj['status'],paired.STATUS)
        self.assertEqual(obj['baseline']['relative_counter_tick'],118)
        self.assertEqual(obj['extra_poll']['relative_counter_tick'],119)
        self.assertTrue(obj['both_modes_rendered_arena_counter_reverified'])
        self.assertTrue(obj['prior_natural_staged_pcm_guest_and_nro_bindings_rechecked'])
        for flag in (
            'physical_joycon_verified',
            'display_pixels_during_counter_verified',
            'speaker_audio_verified',
            'input_latency_verified',
            'audio_mode_causal_improvement_verified'):
            self.assertFalse(obj[flag])
        # Exclusive creation makes stale or overwritten attestation impossible.
        self.assertEqual(self.run_fake_previous(),1)

    def test_missing_either_guest_live_csv_or_json_fails_closed(self):
        for mode in ('baseline','extra'):
            for name in ('live.csv','live.json'):
                with self.subTest(mode=mode,name=name):
                    file=self.parts[mode][name]
                    content=file.read_bytes()
                    file.unlink()
                    try:
                        self.assertEqual(self.run_fake_previous(),1)
                        self.assertFalse(self.out.exists())
                    finally:
                        file.write_bytes(content)

    def test_altered_or_duplicate_recorded_json_fails(self):
        f=self.parts['extra']['live.json']
        original=f.read_text(encoding='ascii')
        for bad in (
            '{}',
            original.replace('1169E164EDF5FD7D','1169E164EDF5FD7C'),
            original.replace('"schema":','"schema":"duplicate","schema":',1),
            original+'{}',
            '',
        ):
            with self.subTest(payload=bad[:45]):
                f.write_text(bad,encoding='ascii')
                self.assertEqual(self.run_fake_previous(),1)
                self.assertFalse(self.out.exists())
        f.write_text(original,encoding='ascii')

    def test_bad_scene_origin_edge_health_timer_and_pcm_fail(self):
        f=self.parts['baseline']['live.csv']
        original=f.read_text(encoding='ascii')
        for raw in (
            original.replace('LIVE_HID_COUNTER,118,','LIVE_HID_COUNTER,129,'),
            original.replace('LIVE_HID_COUNTER,118,','LIVE_HID_COUNTER,116,'),
            original.replace(',90,134,',',90,135,'),
            original.replace(',11,5,3,',',10,5,3,'),
            original.replace(',5,3,0,9,48,',',4,3,0,9,48,'),
            original.replace(',2048,1,1,',',0,1,1,'),
            original.replace(',2048,1,1,',',2048,0,1,'),
            original.replace('1169E164EDF5FD7D','1169E164EDF5FD7C'),
        ):
            with self.subTest(payload=raw[-50:]):
                f.write_text(raw,encoding='ascii')
                self.assertEqual(self.run_fake_previous(),1)
                self.assertFalse(self.out.exists())
        f.write_text(original,encoding='ascii')

    def test_invalid_previous_a_b_binding_same_nro_or_wrong_pcm_fails(self):
        with patch.object(paired.prior,'compare',
                          side_effect=ValueError('bad NRO mode binding')):
            self.assertEqual(paired.main(self.args()),1)
        self.assertFalse(self.out.exists())
        for mode in ('badstatus','same-nro','bad-pcm'):
            fixture=self.prior()
            if mode=='badstatus':
                fixture['status']='INCONCLUSIVE'
            elif mode=='same-nro':
                fixture['extra_poll']['guest_nro_sha256']='A'*64
            else:
                fixture['extra_poll']['counter_software_pcm_fnv64']='0'*16
            with self.subTest(mode=mode), patch.object(
                    paired.prior,'compare',return_value=fixture):
                self.assertEqual(paired.main(self.args()),1)
                self.assertFalse(self.out.exists())

    def test_guest_csv_or_json_symlinks_rejected(self):
        for name in ('live.csv','live.json'):
            with self.subTest(name=name):
                file=self.parts['baseline'][name]
                content=file.read_bytes()
                target=self.root/('outside-'+name)
                target.write_bytes(content)
                file.unlink()
                file.symlink_to(target)
                try:
                    self.assertEqual(self.run_fake_previous(),1)
                    self.assertFalse(self.out.exists())
                finally:
                    file.unlink()
                    file.write_bytes(content)

    def test_required_workflow_binds_both_live_csv_and_json_to_nro(self):
        workflow=Path('.github/workflows/nexium-guest-replay.yml').read_text(
            encoding='utf-8')
        fragment=workflow.split(
            'python3 tools/verify_nexium_guest_live_counter_hid_paired.py',
            1)[1].split(
            '--out paired-visible-arena-zr-pcm-attestation.json',1)[0]
        for mode,flag in (('baseline','baseline'),('extra-poll','extra')):
            for kind,filename in (
                ('live-csv','guest-live-counter-hid.csv'),
                ('live-json','guest-live-counter-hid-evidence.json'),
                ('natural-csv','guest-natural-counter-hid.csv'),
                ('natural-json','guest-natural-counter-hid-evidence.json')):
                self.assertIn('--'+flag+'-'+kind+' paired/'+mode+'/'+filename,
                              fragment)
            self.assertIn('--'+flag+'-report paired/'+mode+
                          '/guest-audio-stress-evidence.json',fragment)
            self.assertIn('--'+flag+'-binding paired/'+mode+
                          '/guest-audio-mode-binding.json',fragment)
            self.assertIn('--'+flag+'-nro paired/build-'+mode+
                          '/cadillacs-dinosaurs-switch.nro',fragment)
        self.assertIn('paired-visible-arena-zr-pcm-attestation.json',workflow)


if __name__=='__main__':
    unittest.main()
