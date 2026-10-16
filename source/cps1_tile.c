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
