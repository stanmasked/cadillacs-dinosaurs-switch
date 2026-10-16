"""CPS-1 MAME gfx_element composite OBJ wrapping at 16x16 ROM bank boundary.

All graphics are synthetic, no copyrighted game tiles are used.
"""
import unittest

from tools.cps1_frame import render_frame
from tools.cps1_video import sprite_block_tiles

GFX_BYTES = 0x400000
TILES_16 = GFX_BYTES // 128
VIEW = (64, 16, 32, 48)
RED = bytes((235, 24, 31, 255))
GREEN = bytes((20, 225, 75, 255))
BLUE = bytes((30, 60, 240, 255))
BACK = bytes((5, 6, 7, 255))

palette = [[0, 0, 0] for _ in range(3072)]
palette[0xbff] = list(BACK[:3])
palette[1] = list(RED[:3])
palette[2] = list(GREEN[:3])
palette[3] = list(BLUE[:3])


def graphics_fixture():
    region = bytearray(GFX_BYTES)
    for code, pen in ((0x7ff0, 1), (0, 2), (0x7ff1, 3)):
        base = code * 128
        for y in range(16):
            for part in (0, 4):
                for plane in range(4):
                    if pen & (1 << (3-plane)):
                        region[base + y*8 + part + plane] = 0xff
    return bytes(region)


REGION = graphics_fixture()


def scene(code, attr):
    return {
        'layer_control': (2 << 6) | (3 << 8) | (1 << 10) | (0 << 12),
        'buffered_obj_words': [64, 16, code, attr, 0, 0, 0, 0xff00],
    }


def pixel(rendered, x, y, width=32):
    return rendered[(y*width+x)*4:(y*width+x+1)*4]


class CompositeSpriteRomWrapTests(unittest.TestCase):
    def test_16x16_element_count_matches_mame_rom_layout(self):
        self.assertEqual(TILES_16, 32768)
        self.assertEqual(len(REGION), 4194304)

    def test_vertical_second_part_wraps_to_code_zero(self):
        picture = render_frame(REGION, palette, scene(0x7ff0, 0x1000), VIEW)
        self.assertEqual(pixel(picture, 0, 0), RED)
        self.assertEqual(pixel(picture, 0, 15), RED)
        self.assertEqual(pixel(picture, 0, 16), GREEN)
        self.assertEqual(pixel(picture, 0, 31), GREEN)
        self.assertEqual(pixel(picture, 0, 32), BACK)

    def test_vertical_flip_reverses_wrapped_source_tile_and_pixel_rows(self):
        picture = render_frame(REGION, palette, scene(0x7ff0, 0x1040), VIEW)
        self.assertEqual(pixel(picture, 0, 0), GREEN)
        self.assertEqual(pixel(picture, 0, 16), RED)
        self.assertEqual(pixel(picture, 0, 32), BACK)

    def test_invalid_unmapped_obj_base_stays_invisible(self):
        picture = render_frame(REGION, palette, scene(0x8000, 0x1000), VIEW)
        self.assertEqual(pixel(picture, 0, 0), BACK)
        self.assertEqual(pixel(picture, 0, 16), BACK)

    def test_horizontal_flip_preserves_composite_tile_code_sequence(self):
        # A 2-wide block begins on 0x7ff0; horizontal flipping selects
        # 0x7ff1 for its left cell and 0x7ff0 for its right cell.
        picture = render_frame(REGION, palette, scene(0x7ff0, 0x0120), VIEW)
        self.assertEqual(pixel(picture, 0, 0), BLUE)
        self.assertEqual(pixel(picture, 16, 0), RED)

    def test_2x2_flip_wraps_second_row_for_both_columns(self):
        picture = render_frame(REGION, palette, scene(0x7ff0, 0x1160), VIEW)
        self.assertEqual(pixel(picture, 0, 0), bytes((0, 0, 0, 255)))
        self.assertEqual(pixel(picture, 16, 0), GREEN)
        self.assertEqual(pixel(picture, 0, 16), BLUE)
        self.assertEqual(pixel(picture, 16, 16), RED)

    def test_sprite_block_metadata_keeps_unwrapped_intermediate_codes(self):
        parts = sprite_block_tiles(0x7ff0, 0x1000)
        self.assertEqual([p.code for p in parts], [0x7ff0, 0x8000])


if __name__ == '__main__':
    unittest.main()
