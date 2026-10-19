"""Synthetic fail-closed tests for independent native C audout accounting."""
from contextlib import redirect_stdout
from io import StringIO
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools import nexium_audio_control_plan as plan
from tools import verify_nexium_audio_controlled_oracle as check


class IndependentAudoutOracleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='dino-audout-oracle-')
        self.root=Path(self.tmp.name)
        self.p=self.root/'plan.json'
        self.r=self.root/'native-result.json'
        self.plan=plan.make_plan()
        self.expected=check.oracle(self.plan)
        self.write()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self):
        self.p.write_text(json.dumps(self.plan,sort_keys=True)+'\n',encoding='ascii')
        self.r.write_text(json.dumps(self.expected,sort_keys=True)+'\n',encoding='ascii')

    def test_native_900_tick_six_window_ledger_matches_independent_oracle(self):
        witness=check.verify(self.p,self.r)
        self.assertEqual(witness['status'],
                         'CONTROLLED_NATIVE_C_LEDGER_MATCHES_INDEPENDENT_ORACLE')
        self.assertEqual(self.expected['baseline_skipped'],484)
        self.assertEqual(self.expected['experimental_skipped'],484)
        self.assertEqual(self.expected['extra_poll_page_releases'],249)
        self.assertEqual(self.expected['later_batch_experimental_poll_calls'],540)
        self.assertEqual(self.expected['baseline_submitted_during_stress'],416)
        self.assertEqual([r['baseline']['skipped'] for r in
                          self.expected['per_150tick_counters']],
                         [80,81,81,80,82,80])
        self.assertFalse(witness['emulator_frame_pacing_matched_verified'])

    def test_mutated_window_and_global_values_refused(self):
        for field in ('submitted','released','skipped'):
            with self.subTest(field=field):
                changed=copy.deepcopy(self.expected)
                changed['per_150tick_counters'][3]['extra-poll'][field]+=1
                self.r.write_text(json.dumps(changed),encoding='ascii')
                with self.assertRaisesRegex(ValueError,'do not match'):
                    check.verify(self.p,self.r)
        self.write()
        changed=copy.deepcopy(self.expected)
        changed['baseline_skipped']+=1
        self.r.write_text(json.dumps(changed),encoding='ascii')
        with self.assertRaises(ValueError):
            check.verify(self.p,self.r)

    def test_recomputed_plan_hash_cannot_change_fixed_stimulus(self):
        changed=copy.deepcopy(self.plan)
        changed['pre_tick_external_release_credits'][20]=2
        changed['stimulus_sha256']=hashlib.sha256(
            plan.canonical_bytes({k:v for k,v in changed.items()
                                  if k!='stimulus_sha256'})).hexdigest()
        self.p.write_text(json.dumps(changed),encoding='ascii')
        with self.assertRaises(ValueError):
            check.verify(self.p,self.r)

    def test_duplicate_result_keys_rejected(self):
        raw=self.r.read_text(encoding='ascii')
        self.r.write_text('{'+'"baseline_skipped":999,'+raw[1:],encoding='ascii')
        with self.assertRaisesRegex(ValueError,'duplicate JSON'):
            check.verify(self.p,self.r)

    def test_symlink_and_truncated_inputs_refused(self):
        dest=self.root/'result-copy.json'
        dest.write_bytes(self.r.read_bytes())
        self.r.unlink()
        self.r.symlink_to(dest)
        with self.assertRaisesRegex(ValueError,'symlinked'):
            check.verify(self.p,self.r)
        self.r.unlink()
        self.r.write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'size'):
            check.verify(self.p,self.r)

    def test_unsafe_type_and_false_emulator_claim_rejected(self):
        for key,value in (('host_input_schedule_matched',1),
                          ('guest_frame_pacing_matched_verified',True),
                          ('emulator_audio_improvement_verified',True),
                          ('extra_poll_page_releases',False)):
            with self.subTest(key=key):
                changed=copy.deepcopy(self.expected)
                changed[key]=value
                self.r.write_text(json.dumps(changed),encoding='ascii')
                with self.assertRaises(ValueError):
                    check.verify(self.p,self.r)
        self.write()
        changed=copy.deepcopy(self.plan)
        changed['causal_emulator_audio_improvement_verified']=0
        self.p.write_text(json.dumps(changed),encoding='ascii')
        with self.assertRaisesRegex(ValueError,'noncanonical'):
            check.verify(self.p,self.r)

    def test_cli_exclusive_success_then_rejects_overwrite(self):
        output=self.root/'oracle-result.json'
        with redirect_stdout(StringIO()):
            self.assertEqual(check.main(['--plan',str(self.p),
                                         '--result',str(self.r),
                                         '--out',str(output)]),0)
        recorded=json.loads(output.read_text(encoding='ascii'))
        self.assertEqual(recorded,check.verify(self.p,self.r))
        original=output.read_bytes()
        with redirect_stdout(StringIO()):
            self.assertEqual(check.main(['--plan',str(self.p),
                                         '--result',str(self.r),
                                         '--out',str(output)]),1)
        self.assertEqual(output.read_bytes(),original)

    def test_inconclusive_never_creates_passing_report(self):
        self.r.unlink()
        output=self.root/'missing-report.json'
        display=StringIO()
        with redirect_stdout(display):
            self.assertEqual(check.main(['--plan',str(self.p),
                                         '--result',str(self.r),
                                         '--out',str(output)]),1)
        self.assertFalse(output.exists())
        line=json.loads(display.getvalue())
        self.assertEqual(line['status'],'INCONCLUSIVE_CONTROLLED_C_ORACLE_MISMATCH')
        self.assertFalse(line['causal_audio_improvement_verified'])


if __name__=='__main__':
    unittest.main()
