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

    uint8_t tile8[64] = {0};
    uint8_t tile32[1024] = {0};
    uint8_t pen = 99;
    uint8_t full_region[512] = {0};
    /* Scroll1 tilemap bit 5 selects the right 4-byte half-row. */
    for (unsigned row=0;row<8u;++row) {
        full_region[row*8u+0u]=255u; /* left half pen 8 */
        full_region[row*8u+4u]=255u; /* right half pen 8 */
        full_region[row*8u+7u]=255u; /* right half pen 9 */
    }
    assert(cps1_decode_tile8(full_region,sizeof(full_region),0,0,tile8));
    for (unsigned i=0;i<64;++i) assert(tile8[i]==8u);
    assert(cps1_decode_tile8(full_region,sizeof(full_region),0,32,tile8));
    for (unsigned i=0;i<64;++i) assert(tile8[i]==9u);
    assert(cps1_tile_pixel(full_region,sizeof(full_region),8u,0,32,
                           7u,7u,&pen) && pen==9u);
    assert(cps1_decode_tile32(full_region,sizeof(full_region),0,tile32));
    assert(tile32[0]==8u);
    assert(tile32[8]==9u);
    assert(tile32[31]==9u); /* 32x32 row stride is 16 bytes; row1 test data overlaps x24 */
    /* An unmapped code must fail without modifying the result. */
    pen=99u;
    assert(!cps1_tile_pixel(full_region,sizeof(full_region),8u,9u,0,
                            0,0,&pen) && pen==99u);
    assert(!cps1_tile_pixel(full_region,sizeof(full_region),24u,0,0,
                            0,0,&pen) && pen==99u);
    assert(!cps1_tile_pixel(full_region,sizeof(full_region),16u,0,0,
                            16,0,&pen) && pen==99u);
    assert(!cps1_decode_tile8(NULL,sizeof(full_region),0,0,tile8));
    assert(!cps1_decode_tile8(full_region,63u,0,0,tile8));
    assert(!cps1_decode_tile8(full_region,sizeof(full_region),8u,0,tile8));
    assert(!cps1_decode_tile32(full_region,511u,0,tile32));
    assert(!cps1_decode_tile32(full_region,sizeof(full_region),1u,tile32));

    puts("PASS: CPS-1 native C 8x8/16x16/32x32 planes, half-row selection, bounds and decoding");
    return 0;
}
