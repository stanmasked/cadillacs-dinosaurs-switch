"""ROM-free geometry regression tests for CPS-1 physical viewport bounds.

The 512x256 bounds must apply in both orientations. Cropped diagnostic
output is addressed in hardware coordinates, not an isolated crop-local
180-degree rotation.
"""
import unittest

from tools.cps1_frame import render_frame
from tools.cps1_video import TOTAL_COLORS


def _palette():
    colors = [(0, 0, 0)] * TOTAL_COLORS
    colors[0] = (230, 30, 40)
    colors[0xbff] = (5, 6, 7)
    return colors


class PhysicalViewportBounds(unittest.TestCase):
    def setUp(self):
        # One synthetic tile, with every pen 0, no commercial data.
        self.gfx = bytes(128)
        self.colors = _palette()
        self.empty = {'layer_control': 0, 'buffered_obj_words': []}

    def test_nonflipped_crop_cannot_extend_past_right_or_bottom_edge(self):
        for viewport in ((511, 0, 2, 1), (0, 255, 1, 2),
                         (510, 254, 3, 2), (510, 254, 2, 3)):
            with self.subTest(viewport=viewport):
                with self.assertRaisesRegex(ValueError, '512x256'):
                    render_frame(self.gfx, self.colors, self.empty, viewport)

    def test_flipped_crop_has_the_same_physical_bounds(self):
        flipped = dict(self.empty, video_control=0x8000)
        for viewport in ((511, 0, 2, 1), (0, 255, 1, 2)):
            with self.subTest(viewport=viewport):
                with self.assertRaisesRegex(ValueError, '512x256'):
                    render_frame(self.gfx, self.colors, flipped, viewport)

    def test_last_physical_pixel_and_exact_edge_rectangle_are_valid(self):
        transparent_background = bytes((5, 6, 7, 255))
        for bit in (0, 0x8000):
            with self.subTest(flipped=bool(bit)):
                scene = dict(self.empty, video_control=bit)
                one_pixel = render_frame(
                    self.gfx, self.colors, scene, (511, 255, 1, 1))
                self.assertEqual(one_pixel, transparent_background)
                corner = render_frame(
                    self.gfx, self.colors, scene, (510, 254, 2, 2))
                self.assertEqual(corner, transparent_background * 4)

    def test_flipped_crop_samples_mirrored_hardware_location(self):
        scene = {
            'layer_control': 0,
            'buffered_obj_words': [8, 17, 0, 0, 0, 0, 0, 0xff00]
        }
        sprite_pixel = bytes((230, 30, 40, 255))
        background_pixel = bytes((5, 6, 7, 255))

        # The physical point (8,17) mirrors to (503,238) on 512x256.
        self.assertEqual(
            render_frame(self.gfx, self.colors, scene, (8, 17, 1, 1)),
            sprite_pixel)
        self.assertEqual(
            render_frame(self.gfx, self.colors, scene, (503, 238, 1, 1)),
            background_pixel)

        scene['video_control'] = 0x8000
        self.assertEqual(
            render_frame(self.gfx, self.colors, scene, (503, 238, 1, 1)),
            sprite_pixel)
        # The recursive unflipped render must not mutate the caller's state.
        self.assertEqual(scene['video_control'], 0x8000)


if __name__ == '__main__':
    unittest.main()
