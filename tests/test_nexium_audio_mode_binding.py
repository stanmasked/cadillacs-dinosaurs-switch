"""ROM-free binding of the selected NRO audio mode to guest witnesses."""
from contextlib import redirect_stdout
from io import StringIO
import hashlib
import hashlib
import json
import struct
from pathlib import Path
import tempfile
import unittest

from tools import verify_nexium_audio_mode_binding as binding
from test_nexium_audio_mid_batch_ab import complete


def synthetic_nro(label):
    """Synthetic file with bounded NRO header; never original game bytes."""
    data=bytearray(256)
    data[0x10:0x14]=b'NRO0'
    struct.pack_into('<I',data,0x18,len(data))
    payload=label.encode('ascii')
    data[0x80:0x80+len(payload)]=payload
    return bytes(data)


class GuestAudioModeBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='dino-audio-mode-')
        self.report=Path(self.temp.name)/'guest.json'

    def tearDown(self):
        self.temp.cleanup()

    def write(self,enabled=False,variation=0):
        report=complete(enabled,variation)
        self.report.write_text(json.dumps(report,sort_keys=True)+'\n',
                               encoding='ascii')
        return report

    def test_baseline_mode_requires_zero_guest_extra_polls(self):
        self.write(False)
        result=binding.attest('baseline',self.report)
        self.assertEqual(result['status'],'SELECTED_AUDIO_MODE_WITNESSED_BY_GUEST')
        self.assertEqual(result['selected_mode'],'baseline')
        self.assertFalse(result['guest_poll_enabled'])
        self.assertEqual(result['guest_poll_calls'],0)
        self.assertEqual(result['guest_poll_released_pages'],0)
        self.assertEqual(result['guest_simulation_ticks'],900)
        self.assertFalse(result['audio_latency_verified'])
        self.assertFalse(result['causal_audio_improvement_verified'])

    def test_experimental_mode_requires_guest_extra_poll_evidence(self):
        self.write(True,1)
        result=binding.attest('extra-poll',self.report)
        self.assertEqual(result['status'],'SELECTED_AUDIO_MODE_WITNESSED_BY_GUEST')
        self.assertEqual(result['selected_mode'],'extra-poll')
        self.assertTrue(result['guest_poll_enabled'])
        self.assertEqual(result['guest_poll_calls'],150)
        self.assertEqual(result['guest_poll_released_pages'],6)
        self.assertEqual(result['guest_later_batch_steps'],150)
        self.assertFalse(result['physical_switch_audio_verified'])

    def test_requested_mode_must_equal_guest_report_mode(self):
        for requested,enabled in (('baseline',True),('extra-poll',False)):
            with self.subTest(requested=requested):
                self.write(enabled)
                with self.assertRaises(ValueError):
                    binding.attest(requested,self.report)

    def test_guest_poll_forgery_is_rejected_even_when_flag_matches(self):
        report=self.write(True,1)
        report['guest_mid_batch_extra_poll_calls']-=1
        self.report.write_text(json.dumps(report)+'\n',encoding='ascii')
        with self.assertRaises(ValueError):
            binding.attest('extra-poll',self.report)

    def test_report_needs_full_guest_900tick_invariants(self):
        report=self.write(False)
        report['audout_blocks_skipped']+=1
        self.report.write_text(json.dumps(report)+'\n',encoding='ascii')
        with self.assertRaises(ValueError):
            binding.attest('baseline',self.report)

    def test_missing_or_invalid_mode_is_never_assumed_baseline(self):
        self.write(False)
        for requested in ('','experimental','BASELINE',None):
            with self.subTest(requested=requested):
                with self.assertRaises(ValueError):
                    binding.attest(requested,self.report)
        with self.assertRaises(ValueError):
            binding.attest('baseline',self.report.with_name('absent.json'))

    def test_cli_valid_mode_reports_success_with_no_hardware_claims(self):
        self.write(True,1)
        captured=StringIO()
        with redirect_stdout(captured):
            rc=binding.main(['--selected-mode','extra-poll',
                             '--report',str(self.report)])
        self.assertEqual(rc,0)
        report=json.loads(captured.getvalue())
        self.assertEqual(report['selected_mode'],'extra-poll')
        self.assertFalse(report['original_arcade_audio_verified'])
        self.assertFalse(report['physical_switch_audio_verified'])

    def test_guest_report_hash_binds_exact_raw_report(self):
        self.write(False)
        raw=self.report.read_bytes()
        result=binding.attest('baseline',self.report)
        self.assertEqual(result['guest_report_sha256'],
                         hashlib.sha256(raw).hexdigest())
        self.assertEqual(len(result['guest_report_sha256']),64)

    def test_cli_writes_new_mode_attestation_without_overwriting_input(self):
        self.write(True,1)
        raw=self.report.read_bytes()
        destination=Path(self.temp.name)/'mode-binding.json'
        captured=StringIO()
        with redirect_stdout(captured):
            rc=binding.main(['--selected-mode','extra-poll',
                             '--report',str(self.report),
                             '--out',str(destination)])
        self.assertEqual(rc,0)
        self.assertEqual(self.report.read_bytes(),raw)
        self.assertEqual(destination.read_text(encoding='ascii'),
                         captured.getvalue())
        result=json.loads(captured.getvalue())
        self.assertEqual(result['guest_report_sha256'],
                         hashlib.sha256(raw).hexdigest())
        self.assertEqual(result['status'],'SELECTED_AUDIO_MODE_WITNESSED_BY_GUEST')

    def test_cli_never_overwrites_existing_guest_input(self):
        self.write(False)
        original=self.report.read_bytes()
        captured=StringIO()
        with redirect_stdout(captured):
            rc=binding.main(['--selected-mode','baseline',
                             '--report',str(self.report),
                             '--out',str(self.report)])
        self.assertEqual(rc,1)
        self.assertEqual(self.report.read_bytes(),original)
        result=json.loads(captured.getvalue())
        self.assertEqual(result['reason'],'FileExistsError')
        self.assertFalse(result['causal_audio_improvement_verified'])

    def test_cli_never_replaces_previous_mode_attestation(self):
        self.write(False)
        destination=Path(self.temp.name)/'prior-mode-binding.json'
        destination.write_text('KEEP_PREVIOUS_ATTESTATION\n',encoding='ascii')
        captured=StringIO()
        with redirect_stdout(captured):
            rc=binding.main(['--selected-mode','baseline',
                             '--report',str(self.report),
                             '--out',str(destination)])
        self.assertEqual(rc,1)
        self.assertEqual(destination.read_text(encoding='ascii'),
                         'KEEP_PREVIOUS_ATTESTATION\n')
        self.assertEqual(json.loads(captured.getvalue())['reason'],'FileExistsError')

    def test_cli_never_follows_symlink_output_to_guest_input(self):
        import os
        if not hasattr(os,'symlink'):
            self.skipTest('symlink unavailable')
        self.write(False)
        alias=Path(self.temp.name)/'alias.json'
        alias.symlink_to(self.report)
        original=self.report.read_bytes()
        captured=StringIO()
        with redirect_stdout(captured):
            rc=binding.main(['--selected-mode','baseline',
                             '--report',str(self.report),
                             '--out',str(alias)])
        self.assertEqual(rc,1)
        self.assertTrue(alias.is_symlink())
        self.assertEqual(self.report.read_bytes(),original)
        self.assertEqual(json.loads(captured.getvalue())['reason'],'FileExistsError')

    def test_devkitpro_container_build_uses_posix_sh_fail_fast(self):
        # GitHub container jobs invoke /bin/sh -e by default. dash
        # rejects `set -o pipefail` before make can build the NRO.
        workflow=(Path(__file__).resolve().parents[1]/
                  '.github/workflows/nexium-guest-replay.yml').read_text(
                      encoding='utf-8')
        build_step=workflow.split(
            '      - name: Configure devkitPro and compile selected ROM-free Switch guest mode',1
        )[1].split('      - uses: actions/upload-artifact@v4',1)[0]
        self.assertIn('          set -eu\n',build_step)
        self.assertNotIn('set -euo pipefail',build_step)
        self.assertIn('make -j2 DEFINES="$defines"',build_step)
        self.assertIn('case "$DINO_AUDIO_MODE" in',build_step)

    def test_pr_workflow_runs_both_guest_audio_modes_without_manual_dispatch(self):
        # The workflow exists on this PR branch, not yet on main.
        # GitHub requires main presence for workflow_dispatch to work,
        # so a PR matrix covers both variants without changing main.
        workflow=(Path(__file__).resolve().parents[1]/
                  '.github/workflows/nexium-guest-replay.yml').read_text(
                      encoding='utf-8')
        self.assertEqual(workflow.count('audio_mode: ${{ fromJSON('),2)
        self.assertIn('github.event_name == \'pull_request\'',workflow)
        self.assertIn('["baseline","extra-poll"]',workflow)
        self.assertIn('github.event_name == \'workflow_dispatch\'',workflow)
        self.assertIn("'[\"baseline\"]'",workflow)
        # Build, NRO integrity, actual guest execution and post-run binding
        # must all carry the same matrix-selected audio mode explicitly.
        self.assertEqual(workflow.count('DINO_AUDIO_MODE: ${{ matrix.audio_mode }}'),4)
        self.assertIn('      - name: Attempt actual ARM64 homebrew guest execution\n'
                      '        env:\n'
                      '          DINO_AUDIO_MODE: ${{ matrix.audio_mode }}',workflow)
        self.assertIn('name: dino-nexium-selftest-nro-${{ matrix.audio_mode }}',workflow)
        self.assertIn(
            'name: dino-ne-xium-actual-nro-guest-evidence-${{ matrix.audio_mode }}',
            workflow)
        self.assertIn('      fail-fast: false',workflow)

    def test_real_nro_digest_is_bound_to_selected_guest_report(self):
        self.write(False)
        nro=Path(self.temp.name)/'switch-baseline.nro'
        nro.write_bytes(synthetic_nro('ROM_FREE_GUEST'))
        result=binding.attest('baseline',self.report,nro)
        self.assertEqual(result['guest_nro_sha256'],
                         hashlib.sha256(nro.read_bytes()).hexdigest())

    def test_nro_mutation_and_symlink_are_rejected(self):
        self.write(False)
        nro=Path(self.temp.name)/'switch-test.nro'
        nro.write_bytes(b'\x00'*16+b'BAD!'+b'BAD_HEADER'*16)
        with self.assertRaises(ValueError):
            binding.attest('baseline',self.report,nro)
        nro.unlink()
        target=Path(self.temp.name)/'real.nro'
        target.write_bytes(synthetic_nro('ROM_FREE'))
        nro.symlink_to(target)
        with self.assertRaises(ValueError):
            binding.attest('baseline',self.report,nro)

    def test_nro_declared_size_must_fit_bounded_executable(self):
        self.write(False)
        nro=Path(self.temp.name)/'bad-declared-size.nro'
        for declared in (0,0x7f,257,0xffffffff):
            with self.subTest(declared=declared):
                data=bytearray(synthetic_nro('SIZE_CHECK'))
                struct.pack_into('<I',data,0x18,declared)
                nro.write_bytes(data)
                with self.assertRaisesRegex(ValueError,'declared program size'):
                    binding.attest('baseline',self.report,nro)

    def test_nro_program_size_may_exclude_extra_assets(self):
        self.write(False)
        nro=Path(self.temp.name)/'assets.nro'
        payload=synthetic_nro('ROM_FREE')+b'ROM_FREE_TEST_ASSET_BYTES'
        nro.write_bytes(payload)
        result=binding.attest('baseline',self.report,nro)
        self.assertEqual(result['guest_nro_sha256'],
                         hashlib.sha256(payload).hexdigest())

    def test_cli_guest_mode_mismatch_fails_closed(self):
        self.write(False)
        captured=StringIO()
        with redirect_stdout(captured):
            rc=binding.main(['--selected-mode','extra-poll',
                             '--report',str(self.report)])
        self.assertEqual(rc,1)
        report=json.loads(captured.getvalue())
        self.assertEqual(report['status'],
                         'INCONCLUSIVE_AUDIO_MODE_NOT_GUEST_BOUND')
        self.assertFalse(report['causal_audio_improvement_verified'])


if __name__=='__main__':
    unittest.main()
