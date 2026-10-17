"""End-to-end, ROM-free MAME register capture CLI tests with real files.

All records are synthetic and remain in a private temporary directory.
"""
import contextlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from tools.mame_obj_sequence_alignment import main, COMPONENTS, CAPTURE_SCHEMA


def states(count):
    words = [0] * 64
    output = [struct.pack('>64H', *words)]
    for index in range(1, count):
        words[(index * 7) % 64] += 1
        output.append(struct.pack('>64H', *words))
    return output


def make_capture(root, *, count=6, shift=0, flat=False, cycle=False):
    render = states(count)
    if flat:
        render = [bytes(128)] * count
    if cycle:
        words = [0] * 64
        render = [struct.pack('>64H', *words)]
        for index in range(1, count):
            words[index % 2] += 1
            render.append(struct.pack('>64H', *words))
    lua = [bytes([100 + i]) * 128 for i in range(shift)] + render[:count-shift]
    for index, (probe, reference) in enumerate(zip(render, lua)):
        stem = f'frame-{900 + index * 2:08d}'
        a, b = reference[:64], reference[64:]
        checksums = {name: '00000000' for name in COMPONENTS}
        checksums['cps-a-be.bin'] = f'{zlib.crc32(a) & 0xffffffff:08x}'
        checksums['cps-b-be.bin'] = f'{zlib.crc32(b) & 0xffffffff:08x}'
        manifest = dict(
            game='dino', frame=900 + index * 2, capture_hook='frame_done',
            pixel_parity_eligible=False, obj_latch='NOT_CAPTURED',
            file_crc32=checksums, **CAPTURE_SCHEMA)
        (root / (stem + '.manifest.json')).write_text(json.dumps(manifest))
        (root / (stem + '.cps-a-be.bin')).write_bytes(a)
        (root / (stem + '.cps-b-be.bin')).write_bytes(b)
        (root / (stem + '.render-regs-be.bin')).write_bytes(probe)
        (root / (stem + '.buffered-obj-be.bin')).write_bytes(bytes(2048))
    return render, lua


def invoke(root, *, count=6, output=None):
    target = output if output is not None else root / 'audit.json'
    args = [str(root), '--first-frame', '900', '--frame-count', str(count),
            '--frame-step', '2', '--max-offset-steps', '2', '--out', str(target)]
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        status = main(args)
    return status, json.loads(target.read_text()) if status == 0 else None


