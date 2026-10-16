import json
import struct
import tempfile
from pathlib import Path
import unittest
import zlib

from tools.cps1_video import (decode_palette_word, build_palette, color_group_base,
                              gfxrom_bank_mapper, sprite_block_tiles, TOTAL_COLORS)
from tools.cps1_color_atlas import parse_snapshot, render_atlas

class PaletteTests(unittest.TestCase):
    def test_color_with_max_brightness_is_full_scale(self):
        self.assertEqual(decode_palette_word(0xffff), (255,255,255))
        self.assertEqual(decode_palette_word(0xff00), (255,0,0))
        self.assertEqual(decode_palette_word(0xf0f0), (0,255,0))
        self.assertEqual(decode_palette_word(0xf00f), (0,0,255))

    def test_brightness_floor_one_third(self):
        self.assertEqual(decode_palette_word(0x0fff), (85,85,85))
        self.assertEqual(decode_palette_word(0x0000), (0,0,0))

    def test_integer_truncation(self):
        self.assertEqual(decode_palette_word(0x8123), (17*31//45, 34*31//45, 51*31//45))

    def test_invalid_palette_words(self):
        for word in (-1,0x10000,'ff',3.14):
            with self.subTest(word=word), self.assertRaises(ValueError):
                decode_palette_word(word)

    def test_complete_six_pages(self):
        words = [0xf000 | (i%16 << 8) for i in range(TOTAL_COLORS)]
        pal = build_palette(words,0x3f)
        self.assertEqual(len(pal),TOTAL_COLORS)
        for page in range(6):
            self.assertEqual(pal[page*512+3], decode_palette_word(words[page*512+3]))

    def test_early_disabled_page_does_not_advance_source(self):
        words = [0xff00]*512 + [0xf0f0]*512 + [0xf00f]*512
        prev = [(9,8,7)]*TOTAL_COLORS
        pal = build_palette(words,0x0a,prev)  # pages 1 and 3
        self.assertEqual(pal[0], (9,8,7))
        self.assertEqual(pal[512], (255,0,0))
        self.assertEqual(pal[1024], (9,8,7))
        self.assertEqual(pal[1536], (0,0,255))

    def test_disabled_pages_preserved(self):
        prev = [(20,30,40)]*TOTAL_COLORS
        self.assertEqual(build_palette([],0,prev),prev)
        self.assertEqual(build_palette([0xffff]*512,1,prev)[512],(20,30,40))

    def test_short_palette_rejected(self):
        with self.assertRaises(ValueError): build_palette([],1)
        with self.assertRaises(ValueError): build_palette([0]*512,0x3f)
        with self.assertRaises(ValueError): build_palette([],0x40)
        with self.assertRaises(ValueError): build_palette([],0,[(0,0,0)]*20)

    def test_palette_group_offsets(self):
        self.assertEqual(color_group_base('sprites',0),0)
        self.assertEqual(color_group_base('sprites',31),496)
        self.assertEqual(color_group_base('scroll1',0),512)
        self.assertEqual(color_group_base('scroll2',31),1520)
        self.assertEqual(color_group_base('scroll3',7),1648)
        with self.assertRaises(ValueError): color_group_base('sprites',32)
        with self.assertRaises(ValueError): color_group_base('invalid',0)

class MapperTests(unittest.TestCase):
    def test_two_bank_boundaries_by_layer(self):
        for layer, max_code in [('sprites',0x7fff),('scroll1',0xffff),
                                ('scroll2',0x7fff),('scroll3',0x1fff)]:
            for code in (0,1,max_code//2,max_code//2+1,max_code):
                with self.subTest(layer=layer,code=code):
                    self.assertEqual(gfxrom_bank_mapper(layer,code),code)
            self.assertEqual(gfxrom_bank_mapper(layer,max_code+1),-1)

    def test_bad_layer_negative_code(self):
        self.assertEqual(gfxrom_bank_mapper('sprites',-1),-1)
        with self.assertRaises(ValueError): gfxrom_bank_mapper('stars1',0)
        with self.assertRaises(TypeError): gfxrom_bank_mapper('sprites','0')

class SpriteTests(unittest.TestCase):
    def test_single_sprite(self):
        self.assertEqual([(t.dx,t.dy,t.code) for t in sprite_block_tiles(0x31,0)],[(0,0,0x31)])

    def test_2x2_at_edge_of_16_code_row(self):
        tiles = sprite_block_tiles(0x3f,0x1100)
        self.assertEqual([(t.dx,t.dy,t.code) for t in tiles],
                         [(0,0,0x3f),(16,0,0x30),(0,16,0x4f),(16,16,0x40)])

    def test_flip_horizontal_vertical(self):
        a = sprite_block_tiles(0x30,0x1160)
        self.assertEqual([t.code for t in a],[0x41,0x40,0x31,0x30])
        self.assertTrue(all(t.flip_x and t.flip_y for t in a))

    def test_bad_sprite_metadata(self):
        with self.assertRaises(ValueError): sprite_block_tiles(-1,0)
        with self.assertRaises(ValueError): sprite_block_tiles(0,0x10000)

class AtlasTests(unittest.TestCase):
    def test_palette_json_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'palette.json'
            p.write_text(json.dumps({'control':'0x01','words':['0xff00',0xf0f0,0xf00f]}))
            self.assertEqual(parse_snapshot(p),(1,[0xff00,0xf0f0,0xf00f]))

    def test_palette_json_bad_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'palette.json'
            p.write_text(json.dumps({'control': 1,'words':[True]}))
            with self.assertRaises(ValueError): parse_snapshot(p)

    def test_atlas_png_uses_palette_rgb_and_transparency(self):
        # A single synthetic 16x16 plane encoded with pen=1 except one pen=15.
        region=bytearray(128)
        for y in range(16):
            for x in range(16):
                pen = 15 if (x,y)==(0,0) else 1
                b=y*8+(x//8)*4
                for bitplane in range(4):
                    if pen & (1<<bitplane): region[b+3-bitplane] |= 1<<(7-x%8)
        palette=[(0,0,0)]*TOTAL_COLORS
        palette[1]=(12,23,34)
        png=render_atlas(region,palette,scale=1,count=1,columns=1)
        self.assertEqual(png[:8],b'\x89PNG\r\n\x1a\n')
        at=8
        chunks={}
        while at<len(png):
            n=struct.unpack('>I',png[at:at+4])[0]
            tag=png[at+4:at+8]
            chunks[tag]=png[at+8:at+8+n]
            at+=12+n
        scan=zlib.decompress(chunks[b'IDAT'])
        self.assertEqual(scan[1:5], bytes((0,0,0,0)))
        self.assertEqual(scan[5:9], bytes((12,23,34,255)))


    def test_scroll1_half_selection(self):
        palette=[(0,0,0)]*TOTAL_COLORS
        palette[513]=(255,0,0)
        # Scroll1 left-half plane sets one red pixel, right-half stays clear.
        region=bytearray(64)
        region[3]=0x80
        left=render_atlas(region,palette,layer='scroll1',count=1,scale=1,scroll1_half='left')
        right=render_atlas(region,palette,layer='scroll1',count=1,scale=1,scroll1_half='right')
        self.assertNotEqual(left,right)
        with self.assertRaises(ValueError):
            render_atlas(region,palette,layer='scroll1',scroll1_half='top')

    def test_invalid_atlas_range(self):
        with self.assertRaises(ValueError): render_atlas(bytes(128),[(0,0,0)]*TOTAL_COLORS,count=0)
        with self.assertRaises(ValueError): render_atlas(bytes(128),[(0,0,0)]*TOTAL_COLORS,layer='stars1')

if __name__ == '__main__': unittest.main()
