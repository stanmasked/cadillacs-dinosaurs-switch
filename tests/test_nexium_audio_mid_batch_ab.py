"""Synthetic Stage 157 A/B negatives; not actual NeXium execution."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools import verify_nexium_audio_mid_batch_ab as ab
from test_compare_nexium_audio_stress_runs import (
    fixture,with_release_probe,with_batch_position,
    with_batch_position_poll,with_released_page_positions,
    with_fixed_ack_headroom,
)


def complete(enabled,variation=0):
    r=with_fixed_ack_headroom(with_released_page_positions(
        with_batch_position_poll(with_batch_position(
            with_release_probe(fixture(variation),25)))))
    w=[]
    for i in range(6):
        w.append({
            'tick_start':i*150,'tick_end':(i+1)*150,
            'poll_calls':25 if enabled else 0,
            'poll_released_pages':1 if enabled else 0,
        })
    r.update({
        'guest_mid_batch_extra_poll_probe_present':True,
        'guest_mid_batch_extra_poll_enabled':enabled,
        'guest_mid_batch_extra_poll_calls':150 if enabled else 0,
        'guest_mid_batch_extra_poll_released_pages':6 if enabled else 0,
        'checkpoint_guest_mid_batch_extra_poll_intervals':w,
    })
    return r


class ExperimentalABTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='dino-mid-ab-test-')
        root=Path(self.temp.name)
        self.a=root/'baseline.json'
        self.b=root/'experimental.json'
        self.write(self.a,complete(False,0))
        self.write(self.b,complete(True,1))

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write(path,data):
        path.write_text(json.dumps(data,sort_keys=True)+'\n',
                        encoding='ascii')

    def test_verified_guest_mode_and_exact_extra_poll_invocations(self):
        result=ab.compare(self.a,self.b)
        self.assertEqual(result['status'],
                         'UNCONTROLLED_GUEST_RUN_DESCRIPTIVE_ONLY')
        self.assertEqual(result['baseline']
                         ['additional_nonblocking_poll_calls'],0)
        self.assertEqual(result['experimental']
                         ['additional_nonblocking_poll_calls'],150)
        self.assertEqual(result['experimental']
                         ['pages_released_by_additional_polls'],6)
        self.assertFalse(result['causal_audio_improvement_verified'])
        self.assertFalse(result['audio_latency_verified'])

    def test_swapped_variants_are_rejected(self):
        with self.assertRaises(ValueError):
            ab.compare(self.b,self.a)

    def test_legacy_reports_lack_guest_mode_witness(self):
        self.write(self.a,fixture())
        with self.assertRaises(ValueError):
            ab.compare(self.a,self.b)

    def test_forged_experimental_mode_and_counters_are_rejected(self):
        valid=complete(True,1)
        for name,bad in (
                ('guest_mid_batch_extra_poll_enabled',False),
                ('guest_mid_batch_extra_poll_enabled',1),
                ('guest_mid_batch_extra_poll_probe_present',False),
                ('guest_mid_batch_extra_poll_calls',149),
                ('guest_mid_batch_extra_poll_calls',True),
                ('guest_mid_batch_extra_poll_released_pages',31),
                ('guest_mid_batch_extra_poll_released_pages',7)):
            with self.subTest(name=name,bad=bad):
                forged=copy.deepcopy(valid)
                forged[name]=bad
                self.write(self.b,forged)
                with self.assertRaises(ValueError):
                    ab.compare(self.a,self.b)

    def test_forged_experimental_windows_fail_even_if_totals_match(self):
        valid=complete(True,1)
        for change in ('calls','releases','fields','start','move'):
            with self.subTest(change=change):
                broken=copy.deepcopy(valid)
                windows=broken['checkpoint_guest_mid_batch_extra_poll_intervals']
                if change=='calls':
                    windows[0]['poll_calls']=24
                elif change=='releases':
                    windows[0]['poll_released_pages']=6
                elif change=='fields':
                    windows[0]['fake_audio_fix']=True
                elif change=='start':
                    windows[0]['tick_start']=1
                else:
                    windows[0]['poll_released_pages']=0
                    windows[1]['poll_released_pages']=2
                self.write(self.b,broken)
                with self.assertRaises(ValueError):
                    ab.compare(self.a,self.b)

    def test_baseline_cannot_claim_unexplained_poll(self):
        s=complete(False,0)
        for field in ('guest_mid_batch_extra_poll_calls',
                      'guest_mid_batch_extra_poll_released_pages'):
            bad=copy.deepcopy(s)
            bad[field]=1
            self.write(self.a,bad)
            with self.assertRaises(ValueError):
                ab.compare(self.a,self.b)

    def test_cli_fail_closed_with_status_and_nonzero_exit(self):
        self.write(self.b,complete(False,1))
        rc=ab.main(['--baseline',str(self.a),
                    '--experimental',str(self.b)])
        self.assertEqual(rc,1)


if __name__=='__main__':
    unittest.main()
