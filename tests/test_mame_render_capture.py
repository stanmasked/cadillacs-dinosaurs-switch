"""ROM-free compile/runtime tests for same-pass MAME CPS-1 capture."""
import json
import os
import shutil
import struct
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.mame_render_instrument import instrument,create_patch
from tools.mame_render_import import import_render,main,SIZES

STUB='''#include <cstdint>
#include <array>
#include <memory>
struct rgb_t {
    unsigned v;
    unsigned char r() const {return (v >> 16) & 255;}
    unsigned char g() const {return (v >> 8) & 255;}
    unsigned char b() const {return v & 255;}
};
struct FakePalette {rgb_t pen_color(unsigned p) const {return rgb_t{0x112233 + p};}};
struct screen_device {unsigned frame_number() const {return 900;}};
struct bitmap_ind16 {unsigned pix(int y,int x) const {return (unsigned)(y+x) & 0x7ff;}};
struct rectangle {int min_x,min_y,max_x,max_y;};
struct GfxRam {
    std::array<uint16_t,0x18000> data{};
    size_t bytes() const {return data.size()*sizeof(uint16_t);}
    uint16_t &operator[](size_t i) {return data[i];}
};
struct FakeMachine {
    struct Game {const char *name = "dino";};
    Game system() const {return {};}
};
struct cps_state {
    GfxRam m_gfxram;
    uint16_t m_cps_a_regs[32]{};
    uint16_t m_cps_b_regs[32]{};
    std::unique_ptr<uint16_t[]> m_buffered_obj = std::make_unique<uint16_t[]>(1024);
    int m_obj_size = 2048;
    FakePalette palette;
    FakePalette *m_palette = &palette;
    FakeMachine machine() const {return {};}
    void render_layers(screen_device &,bitmap_ind16 &,const rectangle &) {}
    uint32_t screen_update_cps1(screen_device &,bitmap_ind16 &,const rectangle &);
};
uint32_t cps_state::screen_update_cps1(screen_device &screen, bitmap_ind16 &bitmap, const rectangle &cliprect)
{
    render_layers(screen, bitmap, cliprect);
    return 0;
}
'''

def fixture(root):
    stem='frame-00000900'
    manifest={'game':'dino','frame':900,
        'capture_hook':'screen_update_cps1_complete',
        'full_cliprect':True,'buffered_obj_same_render_pass':True,
        'reference_pixel_encoding':'rgb24_palette_resolved',
        'raw_word_endianness':'big','palette_source':'MAME_effective_pen_color',
        'gfxram_bytes':196608,'cps_a_bytes':64,'cps_b_bytes':64,
        'buffered_obj_bytes':2048,'palette_bytes':9216,
        'reference_rgb_bytes':258048,'reference_width':384,'reference_height':224,
        'pixel_parity_verified':False}
    (root/(stem+'.manifest.json')).write_text(json.dumps(manifest))
    for suffix,size in SIZES.items():
        blob=bytearray(size)
        if suffix=='gfxram-be.bin':blob[:2]=b'\xab\xcd'
        if suffix=='cps-a-be.bin':
            a=[0]*32;a[2]=0x40;a[3]=0x80
            blob[:]=struct.pack('>32H',*a)
        if suffix=='buffered-obj-be.bin':blob[:8]=b'\x00\x40\x00\x10\x01\x00\x00\x00'
        if suffix=='palette-rgb24.bin':blob[:3]=b'\x10\x20\x30'
        if suffix=='reference-rgb24.bin':blob[:3]=b'\x12\x34\x56'
        (root/(stem+'.'+suffix)).write_bytes(blob)
    return stem

