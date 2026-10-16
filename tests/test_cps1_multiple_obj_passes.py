"""Repeated CPS-1 OBJ passes must preserve one shared MAME priority bitmap.

MAME cps1_v.cpp render_layers() clears priority once, then sprite passes
stamp it to 31 and high-layer tilemap draws OR priority 1.
Only synthetic tile data is used.
"""
import unittest

from tools.cps1_frame import render_frame

PALETTE = [[0,0,0] for _ in range(3072)]
PALETTE[0xbff] = [5,6,7]
PALETTE[1] = [230,20,30]      # first opaque sprite: red
PALETTE[513] = [15,25,220]   # scroll1 pen1: blue
GFX = bytearray(0x400000)
for y in range(16):
    GFX[y*8+3] = 255
    GFX[y*8+7] = 255
    GFX[256+y*8:256+y*8+8] = b'\xff'*8  # code2 pen15, fully transparent
GFX = bytes(GFX)


def scene(order, *, scroll2_transparent=False, scroll1_mask=False):
    control = sum(layer << (6+2*i) for i,layer in enumerate(order))
    return {
        'layer_control': control,
        'palette_rgb': PALETTE,
        'priority_masks': [2 if scroll1_mask else 0,0,0,0],
        'scroll1': {'words':[0]*8192, 'scrollx':0,'scrolly':0,'enabled':True},
        'scroll2': ({'words':[2,0]*4096,'scrollx':0,'scrolly':0,'enabled':True}
                    if scroll2_transparent else
                    {'words':[0]*8192,'scrollx':0,'scrolly':0,'enabled':False}),
        'buffered_obj_words':[64,16,0,0,0,0,0,0xff00],
    }


def first_pixel(snapshot):
    return render_frame(GFX, snapshot['palette_rgb'],snapshot,(64,16,1,1))[:4]


class MultipleSpritePassesTests(unittest.TestCase):
    def test_second_obj_pass_does_not_overwrite_intervening_scroll1(self):
        snapshot=scene((2,0,1,0))
        self.assertEqual(first_pixel(snapshot),bytes((15,25,220,255)))

    def test_transparent_later_background_does_not_erase_old_priority(self):
        snapshot=scene((1,0,2,0),scroll2_transparent=True,scroll1_mask=True)
        self.assertEqual(first_pixel(snapshot),bytes((15,25,220,255)))

    def test_first_opaque_obj_is_still_visible_without_later_background(self):
        snapshot=scene((1,2,0,3))
        self.assertEqual(first_pixel(snapshot),bytes((230,20,30,255)))

    def test_priority_mask_from_earlier_background_prevents_first_sprite(self):
        snapshot=scene((1,0,2,0),scroll2_transparent=True,scroll1_mask=True)
        self.assertEqual(first_pixel(snapshot),bytes((15,25,220,255)))

    def test_repeated_obj_does_not_break_when_all_backgrounds_disabled(self):
        snapshot=scene((2,0,1,0))
        snapshot['scroll1']['enabled']=False
        self.assertEqual(first_pixel(snapshot),bytes((230,20,30,255)))


if __name__=='__main__':
    unittest.main()
