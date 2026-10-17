"""ROM-free multi-frame MAME register alignment and capture-integrity tests."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zlib

from tools.mame_obj_sequence_alignment import (
    audit_sequence, read_frames, main, COMPONENTS, CAPTURE_SCHEMA,
)


def sample(n):
    return bytes(((i*19+n*73) & 255) for i in range(128))


def series(n=6):
    return [sample(i) for i in range(n)]


def split_regs(blob):
    return blob[:64], blob[64:]


def make_directory(directory, renders, lua, first=900, step=2):
    for idx, (render, other) in enumerate(zip(renders, lua)):
        frame=first+idx*step
        stem=f'frame-{frame:08d}'
        a,b=split_regs(other)
        crc={name:'00000000' for name in COMPONENTS}
        crc['cps-a-be.bin']=f'{zlib.crc32(a) & 0xffffffff:08x}'
        crc['cps-b-be.bin']=f'{zlib.crc32(b) & 0xffffffff:08x}'
        manifest={
            'game':'dino', 'frame':frame, 'capture_hook':'frame_done',
            'obj_latch':'NOT_CAPTURED', 'pixel_parity_eligible':False,
            'file_crc32':crc,
            **CAPTURE_SCHEMA,
        }
        (directory/(stem+'.manifest.json')).write_text(json.dumps(manifest))
        (directory/(stem+'.cps-a-be.bin')).write_bytes(a)
        (directory/(stem+'.cps-b-be.bin')).write_bytes(b)
        (directory/(stem+'.render-regs-be.bin')).write_bytes(render)
        (directory/(stem+'.buffered-obj-be.bin')).write_bytes(bytes(2048))


class MultiframeAlignmentTests(unittest.TestCase):
    def test_detects_one_capture_step_offset_but_not_sync(self):
        render=series()
        lua=[sample(55)]+render[:-1]
        report=audit_sequence(render,lua,2,2)
        self.assertEqual(report['best_offset_steps'],1)
        self.assertEqual(report['best_offset_nominal_frames'],2)
        self.assertEqual(report['best_overlap_pairs'],5)
        self.assertTrue(report['offset_hypothesis_informative'])
        self.assertEqual(report['ambiguous_best_offsets'],[])
        self.assertFalse(report['frame_sync_verified'])
        self.assertFalse(report['pixel_parity_eligible'])

    def test_aligned_variable_frames_choose_zero(self):
        render=series()
        report=audit_sequence(render,render,2,2)
        self.assertEqual(report['best_offset_steps'],0)
        self.assertEqual(report['best_overlap_pairs'],6)
        self.assertTrue(report['offset_hypothesis_informative'])
        self.assertFalse(report['frame_sync_verified'])

    def test_all_static_registers_are_ambiguous(self):
        frames=[bytes(128)]*6
        result=audit_sequence(frames,frames,2,2)
        self.assertEqual(result['best_offset_steps'],0)
        self.assertEqual(result['ambiguous_best_offsets'],[-2,-1,0,1,2])
        self.assertFalse(result['offset_hypothesis_informative'])
        self.assertEqual(result['render_distinct_register_states'],1)

    def test_repeated_two_state_cycle_is_ambiguous(self):
        frames=[sample(i%2) for i in range(6)]
        report=audit_sequence(frames,frames,2,2)
        self.assertEqual(report['ambiguous_best_offsets'],[-2,0,2])
        self.assertFalse(report['offset_hypothesis_informative'])

    def test_no_matching_frames_cannot_be_informative(self):
        result=audit_sequence(series(),[sample(i+60) for i in range(6)],2,2)
        self.assertEqual(max(x['exact_equal_pairs'] for x in result['candidates']),0)
        self.assertFalse(result['offset_hypothesis_informative'])

    def test_edge_overlap_reported_not_full_coverage(self):
        frames=series()
        result=audit_sequence(frames, [sample(99),sample(98)]+frames[:4],2,2)
        self.assertEqual(result['best_offset_steps'],2)
        self.assertEqual(result['best_overlap_pairs'],4)
        self.assertEqual(result['candidates'][-1]['compared_pairs'],4)

    def test_validates_bounds_and_exact_128_byte_frames(self):
        frames=series()
        for left,right,step,limit in (
            (frames[:3],frames[:3],2,1),
            (frames,frames[:5],2,1),
            (frames,frames,0,1),
            (frames,frames,2,4),
            (frames,frames,True,1),
            (frames,frames,2,True),
            (frames,[bytearray(128)]*6,2,1),
            (frames,[bytes(127)]*6,2,1)):
            with self.subTest(step=step,limit=limit):
                with self.assertRaises(ValueError):
                    audit_sequence(left,right,step,limit)

    def test_loader_reads_complete_crc_bound_capture(self):
        frames=series()
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name)
            make_directory(directory,frames,frames)
            render,lua=read_frames(directory,900,6,2)
            self.assertEqual(render,frames)
            self.assertEqual(lua,frames)

    def test_loader_rejects_same_length_register_mutation(self):
        frames=series()
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name)
            make_directory(directory,frames,frames)
            file=directory/'frame-00000904.cps-b-be.bin'
            corrupted=bytearray(file.read_bytes())
            corrupted[5]^=1
            file.write_bytes(corrupted)
            with self.assertRaisesRegex(ValueError,'CRC32 mismatch'):
                read_frames(directory,900,6,2)

    def test_loader_rejects_missing_obj_probe_or_bad_size(self):
        frames=series()
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name)
            make_directory(directory,frames,frames)
            file=directory/'frame-00000906.buffered-obj-be.bin'
            file.write_bytes(bytes(2047))
            with self.assertRaisesRegex(ValueError,'incomplete'):
                read_frames(directory,900,6,2)

    def test_loader_rejects_malformed_or_missing_manifest_checksums(self):
        frames=series()
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name)
            make_directory(directory,frames,frames)
            path=directory/'frame-00000900.manifest.json'
            original=json.loads(path.read_text())
            for crc in (None, {}, dict(original['file_crc32'], extra='12345678')):
                manifest=dict(original)
                manifest['file_crc32']=crc
                path.write_text(json.dumps(manifest))
                with self.subTest(crc=crc):
                    with self.assertRaisesRegex(ValueError,'file_crc32'):
                        read_frames(directory,900,6,2)
            path.write_text(json.dumps(original))

    def test_loader_rejects_forged_frame_metadata(self):
        frames=series()
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name)
            make_directory(directory,frames,frames)
            path=directory/'frame-00000900.manifest.json'
            manifest=json.loads(path.read_text())
            for key,value in (('frame',901),('frame',True),('game','sf2'),
                              ('obj_latch','CAPTURED'),
                              ('pixel_parity_eligible',True),
                              ('capture_hook','before_render')):
                wrong=dict(manifest)
                wrong[key]=value
                path.write_text(json.dumps(wrong))
                with self.subTest(key=key,value=value):
                    with self.assertRaisesRegex(ValueError,'provenance'):
                        read_frames(directory,900,6,2)

    def test_loader_rejects_bad_original_capture_geometry_or_endianness(self):
        frames=series()
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name)
            make_directory(directory,frames,frames)
            path=directory/'frame-00000900.manifest.json'
            original=json.loads(path.read_text())
            for field,value in (('reference_width', 512),
                                ('raw_word_endianness', 'little'),
                                ('gfxram_bytes', 0x40000),
                                ('palette_bytes', True)):
                modified=dict(original)
                modified[field]=value
                path.write_text(json.dumps(modified))
                with self.subTest(field=field):
                    with self.assertRaisesRegex(ValueError,'capture schema'):
                        read_frames(directory,900,6,2)

    def test_cli_writes_only_new_metadata_report(self):
        frames=series()
        with tempfile.TemporaryDirectory() as name:
            directory=Path(name)
            make_directory(directory,frames,frames)
            result=directory/'local-report.json'
            args=[str(directory),'--first-frame','900','--frame-count','6',
                  '--frame-step','2','--max-offset-steps','2',
                  '--out',str(result)]
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(args),0)
            doc=json.loads(result.read_text())
            self.assertEqual(doc['best_offset_steps'],0)
            self.assertEqual(len(doc['probe_register_sha256']),6)
            self.assertFalse(doc['frame_sync_verified'])
            self.assertNotIn('render_register_bytes',doc)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(args),2)
            self.assertEqual(json.loads(result.read_text()),doc)

    def test_loader_rejects_invalid_range_without_reading_files(self):
        for first,count,step in ((0,3,2),(-1,6,2),
                                 (99999999,6,2),(900,25,2),
                                 (900,6,0),(True,6,2)):
            with self.subTest(first=first,count=count,step=step):
                with self.assertRaisesRegex(ValueError,'frame selection'):
                    read_frames('/not/a/real/directory',first,count,step)


if __name__ == '__main__':
    unittest.main()
