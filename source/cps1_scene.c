#include "cps1_scene.h"
#include "cps1_tile.h"
#include <stdlib.h>
#include <string.h>

/* CPS-1 dino: MAME cps1_v.cpp CD63B mapper, scroll map scan and QS2
 * priorities. Input captures must come from one coherent emulated frame.
 */
static uint16_t get_u16(const uint8_t *p) {
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}
static uint32_t get_u32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1]<<8) |
           ((uint32_t)p[2]<<16) | ((uint32_t)p[3]<<24);
}
static uint32_t crc32_raw(const uint8_t *p, size_t n) {
    uint32_t crc = 0xffffffffu;
    for (size_t i=0; i<n; ++i) {
        crc ^= p[i];
        for (unsigned b=0; b<8; ++b)
            crc = (crc >> 1) ^ (0xedb88320u & (0u-(crc & 1u)));
    }
    return ~crc;
}

bool cps1_scene_decode(const uint8_t *blob, size_t length, Cps1Scene *out) {
    if (!blob || !out || length != CPS1_SCENE_FILE_BYTES ||
        memcmp(blob,"CPS1SCN1",8) ||
        get_u32(blob+8) != CPS1_SCENE_PAYLOAD_BYTES ||
        get_u32(blob+12) != crc32_raw(blob+16,CPS1_SCENE_PAYLOAD_BYTES))
        return false;

    Cps1Scene *s = malloc(sizeof(*s));
    if (!s) return false;
    const uint8_t *p = blob+16;
    s->layer_control=get_u16(p); p+=2;
    s->video_control=get_u16(p); p+=2;
    for (int i=0;i<3;++i) { s->scrollx[i]=get_u16(p);p+=2; }
    for (int i=0;i<3;++i) { s->scrolly[i]=get_u16(p);p+=2; }
    for (int i=0;i<3;++i) { s->enabled[i]=*p++; }
    if (*p++ != 0) { free(s);return false; }
    for (int i=0;i<4;++i) { s->priority[i]=get_u16(p);p+=2; }
    s->rowscroll_offset=get_u16(p);p+=2;
    memcpy(s->palette,p,sizeof(s->palette));p+=sizeof(s->palette);
    for (int layer=0;layer<3;++layer)
        for (size_t i=0;i<CPS1_SCENE_SCROLL_WORDS;++i) {
            s->scroll[layer][i]=get_u16(p);p+=2;
        }
    for (size_t i=0;i<CPS1_SCENE_OBJ_WORDS;++i) {
        s->obj[i]=get_u16(p);p+=2;
    }
    for (size_t i=0;i<CPS1_SCENE_ROW_WORDS;++i) {
        s->rowscroll[i]=get_u16(p);p+=2;
    }
    if (p != blob+length) { free(s);return false; }
    *out=*s;
    free(s);
    return true;
}

static unsigned scan_tile(int layer, unsigned col, unsigned row) {
    if (layer==0) return (row & 31u) + (col << 5) + ((row & 32u) << 6);
    if (layer==1) return (row & 15u) + (col << 4) + ((row & 48u) << 6);
    return (row & 7u) + (col << 3) + ((row & 56u) << 6);
}

static unsigned tile_size(int layer) { return 8u << layer; }

static uint8_t gfx_pen(const uint8_t *gfx, size_t gfx_bytes,
                       int layer, unsigned code, unsigned tile_index,
                       unsigned x, unsigned y) {
    unsigned side=tile_size(layer);
    size_t stride=side==8?64u:(size_t)side*side/2u;
    size_t slot_count=gfx_bytes/stride;
    unsigned raw_limit=side==8?0xffffu:(side==16?0x7fffu:0x1fffu);
    if (code>raw_limit || code>=slot_count) return 15;
    size_t tile_base=(size_t)code*stride;
    unsigned row_stride=side==8?8u:side/2u;
    unsigned half=side==8 && (tile_index&32u)?4u:0u;
    size_t offset=tile_base+(size_t)y*row_stride+half+(x/8u)*4u;
    unsigned bit=7u-(x&7u);
    uint8_t pen=0;
    for (unsigned p=0;p<4;++p)
        pen |= (uint8_t)(((gfx[offset+p]>>bit)&1u) << (3u-p));
    return pen;
}

static void place(uint8_t *rgba, const Cps1Scene *s, size_t index,
                  unsigned palette_index) {
    const uint8_t *c=s->palette[palette_index];
    rgba[index*4+0]=c[0];
    rgba[index*4+1]=c[1];
    rgba[index*4+2]=c[2];
    rgba[index*4+3]=255;
}

static void draw_scroll(const uint8_t *gfx, size_t gfx_bytes,
                        const Cps1Scene *s, int layer, uint8_t *rgba,
                        uint8_t *occluded, bool high_priority) {
    if (!s->enabled[layer]) return;
    const unsigned side=tile_size(layer);
    const unsigned wrap=64u*side;
    const unsigned palette_base=(unsigned)(layer+1)*512u;
    for (unsigned py=0;py<CPS1_SCENE_H;++py) {
        unsigned screen_y=py+16u;
        unsigned wy=(screen_y+s->scrolly[layer])&(wrap-1u);
        unsigned row=wy/side, local_y=wy%side;
        unsigned sx=s->scrollx[layer];
        if (layer==1 && (s->video_control&1u))
            sx += s->rowscroll[(screen_y+s->rowscroll_offset)&1023u];
        for (unsigned px=0;px<CPS1_SCENE_W;++px) {
            unsigned wx=(px+64u+sx)&(wrap-1u);
            unsigned col=wx/side;
            unsigned local_x=wx%side;
            unsigned tile_index=scan_tile(layer,col,row);
            unsigned code=s->scroll[layer][tile_index*2u];
            unsigned attr=s->scroll[layer][tile_index*2u+1u];
            if (layer==2) code&=0x3fffu;
            if (attr&0x20u) local_x=side-1u-local_x;
            unsigned sample_y=(attr&0x40u)?side-1u-local_y:local_y;
            unsigned pen=gfx_pen(gfx,gfx_bytes,layer,code,tile_index,local_x,sample_y);
            size_t index=(size_t)py*CPS1_SCENE_W+px;
            if (pen != 15u)
                place(rgba,s,index,palette_base+(attr&31u)*16u+pen);
            if (high_priority) {
                unsigned group=(attr>>7)&3u;
                occluded[index]=(uint8_t)(pen!=15u && (s->priority[group]&(1u<<pen))!=0u);
            }
        }
    }
}

