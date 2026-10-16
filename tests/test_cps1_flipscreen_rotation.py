"""ROM-free regression tests for fast CPS-1 RGBA flipscreen rotation."""
import unittest
from unittest.mock import patch

from tools.cps1_frame import _rotate_rgba_pixels_180, render_frame
from tools.cps1_video import TOTAL_COLORS


def _pen_one_tile():
    # 16x16 CPS-1 4bpp graphic using only pen1, no game ROM.
    tile = bytearray(128)
    for row in range(16):
        tile[row*8 + 3] = 255
        tile[row*8 + 7] = 255
    return bytes(tile)


def _palette():
    palette = [(0, 0, 0)] * TOTAL_COLORS
    palette[0xbff] = (5, 6, 7)
    palette[1] = (230, 20, 30)
    palette[0x400 + 1] = (15, 25, 220)
    return palette


def _scene():
    return {
        # Scroll2 background, then OBJ sprites.
        'layer_control': (2 << 6) | (0 << 8) | (1 << 10) | (3 << 12),
        'scroll2': {'words': [0]*8192, 'enabled': True,
                    'scrollx': 3, 'scrolly': 7},
        'buffered_obj_words': [88, 41, 0, 0, 0, 0, 0, 0xff00],
    }


def _slow_oracle(pixels):
    # Independent byte-preserving oracle; never reverse *channels*.
    return b''.join(pixels[i:i+4] for i in range(len(pixels)-4, -1, -4))


class RotateRgbaPixels(unittest.TestCase):
    def test_asymmetric_rgba_channels_and_odd_dimensions(self):
        for width, height in ((1, 1), (3, 5), (7, 2), (384, 224)):
            with self.subTest(width=width, height=height):
                pixels = bytes(((i*37 + i//4*3) & 255)
                               for i in range(width*height*4))
                self.assertEqual(_rotate_rgba_pixels_180(pixels),
                                 _slow_oracle(pixels))
                self.assertEqual(_rotate_rgba_pixels_180(
                    _rotate_rgba_pixels_180(pixels)), pixels)

    def test_input_remains_untouched_for_mutable_rgba(self):
        original = bytearray((11, 22, 33, 44, 55, 66, 77, 88,
                              99, 111, 123, 145))
        expected = bytes(original)
        self.assertEqual(_rotate_rgba_pixels_180(original),
                         _slow_oracle(expected))
        self.assertEqual(original, bytearray(expected))

    def test_nonstandard_native_unsigned_int_uses_safe_fallback(self):
        pixels = bytes((3, 17, 31, 255, 12, 28, 44, 200, 61, 72, 83, 94))
        with patch('tools.cps1_frame.struct.calcsize', return_value=8):
            self.assertEqual(_rotate_rgba_pixels_180(pixels),
                             _slow_oracle(pixels))

    def test_incomplete_pixel_rejected(self):
        for bad in (b'\x01', b'\x01\x02\x03', b'\x01\x02\x03\x04\x05'):
            with self.subTest(length=len(bad)):
                with self.assertRaisesRegex(ValueError, 'multiple of four'):
                    _rotate_rgba_pixels_180(bad)

    def test_flip_uses_physical_raster_not_local_crop_center(self):
        graphics = _pen_one_tile()
        colors = _palette()
        scene = _scene()
        # Distinct opaque OBJ and Scroll2 colors exercise channel order.
        red = bytes((230, 20, 30, 255))
        blue = bytes((15, 25, 220, 255))
        self.assertEqual(render_frame(graphics, colors, scene,
                                      (88, 41, 1, 1)), red)
        self.assertEqual(render_frame(graphics, colors, scene,
                                      (80, 40, 1, 1)), blue)

        # Physical (404,193,44,34) mirrors (64,29,44,34).
        source = render_frame(graphics, colors, scene, (64, 29, 44, 34))
        flipped = dict(scene, video_control=0x8000)
        got = render_frame(graphics, colors, flipped, (404, 193, 44, 34))
        self.assertEqual(got, _slow_oracle(source))
        self.assertNotEqual(got, source)
        self.assertEqual(got[((214-193)*44 + (423-404))*4:
                             ((214-193)*44 + (423-404))*4 + 4], red)
        self.assertNotIn('video_control', scene)


if __name__ == '__main__':
    unittest.main()
