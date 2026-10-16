import json
from pathlib import Path
import tempfile
import unittest

from tools.cps1_frame import (tile_ram_index,decode_layer_control,scan_sprite_words,
                              render_frame,load_snapshot)
from tools.cps1_video import TOTAL_COLORS


def fill_tile(pen=1):
    data=bytearray(128)
    for y in range(16):
        for half in (0,4):
            for plane in range(4):
                if pen & (1 << plane):
                    data[y*8+half+3-plane] = 0xff
    return bytes(data)


def palette():
    pal=[(0,0,0)]*TOTAL_COLORS
    pal[0xbff] = (5,6,7)
    pal[1] = (255,0,0) # sprite page color 0 pen 1
    pal[0x400+1] = (0,255,0) # scroll2 page color 0 pen 1
    pal[0x200+1] = (0,0,255) # scroll1 page color 0 pen 1
    return pal


def control(*layers):
    ids={'sprites':0,'scroll1':1,'scroll2':2,'scroll3':3}
    return sum(ids[n] << (6+2*i) for i,n in enumerate(layers))


def pixel(image,width,x,y):
    o=(y*width+x)*4
    return image[o:o+4]


class Addressing(unittest.TestCase):
    def test_tile_addresses_are_unique_and_complete(self):
        for layer in ('scroll1','scroll2','scroll3'):
            indices={tile_ram_index(layer,col,row)
                     for col in range(64) for row in range(64)}
            self.assertEqual(indices,set(range(4096)))

    def test_address_examples(self):
        self.assertEqual(tile_ram_index('scroll1',1,0),32)
        self.assertEqual(tile_ram_index('scroll1',0,32),2048)
        self.assertEqual(tile_ram_index('scroll2',1,0),16)
        self.assertEqual(tile_ram_index('scroll2',0,16),1024)
        self.assertEqual(tile_ram_index('scroll3',1,0),8)
        self.assertEqual(tile_ram_index('scroll3',0,8),512)

    def test_invalid_tile_positions(self):
        with self.assertRaises(ValueError): tile_ram_index('scroll2',64,0)
        with self.assertRaises(ValueError): tile_ram_index('scroll1',0,-1)
        with self.assertRaises(ValueError): tile_ram_index('sprites',0,0)

    def test_layer_control_order(self):
        v=control('scroll3','scroll2','sprites','scroll1')
        self.assertEqual(decode_layer_control(v),('scroll3','scroll2','sprites','scroll1'))
        self.assertEqual(decode_layer_control(0),('sprites',)*4)
        with self.assertRaises(ValueError): decode_layer_control(-1)

    def test_sprite_marker_stops_before_marker(self):
        self.assertEqual(scan_sprite_words([0x240,0x210,7,1,0,0,0,0xff00,100,40,10,2]),
                         [(64,16,7,1)])

    def test_sprite_word_errors(self):
        with self.assertRaises(ValueError):scan_sprite_words([1,2,3])
        with self.assertRaises(ValueError):scan_sprite_words([1,2,3,65536])


class Render(unittest.TestCase):
    def test_background_rgb(self):
        frame=render_frame(bytes(128),palette(),{'layer_control':0,'buffered_obj_words':[]}, (0,0,32,32))
        self.assertEqual(len(frame),32*32*4)
        self.assertEqual(pixel(frame,32,0,0),bytes((5,6,7,255)))

    def test_sprite_draws_and_marker_excludes_next(self):
        region=fill_tile()
        scene={'layer_control':0,'buffered_obj_words': [1,2,0,0,0,0,0,0xff00]}
        frame=render_frame(region,palette(),scene,(0,0,20,20))
        self.assertEqual(pixel(frame,20,1,2),bytes((255,0,0,255)))
        self.assertEqual(pixel(frame,20,0,2),bytes((5,6,7,255)))

    def test_sprite_priority_over_scroll2_explicit_order(self):
        region=fill_tile()
        words=[0]*8192
        # cover screen with 16x16 tiles, selecting code 0 and color 0
        scene={'layer_control':control('scroll2','scroll3','scroll1','sprites'),
               'scroll2':{'words':words,'enabled':True},
               'buffered_obj_words':[0,0,0,0,0,0,0,0xff00]}
        frame=render_frame(region,palette(),scene,(0,0,16,16))
        self.assertEqual(pixel(frame,16,0,0),bytes((255,0,0,255)))
        scene['layer_control']=control('sprites','scroll3','scroll1','scroll2')
        frame=render_frame(region,palette(),scene,(0,0,16,16))
        self.assertEqual(pixel(frame,16,0,0),bytes((0,255,0,255)))

    def test_scroll2_scrollx_scrolls_to_next_column(self):
        region=fill_tile(1) + fill_tile(15)
        words=[0]*8192
        words[2*tile_ram_index('scroll2',1,0)] = 1
        scene={'layer_control':control('scroll2','scroll1','scroll3','sprites'),
               'scroll2':{'words':words,'scrollx':16,'scrolly':0}}
        frame=render_frame(region,palette(),scene,(0,0,16,16))
        self.assertEqual(pixel(frame,16,0,0),bytes((5,6,7,255)))
        scene['scroll2']['scrollx']=0
        frame=render_frame(region,palette(),scene,(0,0,16,16))
        self.assertEqual(pixel(frame,16,0,0),bytes((0,255,0,255)))

    def test_transparent_sprite_pen_15(self):
        frame=render_frame(fill_tile(15),palette(),{'layer_control':0,
                            'buffered_obj_words':[0,0,0,0]},(0,0,16,16))
        self.assertEqual(pixel(frame,16,4,4),bytes((5,6,7,255)))

    def test_viewport_origin_clipping(self):
        region=fill_tile(1)
        frame=render_frame(region,palette(),{'layer_control':0,
                           'buffered_obj_words':[64,16,0,0]},(64,16,16,16))
        self.assertEqual(pixel(frame,16,0,0),bytes((255,0,0,255)))

    def test_sprite_horizontal_flip(self):
        data=bytearray(fill_tile(15))
        for plane in (0,1,2):
            data[plane] &= 0x7f  # top-left pen1; all other pixels pen15
        frame=render_frame(bytes(data),palette(),{'layer_control':0,
                             'buffered_obj_words':[0,0,0,0x20]},(0,0,16,16))
        self.assertEqual(pixel(frame,16,15,0),bytes((255,0,0,255)))
        self.assertEqual(pixel(frame,16,0,0),bytes((5,6,7,255)))

    def test_bogus_scroll_ram_rejected(self):
        with self.assertRaises(ValueError):
            render_frame(bytes(128),palette(),{'layer_control':0,'scroll1':{'words':[0]*3}},(0,0,8,8))

    def test_invalid_viewport_rejected(self):
        with self.assertRaises(ValueError):
            render_frame(bytes(128),palette(),{'layer_control':0},(0,0,513,9))

    def test_load_json_palette_snapshot(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'snapshot.json'
            p.write_text(json.dumps({'layer_control':0,'palette_source':{'control':1,'words':[0xffff]*512}}))
            _, pal=load_snapshot(p)
            self.assertEqual(pal[0],(255,255,255))
            self.assertEqual(len(pal),TOTAL_COLORS)


if __name__=='__main__':
    unittest.main()