static void draw_sprite_tile(const uint8_t *gfx, size_t gfx_bytes,
                             const Cps1Scene *s, uint8_t *rgba,
                             uint8_t *occluded,
                             unsigned x,unsigned y,unsigned code,unsigned attr) {
    /* MAME gfx_element::prio_transpen wraps a composite *part* after
     * gfxrom_bank_mapper validated the original OBJ base code. */
    code %= CPS1_TILE16_COUNT;
    unsigned color_group=attr&31u;
    bool flip_x=(attr&0x20u)!=0, flip_y=(attr&0x40u)!=0;
    uint8_t pixels[CPS1_TILE16_PIXELS];
    if (!cps1_decode_tile16(gfx,gfx_bytes,code,pixels)) return;
    for (unsigned ty=0;ty<16u;++ty) {
        unsigned sy=y+ty;
        if (sy<16u || sy>=240u) continue;
        for (unsigned tx=0;tx<16u;++tx) {
            unsigned sx=x+tx;
            if (sx<64u || sx>=448u) continue;
            unsigned py=flip_y?15u-ty:ty;
            unsigned px=flip_x?15u-tx:tx;
            unsigned pen=pixels[py*16u+px];
            size_t index=(size_t)(sy-16u)*CPS1_SCENE_W+sx-64u;
            if (pen!=15u) {
                if (!occluded[index])
                    place(rgba,s,index,color_group*16u+pen);
                /* MAME PIXEL_OP_REBASE_TRANSPEN_PRIORITY sets priority 31
                 * even when a higher-priority scroll pen masks this OBJ.
                 * All later sprite pixels at this position are blocked. */
                occluded[index]=1u;
            }
        }
    }
}

static void draw_sprites(const uint8_t *gfx, size_t gfx_bytes,
                         const Cps1Scene *s,uint8_t *rgba,
                         uint8_t *occluded) {
    for (unsigned i=0;i<CPS1_SCENE_OBJ_WORDS;i+=4u) {
        unsigned x=s->obj[i]&0x1ffu, y=s->obj[i+1u]&0x1ffu;
        unsigned code=s->obj[i+2u], attr=s->obj[i+3u];
        if ((attr&0xff00u)==0xff00u) break;
        /* Base code is checked by MAME gfxrom_bank_mapper, before
         * expanding the composite. Never resurrect an invalid raw OBJ. */
        if (code >= CPS1_TILE16_COUNT) continue;
        unsigned nx=(attr&0xff00u)?((attr>>8u)&15u)+1u:1u;
        unsigned ny=(attr&0xff00u)?((attr>>12u)&15u)+1u:1u;
        for (unsigned row=0;row<ny;++row) {
            for (unsigned col=0;col<nx;++col) {
                unsigned src_col=(attr&0x20u)?nx-1u-col:col;
                unsigned src_row=(attr&0x40u)?ny-1u-row:row;
                unsigned tile=(code&~15u)+((code+src_col)&15u)+16u*src_row;
                draw_sprite_tile(gfx,gfx_bytes,s,rgba,occluded,
                                 (x+col*16u)&0x1ffu,(y+row*16u)&0x1ffu,tile,attr);
            }
        }
    }
}

bool cps1_scene_render(const uint8_t *gfx,size_t gfx_bytes,
                       const Cps1Scene *s,uint8_t *rgba,size_t rgba_bytes) {
    if (!gfx || gfx_bytes!=CPS1_GFX_BYTES || !s ||
        !rgba || rgba_bytes<CPS1_SCENE_RGBA_BYTES) return false;
    uint8_t *occluded=calloc(CPS1_SCENE_W*CPS1_SCENE_H,1u);
    if (!occluded) return false;
    for (size_t i=0;i<CPS1_SCENE_W*CPS1_SCENE_H;++i)
        place(rgba,s,i,0xbffu);
    for (unsigned i=0;i<4;++i) {
        unsigned layer=(s->layer_control>>(6u+2u*i))&3u;
        unsigned next=(i<3u)?((s->layer_control>>(8u+2u*i))&3u):4u;
        if (next==0u) memset(occluded,0,CPS1_SCENE_W*CPS1_SCENE_H);
        if (layer==0u) draw_sprites(gfx,gfx_bytes,s,rgba,occluded);
        else draw_scroll(gfx,gfx_bytes,s,(int)layer-1,rgba,occluded,next==0u);
    }
    free(occluded);
    return true;
}

bool cps1_scene_pan(Cps1Scene *scene, int dx, int dy) {
    if (!scene || (!dx && !dy)) return false;
    for (unsigned i=0; i<3; ++i) {
        /* Conversion to uint16_t is intentional: CPS-A scroll registers
           wrap modulo 2^16 even for negative deltas. */
        scene->scrollx[i] = (uint16_t)(scene->scrollx[i] + (uint16_t)dx);
        scene->scrolly[i] = (uint16_t)(scene->scrolly[i] + (uint16_t)dy);
    }
    return true;
}
