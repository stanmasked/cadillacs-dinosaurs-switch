"""ROM-free negatives for exact guest audio ACK discovery tick trace.

The fixture is synthetic (one grant/admission each tick), not evidence of
actual libnx service behavior. The real CI path validates independently
verified ARM64 guest reports and mode-bound NROs.
"""
import copy
import csv
import json
from io import StringIO
from pathlib import Path
import tempfile
import unittest

from tools import verify_nexium_audio_ack_tick_trace as ack


def fixture():
    rows=[]
    for tick in range(1,901):
        rows.append(dict(zip(ack.COLUMNS,(
            tick,tick,1,0,1,0,0,1,0,0,0,1,0))))
    report={
        'simulation_ticks':900,
        'guest_mid_batch_extra_poll_enabled':False,
        'queue_pending_at_stress_start':1,
        'queue_pending_at_stress_end':1,
        'audio_errors_added':0,
        'audout_blocks_submitted':900,
        'audout_blocks_released':900,
        'audout_blocks_skipped':0,
        'guest_mid_batch_extra_poll_calls':0,
        'guest_mid_batch_extra_poll_released_pages':0,
        'full_before_release_poll_ticks':0,
        'full_recovered_before_admission_ticks':0,
        'checkpoint_skipped_deltas':[0]*6,
        'checkpoint_batch_position_intervals':[],
        'checkpoint_release_position_intervals':[],
        'checkpoint_batch_position_poll_intervals':[],
        'checkpoint_guest_mid_batch_extra_poll_intervals':[],
        'checkpoint_mode_intervals':[],
        'checkpoint_release_poll_intervals':[],
    }
    for i in range(6):
        start,end=i*150,(i+1)*150
        bounds={'tick_start':start,'tick_end':end}
        report['checkpoint_batch_position_intervals'].append({
            **bounds,'first_tick_steps':0,'later_tick_steps':0,
            'first_tick_skips':0,'later_tick_skips':0})
        report['checkpoint_release_position_intervals'].append({
            **bounds,'single_frame_released_pages':150,
            'batched_first_released_pages':0,
            'batched_later_released_pages':0})
        report['checkpoint_batch_position_poll_intervals'].append({
            **bounds,'first_full_before_poll':0,
            'first_recovered_after_poll':0,
            'later_full_before_poll':0,'later_recovered_after_poll':0,
            'single_full_before_poll':0,'single_recovered_after_poll':0})
        report['checkpoint_guest_mid_batch_extra_poll_intervals'].append({
            **bounds,'poll_calls':0,'poll_released_pages':0})
        report['checkpoint_mode_intervals'].append({
            **bounds,'single_tick_render_steps':150,
            'skips_in_single_tick_render_frames':0})
        report['checkpoint_release_poll_intervals'].append({
            **bounds,'full_before_poll':0,'recovered_before_admission':0})
    return rows,report


