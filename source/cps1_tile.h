#ifndef CPS1_TILE_H
#define CPS1_TILE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define CPS1_GFX_BYTES 0x400000u
#define CPS1_TILE16_BYTES 128u
#define CPS1_TILE16_PIXELS 256u
#define CPS1_TILE16_COUNT (CPS1_GFX_BYTES / CPS1_TILE16_BYTES)

/* Decode one 16x16 4bpp planar CPS-1 tile from an already interleaved ROM
 * region. Returns false on null pointers or a truncated/out-of-range code.
 * Output entries are raw palette indices 0..15, never invented RGB colors.
 */
bool cps1_decode_tile16(const uint8_t *gfx, size_t gfx_size,
                        size_t code, uint8_t out[CPS1_TILE16_PIXELS]);

#endif
