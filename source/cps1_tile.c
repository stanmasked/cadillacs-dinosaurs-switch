#include "cps1_tile.h"

bool cps1_decode_tile16(const uint8_t *gfx, size_t gfx_size,
                        size_t code, uint8_t out[CPS1_TILE16_PIXELS]) {
    if (!gfx || !out || gfx_size % CPS1_TILE16_BYTES ||
        code >= gfx_size / CPS1_TILE16_BYTES) {
        return false;
    }

    const uint8_t *tile = gfx + code * CPS1_TILE16_BYTES;
    for (size_t y = 0; y < 16; ++y) {
        for (size_t x = 0; x < 16; ++x) {
            const uint8_t *plane = tile + y * 8 + (x / 8) * 4;
            const unsigned bit = 7u - (unsigned)(x % 8);
            uint8_t pen = 0;
            for (unsigned p = 0; p < 4; ++p) {
                pen |= (uint8_t)(((plane[p] >> bit) & 1u) << (3 - p));
            }
            out[y * 16 + x] = pen;
        }
    }
    return true;
}

/* The CPS-1 graphics ROM is interleaved in four 8-bit pixel planes.
 * Scroll1 uses 8x8 half-rows: tilemap address bit 5 selects the
 * 4-byte right half of an 8-byte row. Scroll2 and Scroll3 use 16x16
 * and 32x32 tiles with 8/16 bytes per row respectively.
 */
bool cps1_tile_pixel(const uint8_t *gfx, size_t gfx_size,
                     unsigned side, size_t code, unsigned tile_index,
                     unsigned x, unsigned y, uint8_t *out_pen) {
    if (!gfx || !out_pen || (side!=8u && side!=16u && side!=32u) ||
        x>=side || y>=side) return false;
    size_t stride=side==8u?64u:(size_t)side*side/2u;
    size_t max_code=side==8u?0xffffu:(side==16u?0x7fffu:0x1fffu);
    if (!gfx_size || gfx_size%stride || code>max_code ||
        code>=gfx_size/stride) return false;
    size_t base=code*stride;
    size_t row_stride=side==8u?8u:side/2u;
    size_t half=side==8u && (tile_index&32u)?4u:0u;
    size_t offset=base+(size_t)y*row_stride+half+(x/8u)*4u;
    if (offset+3u>=gfx_size) return false;
    unsigned bit=7u-(x&7u);
    uint8_t pen=0;
    for (unsigned plane=0;plane<4u;++plane)
        pen|=(uint8_t)(((gfx[offset+plane]>>bit)&1u)<<(3u-plane));
    *out_pen=pen;
    return true;
}

bool cps1_decode_tile8(const uint8_t *gfx, size_t gfx_size,
                       size_t code, unsigned tile_index, uint8_t out[64]) {
    if (!out || !gfx || !gfx_size || gfx_size%64u ||
        code>0xffffu || code>=gfx_size/64u) return false;
    for (unsigned y=0;y<8u;++y)
        for (unsigned x=0;x<8u;++x)
            if (!cps1_tile_pixel(gfx,gfx_size,8u,code,tile_index,
                                 x,y,&out[y*8u+x])) return false;
    return true;
}

bool cps1_decode_tile32(const uint8_t *gfx, size_t gfx_size,
                        size_t code, uint8_t out[1024]) {
    if (!out || !gfx || !gfx_size || gfx_size%512u ||
        code>0x1fffu || code>=gfx_size/512u) return false;
    for (unsigned y=0;y<32u;++y)
        for (unsigned x=0;x<32u;++x)
            if (!cps1_tile_pixel(gfx,gfx_size,32u,code,0u,
                                 x,y,&out[y*32u+x])) return false;
    return true;
}
