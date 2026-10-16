/* Host-side tests of the same C code linked into the Switch NRO.
 * No user ROMs or devkitPro libraries needed. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "../source/cps1_tile.h"

static void set_pixel(uint8_t *tile, unsigned x, unsigned y, unsigned pen) {
    const unsigned offset = y * 8 + (x / 8) * 4;
    for (unsigned p = 0; p < 4; ++p) {
        const unsigned mask = 1u << (7 - x % 8);
        if (pen & (1u << (3 - p))) tile[offset + p] |= mask;
        else tile[offset + p] &= (uint8_t)~mask;
    }
}

int main(void) {
    uint8_t gfx[2 * CPS1_TILE16_BYTES] = {0};
    uint8_t pixels[CPS1_TILE16_PIXELS] = {0};

    assert(!cps1_decode_tile16(NULL, sizeof(gfx), 0, pixels));
    assert(!cps1_decode_tile16(gfx, sizeof(gfx), 0, NULL));
    assert(!cps1_decode_tile16(gfx, 129, 0, pixels));
    assert(!cps1_decode_tile16(gfx, sizeof(gfx), 2, pixels));

    for (unsigned y = 0; y < 16; ++y)
        for (unsigned x = 0; x < 16; ++x)
            set_pixel(gfx + CPS1_TILE16_BYTES, x, y, (x + y) & 15);
    assert(cps1_decode_tile16(gfx, sizeof(gfx), 1, pixels));
    for (unsigned y = 0; y < 16; ++y)
        for (unsigned x = 0; x < 16; ++x)
            assert(pixels[y * 16 + x] == ((x + y) & 15));
    assert(cps1_decode_tile16(gfx, sizeof(gfx), 0, pixels));
    for (unsigned i = 0; i < CPS1_TILE16_PIXELS; ++i)
        assert(pixels[i] == 0);

    puts("PASS: CPS-1 native C 16x16 decoder, planes, rows, bounds and tile offsets");
    return 0;
}
