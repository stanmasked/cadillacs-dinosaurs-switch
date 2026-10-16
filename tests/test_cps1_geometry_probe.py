"""ROM-free MAME CPS-1 physical screen and tile-map geometry regression tests."""
import json
from pathlib import Path
import tempfile
import unittest

from tools.cps1_geometry_probe import probe_layer,main
from tools.cps1_frame import render_frame


def plane_tile(side, pen):
    result=bytearray(side*side//2)
    for y in range(side):
        for xband in range(side//8):
            for p in range(4):
                if pen & (1<<(3-p)):
                    result[y*(side//2)+xband*4+p]=255
    return result


def make_scene(layer):
    return {
        'layer_control': {'scroll1':1,'scroll2':2,'scroll3':3}[layer]<<12,
        'video_control':0,
        'buffered_obj_words':[0,0,0,0xff00],
        layer:{'words':[0]*8192,'scrollx':0,'scrolly':0,'enabled':True},
    }


def pixel(data,w,x,y=0):
    return tuple(data[4*(y*w+x):4*(y*w+x)+4])


class PhysicalGeometryTests(unittest.TestCase):
    def test_reference_screen_origin_and_scroll1_half(self):
        scene=make_scene('scroll1')
        a=probe_layer(scene,'scroll1',64,16)
        b=probe_layer(scene,'scroll1',72,16)
        self.assertEqual(a['tile_col_row'],[8,2])
        self.assertEqual(a['tile_index'],258)
        self.assertEqual(a['ram_word_index'],516)
        self.assertEqual(a['scroll1_half'],'left')
        self.assertTrue(a['candidate_drawn'])
        self.assertEqual(a['draw_slots_bottom_to_top'],[3])
        self.assertTrue(a['cd63b_code_valid'])
        self.assertEqual(a['sampled_pixel_xy'],[0,0])
        self.assertEqual(b['tile_index'],290)
        self.assertEqual(b['scroll1_half'],'right')
        self.assertEqual(b['sampled_pixel_xy'],[0,0])
        self.assertTrue(a['inside_visible_area'])
        self.assertFalse(probe_layer(scene,'scroll1',63,16)['inside_visible_area'])

    def test_alternating_8x8_halves_render_exact_pixels(self):
        scene=make_scene('scroll1')
        gfx=bytearray(64)
        for y in range(8):
            gfx[y*8+3]=255 # left-half pen1
            gfx[y*8+6]=255 # right-half pen2
        pal=[[0,0,0] for _ in range(3072)]
        pal[0xbff]=[5,6,7]
        pal[513]=[255,0,0]
        pal[514]=[0,255,0]
        frame=render_frame(bytes(gfx),pal,scene,(64,16,24,1))
        self.assertEqual(pixel(frame,24,0),(255,0,0,255))
        self.assertEqual(pixel(frame,24,7),(255,0,0,255))
        self.assertEqual(pixel(frame,24,8),(0,255,0,255))
        self.assertEqual(pixel(frame,24,15),(0,255,0,255))
        self.assertEqual(pixel(frame,24,16),(255,0,0,255))

    def test_scroll2_exact_boundary_and_one_line_rowscroll(self):
        scene=make_scene('scroll2')
        words=scene['scroll2']['words']
        # Physical X=64 selects tile column four, Y=16 selects tile row one.
        words[65*2]=0
        words[81*2]=1
        gfx=bytes(plane_tile(16,1)+plane_tile(16,2))
        pal=[[0,0,0] for _ in range(3072)]
        pal[0xbff]=[5,6,7]
        pal[1025]=[240,10,10]
        pal[1026]=[10,240,10]
        before=probe_layer(scene,'scroll2',64,16)
        self.assertEqual(before['tile_index'],65)
        self.assertEqual(pixel(render_frame(gfx,pal,scene,(64,16,1,1)),1,0),
                         (240,10,10,255))
        scene['scroll2']['scrollx']=16
        after=probe_layer(scene,'scroll2',64,16)
        self.assertEqual(after['tile_index'],81)
        self.assertEqual(pixel(render_frame(gfx,pal,scene,(64,16,1,1)),1,0),
                         (10,240,10,255))
        scene['scroll2']['scrollx']=0
        scene['video_control']=1
        scene['rowscroll_offset']=7
        scene['rowscroll']=[0]*1024
        scene['rowscroll'][23]=16  # Raster Y16 + offset7
        self.assertEqual(probe_layer(scene,'scroll2',64,16)['tile_index'],81)
        self.assertEqual(probe_layer(scene,'scroll2',64,17)['tile_index'],65)
        result=render_frame(gfx,pal,scene,(64,16,1,2))
        self.assertEqual(pixel(result,1,0,0),(10,240,10,255))
        self.assertEqual(pixel(result,1,0,1),(240,10,10,255))

    def test_scroll3_world_wrap_and_tile_code_mask(self):
        scene=make_scene('scroll3')
        scene['scroll3']['scrollx']=1984
        scene['scroll3']['words'][0]=0xffff
        tile=probe_layer(scene,'scroll3',64,16)
        self.assertEqual(tile['world_xy'],[0,16])
        self.assertEqual(tile['tile_col_row'],[0,0])
        self.assertEqual(tile['tile_code'],0x3fff)
        self.assertFalse(tile['cd63b_code_valid'])
        self.assertIsNone(tile['mapped_tile_code'])
        self.assertFalse(tile['candidate_drawn'])
        self.assertEqual(tile['ram_word_index'],0)
        next_tile=probe_layer(scene,'scroll3',96,16)
        self.assertEqual(next_tile['tile_col_row'],[1,0])
        self.assertEqual(next_tile['tile_index'],8)

    def test_cd63b_out_of_range_and_missing_layer_slot(self):
        scene=make_scene('scroll2')
        pos=probe_layer(scene,'scroll2',64,16)
        scene['scroll2']['words'][pos['ram_word_index']]=0x8000
        invalid=probe_layer(scene,'scroll2',64,16)
        self.assertFalse(invalid['cd63b_code_valid'])
        self.assertFalse(invalid['candidate_drawn'])
        self.assertIsNone(invalid['mapped_tile_code'])
        scene['scroll2']['words'][pos['ram_word_index']]=0x7fff
        valid=probe_layer(scene,'scroll2',64,16)
        self.assertTrue(valid['cd63b_code_valid'])
        self.assertEqual(valid['mapped_tile_code'],0x7fff)
        scene['layer_control']=0
        hidden=probe_layer(scene,'scroll2',64,16)
        self.assertFalse(hidden['candidate_drawn'])
        self.assertEqual(hidden['draw_slots_bottom_to_top'],[])

    def test_scroll1_vertical_wrap_and_attribute_flip(self):
        scene=make_scene('scroll1')
        scene['scroll1']['scrolly']=512-16
        pos=probe_layer(scene,'scroll1',64,16)
        self.assertEqual(pos['world_xy'],[64,0])
        self.assertEqual(pos['tile_col_row'],[8,0])
        scene['scroll1']['words'][pos['tile_index']*2+1]=0x60
        turned=probe_layer(scene,'scroll1',64,16)
        self.assertEqual(turned['sampled_pixel_xy'],[7,7])
        self.assertEqual(turned['priority_group'],0)
        self.assertEqual(probe_layer(scene,'scroll1',64,24)['tile_col_row'],[8,1])

    def test_cli_private_probe_and_no_overwrite(self):
        scene=make_scene('scroll1')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            capture=root/'snapshot.json'
            output=root/'projection.json'
            capture.write_text(json.dumps(scene))
            args=[str(capture),'--layer','scroll1','--x','64','--y','16',
                  '--out',str(output)]
            self.assertEqual(main(args),0)
            self.assertEqual(json.loads(output.read_text())['tile_index'],258)
            self.assertEqual(main(args),2)

    def test_reject_missing_ram_and_invalid_coordinate(self):
        scene=make_scene('scroll2')
        scene['scroll2']['words']=[1,2,3]
        with self.assertRaises(ValueError):probe_layer(scene,'scroll2',64,16)
        scene=make_scene('scroll2')
        for x,y in ((512,16),(64,256),(-1,16)):
            with self.assertRaises(ValueError):probe_layer(scene,'scroll2',x,y)


if __name__=='__main__':
    unittest.main()
