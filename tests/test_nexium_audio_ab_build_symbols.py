"""ROM-free negative tests for the independently checked A/B ELF."""
import unittest
from tools import verify_nexium_audio_ab_build_symbols as check

CORE=sorted(check.CORE)
GOOD='\n'.join(
    f'{i+0x110000:016x} T {name}' for i,name in enumerate(CORE))
EXTRA=GOOD+'\n001100ff T '+check.EXPERIMENT+'\n'


class ABELFLinkageTests(unittest.TestCase):
    def test_baseline_function_absent_and_diagnostic_symbols_present(self):
        result=check.verify(GOOD,'baseline')
        self.assertFalse(result['experiment_poll_symbol_linked'])
        self.assertFalse(result['guest_poll_actually_executed'])
        self.assertFalse(result['causal_audio_improvement_verified'])

    def test_experiment_requires_linked_extra_poll_function(self):
        result=check.verify(EXTRA,'extra')
        self.assertTrue(result['experiment_poll_symbol_linked'])
        self.assertEqual(result['guest_probe_symbols_linked'],3)
        self.assertFalse(result['physical_switch_audio_verified'])

    def test_swapped_build_labels_rejected(self):
        for data,variant in ((GOOD,'extra'),(EXTRA,'baseline')):
            with self.subTest(variant=variant):
                with self.assertRaises(ValueError):
                    check.verify(data,variant)

    def test_missing_unexpected_and_duplicate_probes_are_rejected(self):
        for data in (
                '',
                '00000001 T dino_switch_sound_guest_mid_batch_enabled',
                GOOD+'\n00000022 T '+CORE[0],
                EXTRA+'000000ff T '+check.EXPERIMENT,
                GOOD.replace(' T ',' U ',1),
                GOOD+'\nnot a real symbol '+check.EXPERIMENT,
        ):
            with self.subTest(data=data[-55:]):
                with self.assertRaises(ValueError):
                    check.verify(data,'baseline')

    def test_unknown_variants_rejected(self):
        for name in ('release','default','experimental',None,True):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    check.verify(GOOD,name)

    def test_symbol_type_must_be_executable_and_not_a_data_reference(self):
        for letter in ('B','D','U','A'):
            bad=EXTRA.replace(' T '+check.EXPERIMENT,
                              ' '+letter+' '+check.EXPERIMENT)
            with self.subTest(letter=letter):
                with self.assertRaises(ValueError):
                    check.verify(bad,'extra')

    def test_duplicate_guest_experiment_symbol_rejected(self):
        with self.assertRaises(ValueError):
            check.verify(EXTRA+'00110100 T '+check.EXPERIMENT+'\n','extra')


if __name__=='__main__':
    unittest.main()