class EndToEndMameCliTests(unittest.TestCase):
    def test_aligned_full_capture_produces_conservative_consensus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            code, doc = invoke(root)
            self.assertEqual(code, 0)
            self.assertEqual(doc['diagnostic_verdict']['status'], 'CONSISTENT_BUT_UNVERIFIED')
            self.assertEqual(doc['diagnostic_verdict']['diagnostic_candidate_offset_steps'], 0)
            self.assertEqual(doc['transition_stability']['leave_one_out_trial_count'], 5)
            self.assertFalse(doc['frame_sync_verified'])
            self.assertFalse(doc['diagnostic_verdict']['pixel_parity_eligible'])
            self.assertEqual(len(doc['probe_register_sha256']), 6)

    def test_one_sample_shift_produces_diagnostic_not_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root, shift=1)
            status, doc = invoke(root)
            self.assertEqual(status, 0)
            self.assertEqual(doc['best_offset_steps'], 1)
            self.assertEqual(doc['transition_analysis']['transition_best_offset_steps'], 1)
            self.assertEqual(doc['diagnostic_verdict']['status'], 'CONSISTENT_BUT_UNVERIFIED')
            self.assertEqual(doc['diagnostic_verdict']['diagnostic_candidate_offset_steps'], 1)
            self.assertEqual(doc['diagnostic_verdict']['independent_physical_measurement_count'], 0)

    def test_short_capture_two_step_shift_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root, shift=2)
            status, doc = invoke(root)
            self.assertEqual(status, 0)
            self.assertEqual(doc['transition_analysis']['transition_assessment'],
                             'INSUFFICIENT_OVERLAP')
            self.assertEqual(doc['diagnostic_verdict']['status'], 'EXACT_ONLY_UNCORROBORATED')
            self.assertIsNone(doc['diagnostic_verdict']['diagnostic_candidate_offset_steps'])

    def test_long_capture_two_step_shift_has_real_overlap(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root, count=10, shift=2)
            status, doc = invoke(root, count=10)
            self.assertEqual(status, 0)
            self.assertEqual(doc['diagnostic_verdict']['status'], 'CONSISTENT_BUT_UNVERIFIED')
            self.assertEqual(doc['diagnostic_verdict']['diagnostic_candidate_offset_steps'], 2)
            self.assertTrue(doc['transition_stability']['leave_one_out_stable'])

    def test_static_registers_remain_inconclusive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root, flat=True)
            status, doc = invoke(root)
            self.assertEqual(status, 0)
            self.assertEqual(doc['diagnostic_verdict']['status'], 'INSUFFICIENT_REGISTER_EVIDENCE')
            self.assertIsNone(doc['diagnostic_verdict']['diagnostic_candidate_offset_steps'])

    def test_repeated_change_masks_are_not_independent_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root, cycle=True)
            status, doc = invoke(root)
            self.assertEqual(status, 0)
            self.assertEqual(doc['diagnostic_verdict']['status'], 'EXACT_ONLY_UNCORROBORATED')
            self.assertFalse(doc['transition_analysis']['transition_hypothesis_informative'])

    def test_same_length_lua_register_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            path = root / 'frame-00000904.cps-b-be.bin'
            raw = bytearray(path.read_bytes())
            raw[5] ^= 1
            path.write_bytes(raw)
            code, doc = invoke(root)
            self.assertEqual(code, 2)
            self.assertIsNone(doc)
            self.assertFalse((root / 'audit.json').exists())

    def test_truncated_buffered_obj_cannot_create_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            (root / 'frame-00000900.buffered-obj-be.bin').write_bytes(bytes(2047))
            status, _ = invoke(root)
            self.assertEqual(status, 2)
            self.assertFalse((root / 'audit.json').exists())

    def test_wrong_nominal_frame_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            path = root / 'frame-00000906.manifest.json'
            manifest = json.loads(path.read_text())
            manifest['frame'] = 908
            path.write_text(json.dumps(manifest))
            self.assertEqual(invoke(root)[0], 2)

    def test_missing_crc_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            path = root / 'frame-00000900.manifest.json'
            manifest = json.loads(path.read_text())
            del manifest['file_crc32']
            path.write_text(json.dumps(manifest))
            self.assertEqual(invoke(root)[0], 2)

    def test_existing_destination_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            target = root / 'audit.json'
            target.write_text('do not overwrite')
            code, _ = invoke(root)
            self.assertEqual(code, 2)
            self.assertEqual(target.read_text(), 'do not overwrite')

    def test_missing_cpp_register_probe_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            (root / 'frame-00000902.render-regs-be.bin').unlink()
            code, _ = invoke(root)
            self.assertEqual(code, 2)
            self.assertFalse((root / 'audit.json').exists())

    def test_metadata_report_does_not_include_raw_register_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            status, doc = invoke(root)
            self.assertEqual(status, 0)
            text = (root / 'audit.json').read_text()
            self.assertNotIn('buffered_obj_words', text)
            self.assertNotIn('render_register_bytes', text)
            self.assertNotIn('cps_a_words', text)
            self.assertTrue(doc['diagnostic_verdict']['diagnostic_only'])

    def test_real_python_command_writes_valid_json(self):
        # Execute the actual user-facing command, not just imported main().
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            script = Path(__file__).resolve().parents[1] / 'tools' / 'mame_obj_sequence_alignment.py'
            cmd = [sys.executable, str(script), str(root), '--out',
                   str(root / 'subprocess-audit.json')]
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  cwd=script.parents[1], timeout=10)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads((root / 'subprocess-audit.json').read_text())
            self.assertEqual(report['diagnostic_verdict']['status'],
                             'CONSISTENT_BUT_UNVERIFIED')
            self.assertFalse(report['diagnostic_verdict']['frame_sync_verified'])

    def test_real_python_command_rejects_corruption_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            (root / 'frame-00000900.buffered-obj-be.bin').write_bytes(bytes(2047))
            script = Path(__file__).resolve().parents[1] / 'tools' / 'mame_obj_sequence_alignment.py'
            output = root / 'refused.json'
            proc = subprocess.run([sys.executable, str(script), str(root),
                                   '--out', str(output)], capture_output=True,
                                  text=True, cwd=script.parents[1], timeout=10)
            self.assertEqual(proc.returncode, 2)
            self.assertIn('incomplete', proc.stderr)
            self.assertFalse(output.exists())

    def test_unbounded_frame_selection_is_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            make_capture(root)
            status, _ = invoke(root, count=30)
            self.assertEqual(status, 2)
            self.assertFalse((root / 'audit.json').exists())


if __name__ == '__main__':
    unittest.main()
