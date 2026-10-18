"""Two actual production C adapter binaries under ONE synthetic 900-tick plan.

This controlled host test is not an emulator run or physical Switch audio.
"""
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from tools import nexium_audio_control_plan as plan
from test_dino_switch_audout_mock import Diagnostics

ROOT=Path(__file__).resolve().parents[1]
SOURCES=[
    'source/dino_switch_sound.c',
    'source/dino_audio_queue.c',
    'source/dino_sfx.c',
    'source/dino_pcm_witness.c',
    'tests/mocks/mock_audout.c',
]


class SyntheticControlPlanTests(unittest.TestCase):
    def test_six_identical_window_frame_patterns_and_initial_queue(self):
        p=plan.make_plan()
        self.assertTrue(plan.verify_plan(p))
        self.assertEqual(p['total_simulation_ticks'],900)
        self.assertEqual(p['initial_pending_pages'],2)
        self.assertEqual(len(p['frame_sizes']),360)
        self.assertEqual(sum(p['frame_sizes']),900)
        self.assertEqual(len(p['pre_tick_external_release_credits']),900)
        for i in range(6):
            frames=p['frame_sizes'][i*60:(i+1)*60]
            self.assertEqual(sum(frames),150)
            self.assertEqual(frames,[1,2,3,4]*15)
        self.assertEqual(sum(n-1 for n in p['frame_sizes']),540)

    def test_plan_mutation_or_recalculated_forged_digest_fails_closed(self):
        original=plan.make_plan()
        altered={**original,'pre_tick_external_release_credits':
                 list(original['pre_tick_external_release_credits'])}
        altered['pre_tick_external_release_credits'][17]=2
        with self.assertRaises(ValueError):
            plan.verify_plan(altered)
        import hashlib
        altered['stimulus_sha256']=hashlib.sha256(
            plan.canonical_bytes({
                k:v for k,v in altered.items() if k!='stimulus_sha256'
            })).hexdigest()
        with self.assertRaises(ValueError):
            plan.verify_plan(altered)

    def test_exclusive_cli_plan_creation_never_overwrites(self):
        with tempfile.TemporaryDirectory() as t:
            output=Path(t)/'control.json'
            self.assertEqual(plan.main(['--out',str(output)]),0)
            expected=json.loads(output.read_text(encoding='ascii'))
            self.assertTrue(plan.verify_plan(expected))
            old=output.read_bytes()
            self.assertEqual(plan.main(['--out',str(output)]),1)
            self.assertEqual(output.read_bytes(),old)

    def test_invalid_release_tick_rejected(self):
        for tick in (-1,900,True,'0'):
            with self.subTest(tick=tick):
                with self.assertRaises(ValueError):
                    plan.release_credit(tick)


