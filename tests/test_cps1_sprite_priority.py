"""MAME-referenced CPS-1 sprite occlusion regression tests without original ROM."""
import unittest
from tools.cps1_frame import render_frame

VIEW=(64,16,1,1)
PALETTE=[[0,0,0] for _ in range(3072)]
PALETTE[0xbff]=[5,6,7]
PALETTE[1]=[230,20,30]        # first OBJ, palette group 0, pen 1
PALETTE[17]=[30,220,70]       # second OBJ, palette group 1, pen 1
PALETTE[513]=[20,35,210]      # scroll1 priority foreground, pen 1

def synthetic_graphics():
    data=bytearray(384) # 3 ROM-free 16x16 sprite tile codes
    for y in range(16):
        data[y*8+3]=255
        data[y*8+7]=255
    data[256:384]=b'\xff'*128 # code2 uses transparent pen15
    return bytes(data)

def snapshot(obj):
    return {'layer_control':(2<<6)|(3<<8)|(1<<10)|(0<<12),
            'buffered_obj_words':obj+[0,0,0,0xff00]}

def color_at_first_pixel(obj,*,foreground=False):
    scene=snapshot(obj)
    if foreground:
        scene['scroll1']={'words':[0]*8192,'scrollx':0,'scrolly':0,'enabled':True}
        scene['priority_masks']=[2,0,0,0] # group0 pen1 masks sprites
    return render_frame(synthetic_graphics(),PALETTE,scene,VIEW)[:4]


class Cps1SpritePriorityTests(unittest.TestCase):
    def test_first_nontransparent_sprite_wins_over_later_opaque(self):
        self.assertEqual(color_at_first_pixel(
            [64,16,0,0, 64,16,0,1]),bytes([230,20,30,255]))

    def test_reversing_obj_entries_reverses_front_sprite(self):
        self.assertEqual(color_at_first_pixel(
            [64,16,0,1, 64,16,0,0]),bytes([30,220,70,255]))

    def test_first_transparent_sprite_does_not_stamp_priority(self):
        self.assertEqual(color_at_first_pixel(
            [64,16,2,0, 64,16,0,1]),bytes([30,220,70,255]))

    def test_sentinel_ends_obj_list_before_later_sprite(self):
        self.assertEqual(color_at_first_pixel(
            [64,16,0,0, 0,0,0,0xff00,64,16,0,1]),bytes([230,20,30,255]))

    def test_scroll_high_priority_masks_first_and_later_sprites(self):
        self.assertEqual(color_at_first_pixel(
            [64,16,0,0, 64,16,0,1],foreground=True),bytes([20,35,210,255]))

    def test_full_viewport_only_first_sprites_16x16_region_is_red(self):
        # Pixel-level regression for the exact MAME priority difference.
        # Two fully overlapping 16x16 opaque OBJ entries occupy 256 pixels.
        scene=snapshot([64,16,0,0, 64,16,0,1])
        rendered=render_frame(synthetic_graphics(),PALETTE,scene)
        first=bytes((230,20,30,255))
        backdrop=bytes((5,6,7,255))
        self.assertEqual(len(rendered),384*224*4)
        self.assertEqual(sum(rendered[i:i+4]==first
                             for i in range(0,len(rendered),4)),256)
        self.assertEqual(sum(rendered[i:i+4]==backdrop
                             for i in range(0,len(rendered),4)),86016-256)

    def test_pen0_is_opaque_and_also_stamps_priority(self):
        # code1 is all pen0, which is opaque for CPS-1 sprite rendering.
        self.assertEqual(color_at_first_pixel(
            [64,16,1,0, 64,16,0,1]),bytes([0,0,0,255]))

if __name__=='__main__':
    unittest.main()
