#include "cps1_tile.h"

/* Hardware layouts: 4 pixel-plane bytes per 8 horizontal pixels,
 * bits 7..0 read left-to-right, CPS-1 planes [24,16,8,0].
 * The 8x8 mapper selects two overlapping alternatives from each
 * 64-byte code using MAME tile_index bit 5 (left or right half).
 */
bool cps1_read_tile_pen(const uint8_t *gfx, size_t gfx_size,
                        unsigned side, size_t code, bool right_half,
                        unsigned x, unsigned y, uint8_t *pen_out) {
    if (!gfx || !pen_out || (side!=8u && side!=16u && side!=32u) ||
        x>=side || y>=side) return false;
    const size_t unit=side==8u?64u:(size_t)side*side/2u;
    if (gfx_size % unit || code>=gfx_size/unit) return false;
    const size_t row_bytes=side==8u?8u:(size_t)side/2u;
    const size_t offset=code*unit+(size_t)y*row_bytes+
                        (side==8u && right_half?4u:0u)+(x/8u)*4u;
    unsigned bit=7u-(x&7u);
    uint8_t pen=0;
    for (unsigned plane=0;plane<4u;++plane)
        pen |= (uint8_t)(((gfx[offset+plane]>>bit)&1u)<<(3u-plane));
    *pen_out=pen;
    return true;
}

static bool decode(const uint8_t *gfx,size_t gfx_size,size_t code,
                   unsigned side,bool right_half,uint8_t *out) {
    if (!gfx || !out || (side!=8u && side!=16u && side!=32u))
        return false;
    size_t unit=side==8u?64u:(size_t)side*side/2u;
    if (gfx_size%unit || code>=gfx_size/unit) return false;
    for (unsigned y=0;y<side;++y)
        for (unsigned x=0;x<side;++x) {
            uint8_t pen;
            if (!cps1_read_tile_pen(gfx,gfx_size,side,code,right_half,x,y,&pen))
                return false;
            out[y*side+x]=pen;
        }
    return true;
}

bool cps1_decode_tile8(const uint8_t *gfx,size_t gfx_size,size_t code,
                       bool right_half,uint8_t out[CPS1_TILE8_PIXELS]) {
    return decode(gfx,gfx_size,code,8u,right_half,out);
}
bool cps1_decode_tile16(const uint8_t *gfx,size_t gfx_size,size_t code,
                        uint8_t out[CPS1_TILE16_PIXELS]) {
    return decode(gfx,gfx_size,code,16u,false,out);
}
bool cps1_decode_tile32(const uint8_t *gfx,size_t gfx_size,size_t code,
                        uint8_t out[CPS1_TILE32_PIXELS]) {
    return decode(gfx,gfx_size,code,32u,false,out);
}