@unittest.skipUnless(shutil.which('gcc'), 'gcc required for real C audio mock')
class MatchedProductionAudoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='dino-control-900-')
        cls.libs=[]
        for mode in ('baseline','extra-poll'):
            library=Path(cls.tmp.name)/(mode+'.so')
            flags=['-DDINO_EMULATOR_SELFTEST']
            if mode=='extra-poll':
                flags.append('-DDINO_AUDIO_EXPERIMENT_MID_BATCH_POLL')
            cmd=['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',
                 '-fPIC','-shared','-Itests/mocks','-Isource',
                 *flags,*SOURCES,'-o',str(library)]
            compiled=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
            if compiled.returncode:
                raise AssertionError('Native production adapter failed: '+
                                     compiled.stderr)
            lib=ctypes.CDLL(str(library))
            lib.dino_switch_sound_open.restype=ctypes.c_bool
            lib.dino_switch_sound_step.argtypes=[ctypes.c_uint32]
            lib.dino_switch_sound_diagnostics.argtypes=[
                ctypes.POINTER(Diagnostics)]
            lib.dino_switch_sound_pcm_ticks.restype=ctypes.c_uint32
            lib.dino_switch_sound_pcm_witness.restype=ctypes.c_uint64
            lib.mock_audout_grant_releases.argtypes=[ctypes.c_uint32]
            lib.mock_audout_integrity_errors.restype=ctypes.c_uint32
            lib.mock_audout_pending.restype=ctypes.c_uint32
            lib.dino_switch_sound_guest_mid_batch_enabled.restype=ctypes.c_uint32
            lib.dino_switch_sound_guest_mid_batch_calls.restype=ctypes.c_uint32
            lib.dino_switch_sound_guest_mid_batch_releases.restype=ctypes.c_uint32
            if mode=='extra-poll':
                lib.dino_switch_sound_guest_mid_batch_poll.restype=None
            cls.libs.append(lib)

    @classmethod
    def tearDownClass(cls):
        for lib in cls.libs:
            lib.dino_switch_sound_close()
        cls.tmp.cleanup()

    @staticmethod
    def state(lib):
        out=Diagnostics()
        lib.dino_switch_sound_diagnostics(ctypes.byref(out))
        return out

    def test_separate_C_binaries_and_guest_only_poll_symbol(self):
        baseline,extra=self.libs
        self.assertEqual(baseline.dino_switch_sound_guest_mid_batch_enabled(),0)
        self.assertEqual(extra.dino_switch_sound_guest_mid_batch_enabled(),1)
        with self.assertRaises(AttributeError):
            baseline.dino_switch_sound_guest_mid_batch_poll

    def test_two_modes_same_prefill_frames_and_ack_credits_900_ticks(self):
        baseline,extra=self.libs
        scenario=plan.make_plan()
        self.assertTrue(plan.verify_plan(scenario))
        before=[]
        for lib in (baseline,extra):
            lib.dino_switch_sound_close()
            lib.mock_audout_reset()
            self.assertTrue(lib.dino_switch_sound_open())
            # Establish equal occupancy *before* the 900 measured ticks.
            for _ in range(scenario['prefill_no_release_ticks']):
                lib.dino_switch_sound_step(0)
            snapshot=self.state(lib)
            self.assertEqual(snapshot.pending,2)
            self.assertEqual(snapshot.submitted,2)
            before.append(snapshot.simulated_ticks)
        tick=0
        later=0
        previous=[self.state(lib) for lib in (baseline,extra)]
        windows=[]
        for frames in scenario['frame_sizes']:
            for inside in range(frames):
                credit=scenario['pre_tick_external_release_credits'][tick]
                for lib in (baseline,extra):
                    lib.mock_audout_grant_releases(credit)
                if inside>0:
                    extra.dino_switch_sound_guest_mid_batch_poll()
                    later+=1
                event=1<<((tick*7)%10)
                for lib in (baseline,extra):
                    lib.dino_switch_sound_step(event)
                a=self.state(baseline)
                b=self.state(extra)
                for field in ('pending','submitted','released','skipped',
                              'full_queue_skips','active','queue_valid'):
                    self.assertEqual(getattr(a,field),getattr(b,field),
                                     f'{field} at tick {tick}')
                self.assertEqual(a.simulated_ticks-before[0],tick+1)
                self.assertEqual(b.simulated_ticks-before[1],tick+1)
                self.assertEqual(baseline.dino_switch_sound_pcm_witness(),
                                 extra.dino_switch_sound_pcm_witness())
                self.assertEqual(baseline.mock_audout_integrity_errors(),0)
                self.assertEqual(extra.mock_audout_integrity_errors(),0)
                tick+=1
                if tick%150==0:
                    states=[a,b]
                    row={'tick_start':tick-150,'tick_end':tick}
                    for name,current,old in zip(
                            ('baseline','extra-poll'),states,previous):
                        row[name]={
                            key:getattr(current,key)-getattr(old,key)
                            for key in ('submitted','released','skipped')
                        }
                        self.assertEqual(
                            sum(row[name][k] for k in ('submitted','skipped')),
                            150)
                    windows.append(row)
                    previous=states
        self.assertEqual(tick,900)
        self.assertEqual(len(windows),6)
        self.assertEqual(later,540)
        self.assertEqual(extra.dino_switch_sound_guest_mid_batch_calls(),later)
        self.assertEqual(baseline.dino_switch_sound_guest_mid_batch_calls(),0)
        # Credits are injected before the same simulated tick in both
        # modes; extra polls only change *which poll* observes a real ACK.
        self.assertLessEqual(
            extra.dino_switch_sound_guest_mid_batch_releases(),
            self.state(extra).released)
        self.assertEqual(self.state(baseline).released,
                         self.state(extra).released)
        self.assertEqual(self.state(baseline).submitted+
                         self.state(baseline).skipped,902)
        self.assertEqual(self.state(extra).submitted+
                         self.state(extra).skipped,902)
        for name in ('baseline','extra-poll'):
            self.assertEqual(
                sum(row[name]['skipped'] for row in windows),
                self.state(baseline if name=='baseline' else extra).skipped)
        output=os.environ.get('DINO_CONTROLLED_AUDOUT_RESULT')
        if output:
            # Only after all 900 native ticks, ownership checks and
            # per-window conservation have passed. Never overwrite.
            result={
                'schema':'dino-controlled-native-audout-comparison-v1',
                'status':'DETERMINISTIC_TWO_C_ADAPTERS_MATCHED_HOST_INPUTS',
                'scope':'SYNTHETIC_HOST_C_ADAPTER_ONLY',
                'stimulus_sha256':scenario['stimulus_sha256'],
                'start_pending_pages':2,
                'total_measured_ticks':900,
                'later_batch_experimental_poll_calls':later,
                'extra_poll_page_releases':
                    extra.dino_switch_sound_guest_mid_batch_releases(),
                'per_150tick_counters':windows,
                'baseline_skipped':self.state(baseline).skipped,
                'experimental_skipped':self.state(extra).skipped,
                'baseline_submitted_during_stress':
                    self.state(baseline).submitted-2,
                'experimental_submitted_during_stress':
                    self.state(extra).submitted-2,
                'host_input_schedule_matched':True,
                'observed_queue_accounting_equal':True,
                'guest_frame_pacing_matched_verified':False,
                'emulator_audio_improvement_verified':False,
                'physical_switch_audio_verified':False,
                'original_arcade_audio_verified':False,
            }
            with Path(output).open('x',encoding='ascii') as dest:
                dest.write(json.dumps(result,sort_keys=True)+'\n')


if __name__=='__main__':
    unittest.main()