class InstrumentTests(unittest.TestCase):
    def test_correct_render_hook(self):
        changed=instrument(STUB)
        self.assertLess(changed.index('render_layers(screen, bitmap, cliprect)'),
                        changed.index('CPS1_RENDER_DUMP_DIR'))
        self.assertIn('m_buffered_obj.get()',changed)
        self.assertIn('reference-rgb24.bin',changed)
    def test_small_patch_and_reject_duplicate(self):
        self.assertIn('--- a/src/mame/capcom/cps1_v.cpp',create_patch(STUB))
        with self.assertRaises(ValueError):instrument(instrument(STUB))
    def test_reject_wrong_source(self):
        with self.assertRaises(ValueError):instrument(STUB.replace('render_layers(screen, bitmap, cliprect);',';'))

@unittest.skipUnless(shutil.which('g++'),'C++17 compiler unavailable')
class CppSmoke(unittest.TestCase):
    def test_compiled_render_dump(self):
        program=instrument(STUB)+'''
int main(int argc,char **) {
    cps_state state;
    state.m_gfxram[0]=0xabcd;
    state.m_cps_a_regs[0]=0x0123;
    state.m_cps_b_regs[0]=0x4567;
    state.m_buffered_obj[0]=0x89ab;
    screen_device screen;bitmap_ind16 bitmap;
    rectangle clip{64,16,447,239};
    if (argc>1) clip.max_x=440;
    state.screen_update_cps1(screen,bitmap,clip);
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            cpp=folder/'test.cpp';exe=folder/'test';cpp.write_text(program)
            compiled=subprocess.run(['g++','-std=c++17','-O2','-Wall','-Wextra','-Werror',
                                     str(cpp),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            env=os.environ.copy()
            env.update(CPS1_RENDER_DUMP_DIR=td,CPS1_RENDER_DUMP_START='900',
                       CPS1_RENDER_DUMP_COUNT='1')
            subprocess.run([str(exe),'partial'],env=env,check=True)
            self.assertFalse(list(folder.glob('frame-*.bin')))
            subprocess.run([str(exe)],env=env,check=True)
            for suffix,size in SIZES.items():
                with self.subTest(suffix=suffix):
                    self.assertEqual((folder/('frame-00000900.'+suffix)).stat().st_size,size)
            self.assertEqual((folder/'frame-00000900.gfxram-be.bin').read_bytes()[:2],b'\xab\xcd')
            self.assertEqual((folder/'frame-00000900.buffered-obj-be.bin').read_bytes()[:2],b'\x89\xab')
            self.assertEqual((folder/'frame-00000900.reference-rgb24.bin').read_bytes()[:3],b'\x11\x22\x83')

class ImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.stem=fixture(self.root)
    def test_reference_and_buffered_sprite(self):
        snapshot,png=import_render(self.root,self.stem)
        self.assertEqual(snapshot['buffered_obj_words'][:4],[64,16,256,0])
        self.assertEqual(snapshot['palette_rgb'][0],[16,32,48])
        self.assertTrue(snapshot['pixel_parity_eligible'])
        self.assertFalse(snapshot['pixel_parity_verified'])
        self.assertEqual(struct.unpack_from('>II',png,16),(384,224))
    def test_reject_false_verified_claim(self):
        path=self.root/(self.stem+'.manifest.json')
        doc=json.loads(path.read_text());doc['pixel_parity_verified']=True
        path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):import_render(self.root,self.stem)
    def test_reject_incomplete_obj(self):
        (self.root/(self.stem+'.buffered-obj-be.bin')).write_bytes(bytes(2000))
        with self.assertRaises(ValueError):import_render(self.root,self.stem)
    def test_reject_partial_cliprect(self):
        path=self.root/(self.stem+'.manifest.json')
        doc=json.loads(path.read_text());doc['full_cliprect']=False
        path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError):import_render(self.root,self.stem)
    def test_reject_bad_capture_stem(self):
        with self.assertRaises(ValueError):import_render(self.root,'../../private')
    def test_cli_refuses_overwrite(self):
        out=self.root/'out'
        self.assertEqual(main([str(self.root),self.stem,'--out-dir',str(out)]),0)
        self.assertEqual(main([str(self.root),self.stem,'--out-dir',str(out)]),2)

if __name__=='__main__':
    unittest.main()
