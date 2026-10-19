"""Controlled C adapter tests for six noncommercial audout ACK schedules.

A mock's release credits are artificial input, not measured NeXium timing.
"""
from contextlib import redirect_stdout
from io import StringIO
import copy
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import nexium_audio_release_corpus as corpus
from test_dino_switch_audout_mock import Diagnostics, ROOT

SOURCES=(
    'source/dino_switch_sound.c',
    'source/dino_audio_queue.c',
    'source/dino_sfx.c',
    'source/dino_pcm_witness.c',
    'tests/mocks/mock_audout.c',
)


class ReleaseCorpusContractTests(unittest.TestCase):
    def test_exact_six_credit_scenarios_and_window_positions(self):
        c=corpus.make_corpus()
        self.assertTrue(corpus.verify_corpus(c))
        self.assertEqual([v['name'] for v in c['scenarios']],list(corpus.NAMES))
        self.assertEqual(sum(c['frame_sizes']),900)
        self.assertEqual(len(c['frame_sizes']),360)
        for entry in c['scenarios']:
            self.assertEqual(len(entry['credits']),900)
            self.assertTrue(all(n in (0,1,2) for n in entry['credits']))
        result=corpus.oracle(c)
        self.assertEqual(len(result['scenarios']),6)
        self.assertTrue(all(len(v['per_150tick_counters'])==6
                            for v in result['scenarios']))

    def test_extreme_stalled_and_each_tick_ack_counts(self):
        obs=corpus.oracle(corpus.make_corpus())['scenarios']
        none,steady=obs[:2]
        self.assertEqual(
            (none['baseline']['submitted'],none['baseline']['skipped']),
            (0,900))
        self.assertEqual(
            (steady['baseline']['submitted'],steady['baseline']['skipped']),
            (900,0))
        self.assertEqual(none['extra_poll_released_pages'],0)
        self.assertEqual(steady['extra_poll_calls'],540)

    def test_forged_schedule_or_recomputed_hash_rejected(self):
        c=corpus.make_corpus()
        c['scenarios'][3]['credits'][51]=2
        with self.assertRaisesRegex(ValueError,'noncanonical'):
            corpus.verify_corpus(c)
        import hashlib
        c['corpus_sha256']=hashlib.sha256(corpus.stable_bytes(
            {k:v for k,v in c.items() if k!='corpus_sha256'})).hexdigest()
        with self.assertRaises(ValueError):
            corpus.verify_corpus(c)

    def test_forged_result_and_unsafe_claim_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p=root/'corpus.json'
            r=root/'result.json'
            c=corpus.make_corpus()
            expected=corpus.oracle(c)
            p.write_text(json.dumps(c),encoding='ascii')
            for field,value in (
                ('causal_audio_improvement_verified',True),
                ('physical_switch_audio_verified',True),
                ('frame_pacing_identical_on_host',1),
            ):
                with self.subTest(field=field):
                    copy_=copy.deepcopy(expected)
                    copy_[field]=value
                    r.write_text(json.dumps(copy_),encoding='ascii')
                    with self.assertRaisesRegex(ValueError,'native C ledgers'):
                        corpus.attest(p,r)
            copy_=copy.deepcopy(expected)
            copy_['scenarios'][4]['per_150tick_counters'][2][
                'extra-poll']['skipped']+=1
            r.write_text(json.dumps(copy_),encoding='ascii')
            with self.assertRaises(ValueError):
                corpus.attest(p,r)

    def test_duplicate_symlink_and_missing_report_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p=root/'corpus.json'
            r=root/'result.json'
            p.write_text(json.dumps(corpus.make_corpus()),encoding='ascii')
            r.write_text(json.dumps(corpus.oracle(corpus.make_corpus())),
                         encoding='ascii')
            raw=r.read_text(encoding='ascii')
            r.write_text('{'+'"status":"FORGED",'+raw[1:],encoding='ascii')
            with self.assertRaisesRegex(ValueError,'duplicate'):
                corpus.attest(p,r)
            r.unlink()
            r.symlink_to(p)
            with self.assertRaisesRegex(ValueError,'symlinked'):
                corpus.attest(p,r)
            r.unlink()
            with self.assertRaises(ValueError):
                corpus.attest(p,r)

    def test_cli_exclusive_creation_and_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p=root/'corpus.json'
            r=root/'result.json'
            att=root/'attestation.json'
            with redirect_stdout(StringIO()):
                self.assertEqual(corpus.main(['--out',str(p)]),0)
            r.write_text(json.dumps(corpus.oracle(corpus.make_corpus())),
                         encoding='ascii')
            with redirect_stdout(StringIO()):
                self.assertEqual(corpus.main([
                    '--corpus',str(p),'--result',str(r),
                    '--out',str(att)]),0)
            self.assertEqual(json.loads(att.read_text())['status'],
                             'SIX_NATIVE_C_RELEASE_SCENARIOS_MATCH_ORACLE')
            saved=att.read_bytes()
            with redirect_stdout(StringIO()):
                self.assertEqual(corpus.main([
                    '--corpus',str(p),'--result',str(r),
                    '--out',str(att)]),1)
            self.assertEqual(att.read_bytes(),saved)


