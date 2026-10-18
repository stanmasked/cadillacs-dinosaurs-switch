"""Synthetic ROM-free negatives for two separate audio evidence domains."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from tools import nexium_audio_control_plan as plan
from tools import nexium_audio_release_corpus as corpus
from tools import verify_nexium_audio_controlled_oracle as oracle
from tools import verify_nexium_audio_mode_binding as binding
from tools import verify_nexium_audio_paired_artifacts as paired
from tools import verify_nexium_audio_provenance_manifest as seal
from test_nexium_audio_mid_batch_ab import complete
from test_nexium_audio_paired_artifacts import synthetic_nro


class TwoDomainProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='dino-two-domain-')
        base=Path(self.tmp.name)
        self.f={key:base/(key+'.json') for key in seal.FILES}
        for key in ('baseline-nro','experimental-nro'):
            self.f[key]=base/(key+'.nro')
        self.put('host-plan',plan.make_plan())
        self.put('host-result',oracle.oracle(plan.make_plan()))
        self.put('host-oracle',oracle.verify(self.f['host-plan'],
                                              self.f['host-result']))
        self.put('corpus-plan',corpus.make_corpus())
        self.put('corpus-result',corpus.oracle(corpus.make_corpus()))
        self.put('corpus-attestation',
                 corpus.attest(self.f['corpus-plan'],self.f['corpus-result']))
        for mode,name,variation in ((False,'baseline',0),
                                    (True,'experimental',1)):
            self.f[name+'-nro'].write_bytes(synthetic_nro(name))
            self.put(name+'-report',complete(mode,variation))
            self.put(name+'-binding',binding.attest(
                'extra-poll' if mode else 'baseline',
                self.f[name+'-report'],self.f[name+'-nro']))
        self.put('guest-comparison',paired.compare(
            self.f['baseline-report'],self.f['baseline-binding'],
            self.f['experimental-report'],self.f['experimental-binding'],
            self.f['baseline-nro'],self.f['experimental-nro']))

    def tearDown(self):
        self.tmp.cleanup()

    def put(self,key,value):
        self.f[key].write_text(json.dumps(value,sort_keys=True)+'\n',
                               encoding='ascii')

    def audit(self):
        return seal.verify(self.f)

    def test_all_thirteen_files_verified_and_domains_not_interchanged(self):
        result=self.audit()
        self.assertEqual(result['status'],
                         'HOST_AND_GUEST_EVIDENCE_INDEPENDENTLY_BOUND')
        self.assertEqual(len(result['host_native_c_domain']['file_sha256']),6)
        self.assertEqual(len(result['real_nexium_guest_domain']['file_sha256']),7)
        self.assertEqual(
            result['host_native_c_domain']['synthetic_ticks_per_mode'],900)
        self.assertFalse(result[
            'synthetic_host_and_real_guest_evidence_interchangeable'])
        self.assertFalse(result['physical_switch_audio_verified'])
        self.assertFalse(result['causal_audio_improvement_verified'])

    def test_host_result_mutation_rejected_even_with_old_valid_attestation(self):
        fake=copy.deepcopy(json.loads(self.f['host-result'].read_text()))
        fake['baseline_skipped']+=1
        self.put('host-result',fake)
        with self.assertRaises(ValueError):
            self.audit()

    def test_corpus_fake_independent_claim_refused(self):
        fake=json.loads(self.f['corpus-attestation'].read_text())
        fake['independent_emulator_guest_runs_verified']=True
        self.put('corpus-attestation',fake)
        with self.assertRaisesRegex(ValueError,'attestation mismatch'):
            self.audit()

    def test_swapped_guest_binary_detected_by_full_nro_binding(self):
        self.f['experimental-nro'].write_bytes(
            self.f['baseline-nro'].read_bytes())
        with self.assertRaises(ValueError):
            self.audit()

    def test_replaced_guest_comparison_rejected(self):
        comparison=json.loads(self.f['guest-comparison'].read_text())
        comparison['descriptive_comparison']['extra_minus_baseline_skips']+=1
        self.put('guest-comparison',comparison)
        with self.assertRaisesRegex(ValueError,'comparison mismatch'):
            self.audit()

    def test_duplicate_keys_symlink_and_missing_file_fail_closed(self):
        raw=self.f['guest-comparison'].read_text()
        self.f['guest-comparison'].write_text(
            '{"status":"FORGED",'+raw[1:])
        with self.assertRaisesRegex(ValueError,'duplicate'):
            self.audit()
        self.put('guest-comparison',paired.compare(
            self.f['baseline-report'],self.f['baseline-binding'],
            self.f['experimental-report'],self.f['experimental-binding'],
            self.f['baseline-nro'],self.f['experimental-nro']))
        other=Path(self.tmp.name)/'other.json'
        other.write_bytes(self.f['corpus-result'].read_bytes())
        self.f['corpus-result'].unlink()
        self.f['corpus-result'].symlink_to(other)
        with self.assertRaisesRegex(ValueError,'symlinked'):
            self.audit()

    def test_float_or_boolean_causality_forgery_fail_closed(self):
        guest=json.loads(self.f['guest-comparison'].read_text())
        guest['host_conditions_matched_verified']=0
        self.put('guest-comparison',guest)
        with self.assertRaises(ValueError):
            self.audit()

    def test_missing_one_of_thirteen_sources_fails_closed(self):
        removed=self.f.pop('corpus-plan')
        with self.assertRaisesRegex(ValueError,'incomplete'):
            self.audit()
        self.f['corpus-plan']=removed

    def test_cli_can_create_exclusive_manifest(self):
        output=Path(self.tmp.name)/'manifest.json'
        args=[]
        for key in seal.FILES:
            args.extend(('--'+key,str(self.f[key])))
        from contextlib import redirect_stdout
        from io import StringIO
        with redirect_stdout(StringIO()):
            self.assertEqual(seal.main(args+['--out',str(output)]),0)
        self.assertEqual(json.loads(output.read_text()),self.audit())
        original=output.read_bytes()
        with redirect_stdout(StringIO()):
            self.assertEqual(seal.main(args+['--out',str(output)]),1)
        self.assertEqual(output.read_bytes(),original)


if __name__=='__main__':
    unittest.main()
