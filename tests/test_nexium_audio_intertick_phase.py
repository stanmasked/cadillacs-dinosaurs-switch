"""Test exact intertick ACK-arrival timing in production C audio adapters.

The two C binaries receive the same externally granted release time. Only
extra-poll variant can observe the release *before* next ordinary game tick.
No real NeXium timing, hardware output, or audible parity is inferred.
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

from tools import nexium_audio_intertick_phase as phase
from test_dino_switch_audout_mock import Diagnostics, ROOT

SOURCES=(
    'source/dino_switch_sound.c',
    'source/dino_audio_queue.c',
    'source/dino_sfx.c',
    'source/dino_pcm_witness.c',
    'tests/mocks/mock_audout.c',
)


class HostPhasePlanTests(unittest.TestCase):
    def test_three_pre_registered_cases_share_one_frame_schedule(self):
        p=phase.make_plan()
        self.assertIs(phase.check_plan(p),p)
        self.assertEqual(sum(p['frames']),900)
        self.assertEqual(len(p['frames']),360)
        self.assertEqual(len(p['external_credits']),900)
        self.assertEqual(p['intertick_poll_positions'],540)
        result=phase.oracle(p)
        self.assertEqual([v['phase'] for v in result['cases']],
                         list(phase.PHASES))
        for case in result['cases']:
            self.assertEqual(len(case['per_150tick_counters']),6)
            self.assertEqual(case['extra_poll_calls'],540)
            self.assertEqual(case['baseline'],case['extra-poll'])

    def test_early_arrival_detected_earlier_but_not_admitted_more(self):
        before,after,alternating=phase.oracle(phase.make_plan())['cases']
        self.assertGreater(before['extra_poll_page_releases'],0)
        self.assertEqual(after['extra_poll_page_releases'],0)
        self.assertEqual(after['early_detection_events'],0)
        self.assertGreater(alternating['extra_poll_page_releases'],0)
        self.assertLess(alternating['extra_poll_page_releases'],
                        before['extra_poll_page_releases'])
        for entry in (before,after,alternating):
            self.assertEqual(entry['baseline']['submitted'],416)
            self.assertEqual(entry['baseline']['skipped'],484)
            self.assertEqual(entry['baseline']['released'],416)

    def test_changed_credit_or_phase_rejected_even_with_rehashed_plan(self):
        p=phase.make_plan()
        p['external_credits'][12]=0
        import hashlib
        p['plan_sha256']=hashlib.sha256(phase.canonical(
            {k:v for k,v in p.items() if k!='plan_sha256'})).hexdigest()
        with self.assertRaisesRegex(ValueError,'altered'):
            phase.check_plan(p)
        p=phase.make_plan()
        p['phase_cases'][0]='after-extra'
        with self.assertRaises(ValueError):
            phase.check_plan(p)

    def test_fake_intertick_late_poll_release_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'plan.json'
            r=Path(d)/'report.json'
            p.write_text(json.dumps(phase.make_plan()),encoding='ascii')
            observed=phase.oracle(phase.make_plan())
            observed['cases'][1]['extra_poll_page_releases']=1
            r.write_text(json.dumps(observed),encoding='ascii')
            with self.assertRaisesRegex(ValueError,'differ'):
                phase.attest(p,r)

    def test_false_device_claim_and_counter_substitution_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'plan.json'
            r=Path(d)/'result.json'
            p.write_text(json.dumps(phase.make_plan()),encoding='ascii')
            actual=phase.oracle(phase.make_plan())
            for change in (
                ('hardware_audio_verified',True),
                ('causal_audio_improvement_verified',True),
                ('external_release_arrival_identical_for_modes',1),
            ):
                forged=copy.deepcopy(actual)
                forged[change[0]]=change[1]
                r.write_text(json.dumps(forged),encoding='ascii')
                with self.subTest(change=change),self.assertRaises(ValueError):
                    phase.attest(p,r)

    def test_duplicate_json_symlink_and_cli_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'plan.json'
            r=Path(d)/'result.json'
            a=Path(d)/'att.json'
            with redirect_stdout(StringIO()):
                self.assertEqual(phase.main(['--out',str(p)]),0)
            r.write_text(json.dumps(phase.oracle(phase.make_plan())),
                         encoding='ascii')
            with redirect_stdout(StringIO()):
                self.assertEqual(phase.main([
                    '--plan',str(p),'--result',str(r),'--out',str(a)]),0)
            self.assertEqual(json.loads(a.read_text())['status'],
                             'INTERTICK_PHASES_C_AND_ORACLE_MATCH')
            prior=a.read_bytes()
            with redirect_stdout(StringIO()):
                self.assertEqual(phase.main([
                    '--plan',str(p),'--result',str(r),'--out',str(a)]),1)
            self.assertEqual(a.read_bytes(),prior)
            r.write_text('{"status":"FORGED",'+r.read_text()[1:])
            with self.assertRaisesRegex(ValueError,'duplicate'):
                phase.attest(p,r)
            r.unlink()
            r.symlink_to(p)
            with self.assertRaisesRegex(ValueError,'symlinked'):
                phase.attest(p,r)


@unittest.skipUnless(shutil.which('gcc'), 'host GCC required for C audout')
class RealCIntertickPhaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dino-intertick-C-')
        cls.libs=[]
        for enabled in (False,True):
            libfile=Path(cls.tmp.name)/('experimental.so' if enabled
                                        else 'baseline.so')
            defines=['-DDINO_EMULATOR_SELFTEST']
            if enabled:
                defines.append('-DDINO_AUDIO_EXPERIMENT_MID_BATCH_POLL')
            cmd=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                 '-fPIC','-shared','-Itests/mocks','-Isource',
                 *defines,*SOURCES,'-o',str(libfile)]
            built=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            if built.returncode:
                raise AssertionError('Production C adapter compile failed: '+
                                     built.stderr)
            lib=ctypes.CDLL(str(libfile))
            lib.dino_switch_sound_open.restype=ctypes.c_bool
            lib.dino_switch_sound_step.argtypes=[ctypes.c_uint32]
            lib.dino_switch_sound_diagnostics.argtypes=[
                ctypes.POINTER(Diagnostics)]
            lib.dino_switch_sound_pcm_witness.restype=ctypes.c_uint64
            lib.dino_switch_sound_guest_mid_batch_calls.restype=ctypes.c_uint32
            lib.dino_switch_sound_guest_mid_batch_releases.restype=ctypes.c_uint32
            lib.mock_audout_grant_releases.argtypes=[ctypes.c_uint32]
            lib.mock_audout_integrity_errors.restype=ctypes.c_uint32
            lib.mock_audout_pending.restype=ctypes.c_uint32
            if enabled:
                lib.dino_switch_sound_guest_mid_batch_poll.restype=None
            cls.libs.append(lib)

    @classmethod
    def tearDownClass(cls):
        for lib in cls.libs:
            lib.dino_switch_sound_close()
        cls.tmp.cleanup()

    @staticmethod
    def state(lib):
        obj=Diagnostics()
        lib.dino_switch_sound_diagnostics(ctypes.byref(obj))
        return obj

    def test_identical_release_arrivals_both_modes_three_phases(self):
        base,extra=self.libs
        p=phase.make_plan()
        phase.check_plan(p)
        observed=[]
        for arrival in phase.PHASES:
            starts=[]
            for lib in (base,extra):
                lib.dino_switch_sound_close()
                lib.mock_audout_reset()
                self.assertTrue(lib.dino_switch_sound_open())
                for _ in range(2):
                    lib.dino_switch_sound_step(0)
                state=self.state(lib)
                self.assertEqual(state.pending,2)
                self.assertEqual(state.submitted,2)
                starts.append(state.simulated_ticks)
            before=[self.state(x) for x in (base,extra)]
            oldpoll=0
            older_events=0
            early_events=0
            tick=0
            rows=[]
            for frames in p['frames']:
                for position in range(frames):
                    count=p['external_credits'][tick]
                    earlier=phase.is_early(arrival,tick,position)
                    if position and not earlier:
                        # All old synthetic credits expire at the tick
                        # boundary; the new external ACK arrives only
                        # after the experimental poll in this phase.
                        for lib in (base,extra):
                            lib.mock_audout_grant_releases(0)
                        extra.dino_switch_sound_guest_mid_batch_poll()
                        for lib in (base,extra):
                            lib.mock_audout_grant_releases(count)
                    else:
                        # Same external release becomes available to both
                        # adapters BEFORE the experimental optional poll.
                        for lib in (base,extra):
                            lib.mock_audout_grant_releases(count)
                        if position:
                            a_before=self.state(base)
                            extra.dino_switch_sound_guest_mid_batch_poll()
                            a_after=self.state(extra)
                            observed_delta=a_before.pending-a_after.pending
                            self.assertGreaterEqual(observed_delta,0)
                            if observed_delta:
                                early_events+=1
                    event=1<<((tick*7)%10)
                    for lib in (base,extra):
                        lib.dino_switch_sound_step(event)
                    a,b=(self.state(x) for x in (base,extra))
                    for k in ('pending','submitted','released','skipped',
                              'queue_valid','active','audio_errors'):
                        self.assertEqual(getattr(a,k),getattr(b,k),
                                         f'{arrival}, {k}, tick {tick}')
                    self.assertEqual(a.simulated_ticks-starts[0],tick+1)
                    self.assertEqual(b.simulated_ticks-starts[1],tick+1)
                    self.assertEqual(base.dino_switch_sound_pcm_witness(),
                                     extra.dino_switch_sound_pcm_witness())
                    self.assertEqual(base.mock_audout_pending(),a.pending)
                    self.assertEqual(extra.mock_audout_pending(),b.pending)
                    self.assertEqual(base.mock_audout_integrity_errors(),0)
                    self.assertEqual(extra.mock_audout_integrity_errors(),0)
                    tick+=1
                    if tick%150==0:
                        row={'tick_start':tick-150,'tick_end':tick}
                        current=(a,b)
                        for name,current_state,older in zip(
                                ('baseline','extra-poll'),current,before):
                            row[name]={
                                key:getattr(current_state,key)-getattr(older,key)
                                for key in ('submitted','released','skipped')
                            }
                        polls=extra.dino_switch_sound_guest_mid_batch_releases()
                        row['extra_poll_page_releases']=polls-oldpoll
                        row['early_detection_events']=early_events-older_events
                        rows.append(row)
                        oldpoll=polls
                        older_events=early_events
                        before=[a,b]
            self.assertEqual(tick,900)
            self.assertEqual(len(rows),6)
            self.assertEqual(extra.dino_switch_sound_guest_mid_batch_calls(),540)
            self.assertEqual(base.dino_switch_sound_guest_mid_batch_calls(),0)
            a,b=(self.state(x) for x in (base,extra))
            observed.append({
                'phase':arrival,
                'baseline':{
                    'submitted':a.submitted-2,
                    'released':a.released,'skipped':a.skipped,
                    'pending_end':a.pending,
                },
                'extra-poll':{
                    'submitted':b.submitted-2,
                    'released':b.released,'skipped':b.skipped,
                    'pending_end':b.pending,
                },
                'extra_poll_calls':extra.dino_switch_sound_guest_mid_batch_calls(),
                'extra_poll_page_releases':
                    extra.dino_switch_sound_guest_mid_batch_releases(),
                'early_detection_events':early_events,
                'per_150tick_counters':rows,
            })
        recorded={
            'schema':phase.RESULT_SCHEMA,
            'status':'THREE_INTERTICK_PHASES_NATIVE_C_MATCHED_HOST_INPUTS',
            'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
            'plan_sha256':p['plan_sha256'],
            'cases':observed,
            'external_release_arrival_identical_for_modes':True,
            'hardware_audio_verified':False,
            'emulator_clock_matched_verified':False,
            'causal_audio_improvement_verified':False,
        }
        self.assertTrue(phase.corpus.exact(recorded,phase.oracle(p)))
        filename=os.environ.get('DINO_INTERTICK_RESULT')
        if filename:
            with Path(filename).open('x',encoding='ascii') as dest:
                dest.write(json.dumps(recorded,sort_keys=True)+'\n')


if __name__=='__main__':
    unittest.main()