@unittest.skipUnless(shutil.which('gcc'),'host gcc required for actual C adapters')
class NativeAudoutReleaseCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dino-release-corpus-')
        cls.libs=[]
        for mode in ('baseline','extra-poll'):
            path=Path(cls.tmp.name)/(mode+'.so')
            defines=['-DDINO_EMULATOR_SELFTEST']
            if mode=='extra-poll':
                defines.append('-DDINO_AUDIO_EXPERIMENT_MID_BATCH_POLL')
            cmd=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                 '-fPIC','-shared','-Itests/mocks','-Isource',
                 *defines,*SOURCES,'-o',str(path)]
            process=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            if process.returncode:
                raise AssertionError('actual C adapter compile failed: '+
                                     process.stderr)
            lib=ctypes.CDLL(str(path))
            lib.dino_switch_sound_open.restype=ctypes.c_bool
            lib.dino_switch_sound_step.argtypes=[ctypes.c_uint32]
            lib.dino_switch_sound_diagnostics.argtypes=[
                ctypes.POINTER(Diagnostics)]
            lib.dino_switch_sound_pcm_witness.restype=ctypes.c_uint64
            lib.dino_switch_sound_guest_mid_batch_calls.restype=ctypes.c_uint32
            lib.dino_switch_sound_guest_mid_batch_releases.restype=ctypes.c_uint32
            lib.mock_audout_grant_releases.argtypes=[ctypes.c_uint32]
            lib.mock_audout_pending.restype=ctypes.c_uint32
            lib.mock_audout_integrity_errors.restype=ctypes.c_uint32
            if mode=='extra-poll':
                lib.dino_switch_sound_guest_mid_batch_poll.restype=None
            cls.libs.append(lib)

    @classmethod
    def tearDownClass(cls):
        for lib in cls.libs:
            lib.dino_switch_sound_close()
        cls.tmp.cleanup()

    @staticmethod
    def diagnostic(lib):
        data=Diagnostics()
        lib.dino_switch_sound_diagnostics(ctypes.byref(data))
        return data

    def test_six_actual_C_adapters_under_exactly_same_release_credits(self):
        c=corpus.make_corpus()
        corpus.verify_corpus(c)
        override=os.environ.get('DINO_CONTROLLED_AUDOUT_CORPUS_PLAN')
        if override:
            read,_=corpus.read_json(override)
            self.assertTrue(corpus.exact(read,c))
        baseline,extra=self.libs
        observed=[]
        for scenario in c['scenarios']:
            before=[]
            for lib in (baseline,extra):
                lib.dino_switch_sound_close()
                lib.mock_audout_reset()
                self.assertTrue(lib.dino_switch_sound_open())
                for _ in range(2):
                    lib.dino_switch_sound_step(0)
                initial=self.diagnostic(lib)
                self.assertEqual(initial.pending,2)
                self.assertEqual(initial.submitted,2)
                before.append(initial.simulated_ticks)
            tick=0
            prev=[self.diagnostic(x) for x in (baseline,extra)]
            prev_poll=0
            windows=[]
            for frame_size in c['frame_sizes']:
                for position in range(frame_size):
                    credit=scenario['credits'][tick]
                    for lib in (baseline,extra):
                        lib.mock_audout_grant_releases(credit)
                    if position>0:
                        extra.dino_switch_sound_guest_mid_batch_poll()
                    event=1<<((tick*7)%10)
                    for lib in (baseline,extra):
                        lib.dino_switch_sound_step(event)
                    a=self.diagnostic(baseline)
                    b=self.diagnostic(extra)
                    self.assertEqual(a.simulated_ticks-before[0],tick+1)
                    self.assertEqual(b.simulated_ticks-before[1],tick+1)
                    for key in ('pending','submitted','released','skipped',
                                'active','queue_valid','audio_errors'):
                        self.assertEqual(getattr(a,key),getattr(b,key),
                                         f"{scenario['name']} {key} tick {tick}")
                    self.assertEqual(baseline.dino_switch_sound_pcm_witness(),
                                     extra.dino_switch_sound_pcm_witness())
                    self.assertEqual(baseline.mock_audout_pending(),a.pending)
                    self.assertEqual(extra.mock_audout_pending(),b.pending)
                    self.assertEqual(baseline.mock_audout_integrity_errors(),0)
                    self.assertEqual(extra.mock_audout_integrity_errors(),0)
                    tick+=1
                    if tick%150==0:
                        states=(a,b)
                        row={'tick_start':tick-150,'tick_end':tick}
                        for name,now,old in zip(('baseline','extra-poll'),
                                                 states,prev):
                            row[name]={
                                key:getattr(now,key)-getattr(old,key)
                                for key in ('submitted','released','skipped')
                            }
                            self.assertEqual(
                                row[name]['submitted']+row[name]['skipped'],150)
                        poll=extra.dino_switch_sound_guest_mid_batch_releases()
                        row['extra_poll_released_pages']=poll-prev_poll
                        windows.append(row)
                        prev=list(states)
                        prev_poll=poll
            self.assertEqual(tick,900)
            self.assertEqual(len(windows),6)
            self.assertEqual(extra.dino_switch_sound_guest_mid_batch_calls(),540)
            self.assertEqual(baseline.dino_switch_sound_guest_mid_batch_calls(),0)
            left,right=(self.diagnostic(x) for x in (baseline,extra))
            observed.append({
                'name':scenario['name'],
                'baseline':{
                    'submitted':left.submitted-2,
                    'released':left.released,
                    'skipped':left.skipped,
                    'pending_end':left.pending,
                },
                'extra-poll':{
                    'submitted':right.submitted-2,
                    'released':right.released,
                    'skipped':right.skipped,
                    'pending_end':right.pending,
                },
                'extra_poll_calls':extra.dino_switch_sound_guest_mid_batch_calls(),
                'extra_poll_released_pages':
                    extra.dino_switch_sound_guest_mid_batch_releases(),
                'per_150tick_counters':windows,
            })
        measured={
            'schema':corpus.RESULT_SCHEMA,
            'status':'MATCHED_SYNTHETIC_C_RELEASE_CORPUS_ONLY',
            'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
            'corpus_sha256':c['corpus_sha256'],
            'scenarios':observed,
            'frame_pacing_identical_on_host':True,
            'external_release_credits_identical_on_host':True,
            'real_ne_xium_guest_timing_verified':False,
            'physical_switch_audio_verified':False,
            'causal_audio_improvement_verified':False,
        }
        self.assertTrue(corpus.exact(measured,corpus.oracle(c)))
        destination=os.environ.get('DINO_CONTROLLED_AUDOUT_CORPUS_RESULT')
        if destination:
            with Path(destination).open('x',encoding='ascii') as f:
                f.write(json.dumps(measured,sort_keys=True)+'\n')


if __name__=='__main__':
    unittest.main()
