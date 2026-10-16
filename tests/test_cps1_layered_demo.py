"""No-ROM regressions for CPS1SEQ1 multilayer Switch diagnostic demo."""
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

from tools.cps1_layered_demo import (demo_snapshots, make_tilemap,
                                     tile_index, make_palette, main)
from tools.cps1_scene_export import pack_scene
from tools.cps1_sequence_export import pack_sequence
from tools.cps1_frame import render_frame


class LayeredDemoTests(unittest.TestCase):
    def test_grid_is_permutation_of_4096_map_entries(self):
        for name in ('scroll1', 'scroll2', 'scroll3'):
            seen = {tile_index(name, x, y) for x in range(64) for y in range(64)}
            self.assertEqual(len(seen), 4096)
            self.assertEqual(seen, set(range(4096)))
            self.assertEqual(len(make_tilemap(name)), 8192)

    def test_synthetic_palette_has_3072_valid_rgb_entries(self):
        palette = make_palette()
        self.assertEqual(len(palette), 3072)
        self.assertTrue(all(len(color) == 3 and all(0 <= c <= 255 for c in color)
                            for color in palette))
        self.assertEqual(palette[0xbff], [15, 21, 31])

    def test_three_scroll_layers_and_raster_line_motion(self):
        snaps = demo_snapshots(36)
        self.assertEqual(len(snaps), 36)
        self.assertEqual([snaps[-1][n]['scrollx'] for n in
                          ('scroll1', 'scroll2', 'scroll3')], [140, 70, 11])
        for scene in (snaps[0], snaps[18], snaps[-1]):
            self.assertEqual(scene['video_control'] & 1, 1)
            self.assertTrue(all(scene[n]['enabled'] for n in ('scroll1','scroll2','scroll3')))
            self.assertEqual(len(scene['rowscroll']), 1024)
            self.assertEqual(scene['rowscroll'][25], (16//12+scene['scroll2']['scrollx'])&31)
            self.assertEqual(scene['buffered_obj_words'][-1], 0xff00)
            self.assertEqual(len(scene['buffered_obj_words']), 16)
            self.assertEqual(scene['demo_type'], 'SYNTHETIC_MULTI_LAYER_NOT_GAMEPLAY')

    def test_two_frames_are_different_and_each_has_three_sprites(self):
        first, last = demo_snapshots(36)[::35]
        self.assertNotEqual(first['buffered_obj_words'][:12], last['buffered_obj_words'][:12])
        self.assertNotEqual(first['scroll1']['scrollx'], last['scroll1']['scrollx'])
        self.assertEqual(first['palette_rgb'], last['palette_rgb'])
        self.assertEqual(first['scroll2']['words'], last['scroll2']['words'])

    def test_pack_scene_and_sequence_crc_contract(self):
        blobs = [pack_scene(scene) for scene in demo_snapshots(3)]
        self.assertEqual(set(map(len, blobs)), {62510})
        seq = pack_sequence(blobs, 12)
        self.assertEqual(seq[:8], b'CPS1SEQ1')
        self.assertEqual(len(seq), 20 + 62510*3)
        self.assertEqual(struct.unpack_from('<HH', seq, 8), (3, 12))
        self.assertEqual(zlib.crc32(seq[20:]), struct.unpack_from('<I', seq, 12)[0])
        self.assertEqual(seq[20:28], b'CPS1SCN1')
        self.assertEqual(seq[20+62510:20+62510+8], b'CPS1SCN1')

    def test_compositing_changes_over_frames_without_rom(self):
        scenes = demo_snapshots(2)
        gfx = bytearray(0x400000)
        for tile in range(512):
            for y in range(16):
                gfx[tile*128+y*8+3] = (tile*13+y*5)&255
                gfx[tile*128+y*8+7] = (tile*7+y*9)&255
        a = render_frame(gfx, scenes[0]['palette_rgb'], scenes[0])
        b = render_frame(gfx, scenes[1]['palette_rgb'], scenes[1])
        self.assertEqual(len(a), 384*224*4)
        self.assertNotEqual(a, b)

    def test_reject_invalid_counts_and_preserve_cli_outputs(self):
        for count in (0,121,-4,True,1.2):
            with self.assertRaises(ValueError):
                demo_snapshots(count)
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'sequence.bin'
            report = Path(temp)/'report.json'
            args = ['--frames','2','--fps','12','--out',str(target),'--report',str(report)]
            self.assertEqual(main(args), 0)
            self.assertIs(json.loads(report.read_text())['authentic_gameplay'],False)
            self.assertEqual(target.stat().st_size, 20+62510*2)
            self.assertEqual(main(args), 2)
            self.assertEqual(main(['--frames','1','--fps','0',
                                   '--out',str(target),'--report',str(report)]), 2)


if __name__=='__main__':
    unittest.main()