class ExactGuestACKDiscoveryTests(unittest.TestCase):
    def test_valid_900_tick_trace_reconciles_all_six_guest_windows(self):
        rows,report=fixture()
        result=ack.compare_trace(rows,report,'baseline')
        self.assertEqual(result['ack_pages_observed'],900)
        self.assertEqual(result['ack_discovery_ticks'],900)
        self.assertEqual(len(result['ack_discovery_windows']),6)
        self.assertEqual([r['released_pages'] for r
                          in result['ack_discovery_windows']],[150]*6)
        self.assertTrue(
            result['exact_simulation_tick_of_guest_ack_discovery_observed'])
        self.assertFalse(result['libnx_service_arrival_timestamp_observed'])
        self.assertFalse(result['physical_speaker_delivery_verified'])

    def test_guest_window_shift_and_release_forgery_rejected(self):
        rows,report=fixture()
        for mutation in ('release','skip','pending','full','recovered',
                         'submitted','frame','tick','mode'):
            r=copy.deepcopy(rows)
            record=copy.deepcopy(report)
            if mutation=='mode':
                with self.assertRaises(ValueError):
                    ack.compare_trace(r,record,'extra-poll')
                continue
            key={'release':'released','skip':'skipped',
                 'pending':'pending','full':'pre_poll_full',
                 'recovered':'pre_poll_recovered','submitted':'submitted',
                 'frame':'frame_id','tick':'tick'}[mutation]
            r[155][key]=0 if key in ('tick','frame_id','pending',
                                   'released','submitted') else 1
            with self.subTest(case=mutation),self.assertRaises(ValueError):
                ack.compare_trace(r,record,'baseline')

    def test_guest_summary_window_and_hash_aliases_fail_closed(self):
        rows,report=fixture()
        for case in ('window_end','pages','single_ticks','recovery','skip',
                     'finish_pending','midpoll'):
            forged=copy.deepcopy(report)
            if case=='window_end':
                forged['checkpoint_release_position_intervals'][2]['tick_end']=451
            if case=='pages':
                forged['checkpoint_release_position_intervals'][3][
                    'single_frame_released_pages']+=1
            if case=='single_ticks':
                forged['checkpoint_mode_intervals'][0][
                    'single_tick_render_steps']-=1
            if case=='recovery':
                forged['checkpoint_batch_position_poll_intervals'][4][
                    'single_recovered_after_poll']=1
            if case=='skip':
                forged['checkpoint_skipped_deltas'][2]=1
            if case=='finish_pending':
                forged['queue_pending_at_stress_end']=2
            if case=='midpoll':
                forged['checkpoint_guest_mid_batch_extra_poll_intervals'][1][
                    'poll_calls']=1
            with self.subTest(case=case),self.assertRaises(ValueError):
                ack.compare_trace(rows,forged,'baseline')

    def test_invalid_or_noncanonical_guest_csv_rejected(self):
        rows,_=fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ack.csv'
            def write(rows,header=ack.COLUMNS):
                with path.open('w',newline='',encoding='ascii') as stream:
                    out=csv.writer(stream)
                    out.writerow(header)
                    for row in rows:
                        out.writerow([row[k] for k in ack.COLUMNS])
            write(rows)
            raw,read=ack.parse_csv(path)
            self.assertEqual(len(read),900)
            self.assertTrue(raw.startswith(b'tick,frame_id'))
            path.write_bytes(raw.replace(b'1,1,1,0,1,0,0,1,0,0,0,1,0',
                                         b'01,1,1,0,1,0,0,1,0,0,0,1,0',1))
            with self.assertRaises(ValueError):
                ack.parse_csv(path)
            write(rows,header=['tick']+list(ack.COLUMNS))
            with self.assertRaises(ValueError):
                ack.parse_csv(path)
            write(rows[:-1])
            with self.assertRaises(ValueError):
                ack.parse_csv(path)
            path.unlink()
            path.symlink_to(Path(tmp)/'unavailable')
            with self.assertRaises(ValueError):
                ack.parse_csv(path)

    def test_counter_type_and_batch_order_rejected(self):
        rows,report=fixture()
        for key,val in (('tick',True),('released',2.0),
                        ('batch_size',0),('batch_size',16),
                        ('batch_position',1),('mid_released',1),
                        ('mid_calls',1),('audio_errors',1),
                        ('frame_id',0xffffffff+1)):
            with self.subTest(field=key,value=val):
                data=copy.deepcopy(rows)
                data[300][key]=val
                with self.assertRaises(ValueError):
                    ack.compare_trace(data,report,'baseline')

    def test_one_long_batched_frame_versus_one_single_tick_not_conflated(self):
        rows,report=fixture()
        # The adapter's max pages/tick is two; a two-page return is a
        # single release-bearing tick, NOT two sequential service times.
        rows[1]['released']=2
        rows[1]['pending']=0
        rows[1]['submitted']=1
        with self.assertRaises(ValueError):
            ack.compare_trace(rows,report,'baseline')


if __name__=='__main__':
    unittest.main()
